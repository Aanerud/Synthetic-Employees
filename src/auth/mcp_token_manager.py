"""MCP Token Manager - handles token exchange from MS Graph to MCP JWT."""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Dict, Optional

import requests

from .token_manager import TokenManager, GraphToken
from ..utils.retry import (
    TOKEN_RETRY_CONFIG,
    with_retry,
    is_retryable_status_code,
    create_retryable_error_from_response,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..mcp_client.stdio_client import MCPStdioClient
    from ..mcp_client.client import MCPClient


@dataclass
class MCPToken:
    """MCP Server JWT bearer token."""

    access_token: str
    token_type: str
    expires_at: datetime
    user_id: str
    user_email: str
    user_name: Optional[str] = None

    @property
    def is_expired(self) -> bool:
        """Check if token is expired (with 5 min buffer)."""
        return datetime.now() >= (self.expires_at - timedelta(minutes=5))


class MCPTokenManager:
    """
    Manages MCP JWT tokens for synthetic employees.

    Flow:
    1. Get MS Graph access token via ROPC (using TokenManager)
    2. Exchange Graph token for MCP JWT via /api/auth/graph-token-exchange
    3. Cache MCP tokens and handle refresh

    Usage with stdio client (recommended):
        token_manager = MCPTokenManager()
        client = token_manager.get_stdio_client(email)
        inbox = client.get_inbox()
    """

    def __init__(
        self,
        mcp_server_url: Optional[str] = None,
        graph_token_manager: Optional[TokenManager] = None,
        adapter_path: Optional[str] = None,
    ):
        self.mcp_server_url = mcp_server_url or os.getenv(
            "MCP_SERVER_URL", "http://localhost:3000"
        )
        self.graph_token_manager = graph_token_manager or TokenManager()
        self.adapter_path = adapter_path or os.getenv(
            "MCP_ADAPTER_PATH",
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                "MCP Microsoft Office",
                "mcp-adapter.cjs"
            )
        )

        # MCP token cache: email -> MCPToken
        self._mcp_token_cache: Dict[str, MCPToken] = {}

        # HTTP session for MCP server
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    def get_mcp_token(
        self, email: str, password: Optional[str] = None, force_refresh: bool = False
    ) -> MCPToken:
        """
        Get an MCP JWT token for a user.

        Args:
            email: User email address
            password: User password (uses DEFAULT_PASSWORD env var if not provided)
            force_refresh: Force token refresh even if cached token is valid

        Returns:
            MCPToken with JWT bearer token

        Raises:
            ValueError: If authentication fails
            requests.RequestException: If MCP server communication fails
        """
        # Check cache first
        if not force_refresh and email in self._mcp_token_cache:
            cached = self._mcp_token_cache[email]
            if not cached.is_expired:
                return cached

        # Get password from env if not provided
        if password is None:
            password = os.getenv("DEFAULT_PASSWORD")
            if not password:
                raise ValueError(
                    "Password required - either pass it or set DEFAULT_PASSWORD env var"
                )

        # Step 1: Get MS Graph access token via ROPC
        graph_token = self.graph_token_manager.authenticate(email, password)

        # Step 2: Exchange Graph token for MCP JWT
        mcp_token = self._exchange_for_mcp_token(graph_token)

        # Cache the token
        self._mcp_token_cache[email] = mcp_token

        return mcp_token

    @with_retry(config=TOKEN_RETRY_CONFIG)
    def _exchange_for_mcp_token(self, graph_token: GraphToken) -> MCPToken:
        """
        Exchange MS Graph token for MCP JWT.

        This method includes automatic retry with exponential backoff for
        transient failures (429, 500, 502, 503, 504).

        Args:
            graph_token: Valid MS Graph access token

        Returns:
            MCPToken with MCP JWT bearer token

        Raises:
            ValueError: If token exchange fails
            requests.RequestException: If server communication fails
        """
        exchange_url = f"{self.mcp_server_url}/api/auth/graph-token-exchange"

        response = self._session.post(
            exchange_url,
            json={"graph_access_token": graph_token.access_token},
            timeout=30,
        )

        # Handle 429 rate limiting - raise retryable error
        if response.status_code == 429:
            logger.warning("Token exchange rate limited (429), will retry")
            raise create_retryable_error_from_response(
                response, "Token exchange rate limited"
            )

        # Handle other retryable status codes
        if is_retryable_status_code(response.status_code, TOKEN_RETRY_CONFIG):
            logger.warning(
                f"Token exchange failed with {response.status_code}, will retry"
            )
            raise create_retryable_error_from_response(response)

        if response.status_code == 401:
            error_data = response.json()
            raise ValueError(
                f"Token exchange failed: {error_data.get('error', 'unknown')} - "
                f"{error_data.get('error_description', 'Authentication failed')}"
            )

        if response.status_code >= 400:
            error_data = response.json() if response.content else {}
            raise ValueError(
                f"Token exchange failed ({response.status_code}): "
                f"{error_data.get('error_description', response.text)}"
            )

        response.raise_for_status()
        data = response.json()

        # Parse expiration
        expires_at = datetime.fromisoformat(
            data["expires_at"].replace("Z", "+00:00")
        ).replace(tzinfo=None)

        return MCPToken(
            access_token=data["access_token"],
            token_type=data.get("token_type", "Bearer"),
            expires_at=expires_at,
            user_id=data["user"]["id"],
            user_email=data["user"]["email"],
            user_name=data["user"].get("name"),
        )

    def get_cached_token(self, email: str) -> Optional[MCPToken]:
        """Get cached MCP token for user (if not expired)."""
        if email in self._mcp_token_cache:
            token = self._mcp_token_cache[email]
            if not token.is_expired:
                return token
        return None

    def clear_cache(self, email: Optional[str] = None):
        """Clear token cache for specific user or all users."""
        if email:
            self._mcp_token_cache.pop(email, None)
            self.graph_token_manager.clear_cache(email)
        else:
            self._mcp_token_cache.clear()
            self.graph_token_manager.clear_cache()

    def validate_token(self, token: MCPToken) -> bool:
        """
        Validate an MCP token by making a test API call.

        Args:
            token: MCP token to validate

        Returns:
            True if token is valid and can access the API
        """
        try:
            # Try to access a simple endpoint
            response = self._session.get(
                f"{self.mcp_server_url}/health",
                headers={"Authorization": f"Bearer {token.access_token}"},
                timeout=10,
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def get_authorization_header(self, email: str, password: Optional[str] = None) -> str:
        """
        Get Authorization header value for an agent.

        Convenience method for making authenticated requests.

        Args:
            email: User email address
            password: User password (uses DEFAULT_PASSWORD if not provided)

        Returns:
            Authorization header value (e.g., "Bearer eyJ...")
        """
        token = self.get_mcp_token(email, password)
        return f"Bearer {token.access_token}"

    def get_stdio_client(
        self, email: str, password: Optional[str] = None
    ) -> "MCPStdioClient":
        """
        Get a stdio-based MCP client for a user.

        This is the recommended way to interact with the MCP server as it uses
        the same transport as Claude Desktop, ensuring 1:1 parity.

        Args:
            email: User email address
            password: User password (uses DEFAULT_PASSWORD if not provided)

        Returns:
            MCPStdioClient instance ready to use

        Example:
            token_manager = MCPTokenManager()
            client = token_manager.get_stdio_client("user@example.com")
            inbox = client.get_inbox()
            client.send_mail(to="other@example.com", subject="Hi", body="Hello!")
        """
        # Import here to avoid circular imports
        from ..mcp_client.stdio_client import MCPStdioClient

        mcp_token = self.get_mcp_token(email, password)
        return MCPStdioClient(
            bearer_token=mcp_token.access_token,
            adapter_path=self.adapter_path,
            server_url=self.mcp_server_url,
        )

    def get_http_client(
        self, email: str, password: Optional[str] = None
    ) -> "MCPClient":
        """
        Get an HTTP-based MCP client for a user.

        This is the legacy client that communicates directly via HTTP.
        For new code, prefer get_stdio_client() for Claude Desktop parity.

        Args:
            email: User email address
            password: User password (uses DEFAULT_PASSWORD if not provided)

        Returns:
            MCPClient instance ready to use
        """
        # Import here to avoid circular imports
        from ..mcp_client.client import MCPClient

        mcp_token = self.get_mcp_token(email, password)
        return MCPClient(
            bearer_token=mcp_token.access_token,
            server_url=self.mcp_server_url,
        )
