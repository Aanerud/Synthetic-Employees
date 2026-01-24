"""Token manager using MSAL for Microsoft Graph authentication."""

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional

import msal


@dataclass
class GraphToken:
    """Microsoft Graph API access token."""

    access_token: str
    expires_at: datetime
    scopes: list[str]
    user_email: str

    @property
    def is_expired(self) -> bool:
        """Check if token is expired (with 5 min buffer)."""
        return datetime.now() >= (self.expires_at - timedelta(minutes=5))


class TokenManager:
    """
    Manages Microsoft Graph API tokens using MSAL ROPC flow.

    Uses Resource Owner Password Credentials (ROPC) to authenticate
    users directly with username/password. This works for non-federated
    accounts without MFA enabled.
    """

    # Microsoft Graph API scopes
    DEFAULT_SCOPES = [
        "https://graph.microsoft.com/Mail.ReadWrite",
        "https://graph.microsoft.com/Mail.Send",
        "https://graph.microsoft.com/Calendars.ReadWrite",
        "https://graph.microsoft.com/User.Read",
    ]

    def __init__(
        self,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
    ):
        self.tenant_id = tenant_id or os.getenv("AZURE_TENANT_ID")
        self.client_id = client_id or os.getenv("AZURE_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("AZURE_CLIENT_SECRET")

        if not self.tenant_id or not self.client_id:
            raise ValueError(
                "AZURE_TENANT_ID and AZURE_CLIENT_ID must be set in environment or passed as arguments"
            )

        # Token cache: email -> GraphToken
        self._token_cache: Dict[str, GraphToken] = {}

        # Create MSAL confidential client app (if we have client secret)
        # or public client app (for ROPC without secret)
        authority = f"https://login.microsoftonline.com/{self.tenant_id}"

        if self.client_secret:
            self._app = msal.ConfidentialClientApplication(
                client_id=self.client_id,
                client_credential=self.client_secret,
                authority=authority,
            )
        else:
            self._app = msal.PublicClientApplication(
                client_id=self.client_id,
                authority=authority,
            )

    def authenticate(
        self, username: str, password: str, scopes: Optional[list[str]] = None
    ) -> GraphToken:
        """
        Authenticate user with username/password (ROPC flow).

        Args:
            username: User email (e.g., user@domain.onmicrosoft.com)
            password: User password
            scopes: OAuth scopes (defaults to mail/calendar access)

        Returns:
            GraphToken with access token

        Raises:
            ValueError: If authentication fails
        """
        scopes = scopes or self.DEFAULT_SCOPES

        # Check cache first
        if username in self._token_cache:
            cached = self._token_cache[username]
            if not cached.is_expired:
                return cached

        # Acquire token via ROPC
        result = self._app.acquire_token_by_username_password(
            username=username,
            password=password,
            scopes=scopes,
        )

        if "access_token" not in result:
            error = result.get("error", "unknown_error")
            error_description = result.get("error_description", "Authentication failed")
            raise ValueError(f"Authentication failed for {username}: {error} - {error_description}")

        # Calculate expiration (typically 1 hour)
        expires_in = result.get("expires_in", 3600)
        expires_at = datetime.now() + timedelta(seconds=expires_in)

        token = GraphToken(
            access_token=result["access_token"],
            expires_at=expires_at,
            scopes=scopes,
            user_email=username,
        )

        # Cache the token
        self._token_cache[username] = token

        return token

    def get_token(self, username: str) -> Optional[GraphToken]:
        """Get cached token for user (if not expired)."""
        if username in self._token_cache:
            token = self._token_cache[username]
            if not token.is_expired:
                return token
        return None

    def clear_cache(self, username: Optional[str] = None):
        """Clear token cache for specific user or all users."""
        if username:
            self._token_cache.pop(username, None)
        else:
            self._token_cache.clear()
