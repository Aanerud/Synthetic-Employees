"""MCP Stdio Client - communicates with MCP server via stdio transport.

This client spawns mcp-adapter.cjs as a subprocess and communicates via
stdin/stdout using the JSON-RPC 2.0 protocol. This is the same transport
used by Claude Desktop, ensuring 1:1 parity.
"""

import json
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from queue import Empty, Queue
from typing import Any, Dict, List, Optional

from ..utils.retry import MCP_RETRY_CONFIG, RetryableError, with_retry

logger = logging.getLogger(__name__)


class MCPStdioError(Exception):
    """Base exception for MCP Stdio client errors."""
    pass


class MCPStdioAuthenticationError(MCPStdioError):
    """Authentication failed (invalid bearer token)."""
    pass


class MCPStdioServerError(MCPStdioError):
    """MCP server error."""
    pass


class MCPStdioConnectionError(MCPStdioError):
    """Connection to MCP adapter failed."""
    pass


class MCPStdioClient:
    """
    MCP client using stdio transport (same as Claude Desktop).

    Spawns mcp-adapter.cjs as a subprocess with MCP_BEARER_TOKEN environment
    variable and communicates via JSON-RPC 2.0 over stdin/stdout.
    """

    def __init__(
        self,
        bearer_token: str,
        adapter_path: Optional[str] = None,
        server_url: Optional[str] = None,
        timeout: float = 30.0,
    ):
        """
        Initialize the MCP Stdio Client.

        Args:
            bearer_token: MCP JWT bearer token for authentication
            adapter_path: Path to mcp-adapter.cjs (uses MCP_ADAPTER_PATH env var if not provided)
            server_url: MCP server URL (uses MCP_SERVER_URL env var if not provided)
            timeout: Request timeout in seconds
        """
        self.bearer_token = bearer_token
        self.adapter_path = adapter_path or os.getenv(
            "MCP_ADAPTER_PATH",
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                "MCP Microsoft Office",
                "mcp-adapter.cjs"
            )
        )
        self.server_url = server_url or os.getenv("MCP_SERVER_URL", "http://localhost:3000")
        self.timeout = timeout

        self._process: Optional[subprocess.Popen] = None
        self._response_queue: Queue = Queue()
        self._pending_requests: Dict[str, Queue] = {}
        self._reader_thread: Optional[threading.Thread] = None
        self._initialized = False
        self._lock = threading.Lock()

        # Start the adapter process
        self._start_adapter()

        # Initialize MCP connection
        self._initialize()

    def _start_adapter(self):
        """Start the mcp-adapter.cjs subprocess."""
        if not os.path.exists(self.adapter_path):
            raise MCPStdioConnectionError(
                f"MCP adapter not found at: {self.adapter_path}"
            )

        # Prepare environment with bearer token
        env = os.environ.copy()
        env["MCP_BEARER_TOKEN"] = self.bearer_token
        env["MCP_SERVER_URL"] = self.server_url

        try:
            self._process = subprocess.Popen(
                ["node", self.adapter_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=1,  # Line buffered
            )
        except FileNotFoundError:
            raise MCPStdioConnectionError(
                "Node.js not found. Please install Node.js to use the stdio transport."
            )
        except Exception as e:
            raise MCPStdioConnectionError(f"Failed to start MCP adapter: {e}")

        # Start background thread to read responses
        self._reader_thread = threading.Thread(target=self._read_responses, daemon=True)
        self._reader_thread.start()

        # Give the process a moment to start
        time.sleep(0.1)

        # Check if process started successfully
        if self._process.poll() is not None:
            stderr = self._process.stderr.read() if self._process.stderr else ""
            raise MCPStdioConnectionError(
                f"MCP adapter process exited immediately. stderr: {stderr}"
            )

    def _read_responses(self):
        """Background thread to read responses from stdout."""
        while self._process and self._process.poll() is None:
            try:
                line = self._process.stdout.readline()
                if not line:
                    continue

                line = line.strip()
                if not line:
                    continue

                try:
                    response = json.loads(line)

                    # Route response to the appropriate pending request
                    request_id = response.get("id")
                    if request_id and request_id in self._pending_requests:
                        self._pending_requests[request_id].put(response)
                    else:
                        # Notification or unmatched response
                        self._response_queue.put(response)

                except json.JSONDecodeError:
                    # Skip non-JSON lines (logs, etc.)
                    pass

            except Exception:
                # Process likely terminated
                break

    def _send_message(self, message: dict) -> dict:
        """
        Send a JSON-RPC message and wait for response.

        Args:
            message: JSON-RPC 2.0 message to send

        Returns:
            JSON-RPC 2.0 response

        Raises:
            MCPStdioConnectionError: If connection is broken
            MCPStdioServerError: If server returns an error
        """
        if not self._process or self._process.poll() is not None:
            raise MCPStdioConnectionError("MCP adapter process is not running")

        request_id = message.get("id", str(uuid.uuid4()))
        message["id"] = request_id

        # Create a queue for this request's response
        response_queue: Queue = Queue()
        self._pending_requests[request_id] = response_queue

        try:
            # Send the message
            json_message = json.dumps(message)
            with self._lock:
                self._process.stdin.write(json_message + "\n")
                self._process.stdin.flush()

            # Wait for response
            try:
                response = response_queue.get(timeout=self.timeout)
            except Empty:
                raise MCPStdioServerError(
                    f"Request timed out after {self.timeout} seconds"
                )

            return response

        finally:
            # Clean up pending request
            self._pending_requests.pop(request_id, None)

    def _initialize(self):
        """Initialize the MCP connection."""
        # Send initialize request
        init_response = self._send_message({
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "synthetic-employees",
                    "version": "1.0.0"
                }
            },
            "id": str(uuid.uuid4())
        })

        if "error" in init_response:
            error = init_response["error"]
            raise MCPStdioServerError(
                f"Initialization failed: {error.get('message', str(error))}"
            )

        # Send initialized notification
        self._send_message({
            "jsonrpc": "2.0",
            "method": "initialized",
            "params": {},
            "id": str(uuid.uuid4())
        })

        self._initialized = True

    def _is_retryable_error(self, error_message: str) -> bool:
        """Check if an error message indicates a retryable condition."""
        retryable_indicators = [
            "429",
            "500",
            "502",
            "503",
            "504",
            "rate limit",
            "too many requests",
            "service unavailable",
            "gateway",
            "timeout",
            "ECONNRESET",
            "ETIMEDOUT",
        ]
        error_lower = error_message.lower()
        return any(indicator.lower() in error_lower for indicator in retryable_indicators)

    @with_retry(config=MCP_RETRY_CONFIG)
    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """
        Call an MCP tool.

        This method includes automatic retry with exponential backoff for
        transient failures (rate limits, server errors, connection issues).

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            Tool result

        Raises:
            MCPStdioAuthenticationError: If authentication fails
            MCPStdioServerError: If tool execution fails
        """
        response = self._send_message({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments
            },
            "id": str(uuid.uuid4())
        })

        if "error" in response:
            error = response["error"]
            error_message = error.get("message", str(error))

            # Check for authentication errors (not retryable)
            if "401" in error_message or "unauthorized" in error_message.lower():
                raise MCPStdioAuthenticationError(error_message)

            # Check for retryable errors
            if self._is_retryable_error(error_message):
                logger.warning(f"Retryable MCP error for {name}: {error_message}")
                raise RetryableError(f"Tool error (retryable): {error_message}")

            raise MCPStdioServerError(f"Tool error: {error_message}")

        # Extract result
        result = response.get("result", {})

        # Handle MCP content format
        if isinstance(result, dict) and "content" in result:
            content = result["content"]
            if isinstance(content, list) and len(content) > 0:
                first_content = content[0]
                if isinstance(first_content, dict) and first_content.get("type") == "text":
                    text = first_content.get("text", "")
                    # Try to parse as JSON
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        return text

        return result

    def list_tools(self) -> List[Dict]:
        """Get list of available tools."""
        response = self._send_message({
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {},
            "id": str(uuid.uuid4())
        })

        if "error" in response:
            error = response["error"]
            raise MCPStdioServerError(
                f"Failed to list tools: {error.get('message', str(error))}"
            )

        result = response.get("result", {})
        return result.get("tools", [])

    # ========== Email Tools ==========

    def get_inbox(self, limit: int = 10, filter_query: Optional[str] = None) -> List[Dict]:
        """Get inbox messages."""
        args: Dict[str, Any] = {"limit": limit}
        if filter_query:
            args["filter"] = filter_query
        return self.call_tool("readMail", args)

    def send_mail(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[List[str]] = None,
        importance: Optional[str] = None,
    ) -> Dict:
        """Send an email."""
        args: Dict[str, Any] = {"to": to, "subject": subject, "body": body}
        if cc:
            args["cc"] = cc
        if importance:
            args["importance"] = importance
        return self.call_tool("sendMail", args)

    def reply_to_mail(self, message_id: str, body: str, reply_all: bool = False) -> Dict:
        """Reply to an email."""
        args = {"messageId": message_id, "body": body, "replyAll": reply_all}
        return self.call_tool("replyToMail", args)

    def search_mail(
        self, query: str, limit: int = 10, folder: Optional[str] = None
    ) -> List[Dict]:
        """Search mailbox."""
        args: Dict[str, Any] = {"query": query, "limit": limit}
        if folder:
            args["folder"] = folder
        return self.call_tool("searchMail", args)

    def mark_as_read(self, message_id: str) -> Dict:
        """Mark email as read."""
        return self.call_tool("markEmailRead", {"messageId": message_id})

    def delete_mail(self, message_id: str) -> Dict:
        """Delete an email."""
        return self.call_tool("deleteMail", {"messageId": message_id})

    # ========== Attachment Tools ==========

    def get_mail_attachments(self, message_id: str) -> List[Dict]:
        """Get attachments for an email message."""
        result = self.call_tool("getMailAttachments", {"id": message_id})
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "value" in result:
            return result["value"]
        return [result] if result else []

    # ========== File Tools ==========

    def upload_file(self, filename: str, content: str, folder: str = "Documents") -> Dict:
        """Upload a file to OneDrive."""
        return self.call_tool("uploadFile", {
            "fileName": filename,
            "content": content,
            "folderPath": folder,
        })

    def create_sharing_link(self, file_id: str) -> Dict:
        """Create a sharing link for a file."""
        return self.call_tool("createSharingLink", {
            "fileId": file_id,
            "type": "view",
            "scope": "organization",
        })

    def get_file_content(self, file_id: str) -> Dict:
        """Get the content of a file."""
        return self.call_tool("getFileContent", {"fileId": file_id})

    # ========== Calendar Tools ==========

    def get_events(
        self,
        timeframe: str = "today",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> List[Dict]:
        """Get calendar events."""
        args: Dict[str, Any] = {"timeframe": timeframe}
        if start_time:
            args["startTime"] = start_time
        if end_time:
            args["endTime"] = end_time
        return self.call_tool("getEvents", args)

    def create_event(
        self,
        subject: str,
        start: str,
        end: str,
        attendees: List[str],
        body: Optional[str] = None,
        location: Optional[str] = None,
        is_online_meeting: bool = False,
    ) -> Dict:
        """Create a calendar event."""
        args: Dict[str, Any] = {
            "subject": subject,
            "start": start,
            "end": end,
            "attendees": attendees,
        }
        if body:
            args["body"] = body
        if location:
            args["location"] = location
        if is_online_meeting:
            args["isOnlineMeeting"] = True
        return self.call_tool("createEvent", args)

    def update_event(self, event_id: str, changes: Dict[str, Any]) -> Dict:
        """Update a calendar event."""
        args = {"eventId": event_id, **changes}
        return self.call_tool("updateEvent", args)

    def delete_event(self, event_id: str) -> Dict:
        """Cancel/delete a calendar event."""
        return self.call_tool("deleteEvent", {"eventId": event_id})

    def respond_to_event(
        self, event_id: str, response: str, comment: Optional[str] = None
    ) -> Dict:
        """Respond to meeting invite (accept/decline/tentative)."""
        args: Dict[str, Any] = {"eventId": event_id, "response": response}
        if comment:
            args["comment"] = comment
        return self.call_tool("respondToEvent", args)

    # ========== Search Tools ==========

    def search_all(self, query: str, limit: int = 10) -> Dict:
        """Unified search across emails, files, and calendar."""
        args = {"query": query, "limit": limit}
        return self.call_tool("searchAll", args)

    # ========== File Tools ==========

    def search_files(self, query: str, limit: int = 10) -> List[Dict]:
        """Search OneDrive/SharePoint files."""
        args = {"query": query, "limit": limit}
        return self.call_tool("searchFiles", args)

    def get_file(self, file_id: str) -> Dict:
        """Download file content."""
        return self.call_tool("getFile", {"fileId": file_id})

    # ========== Teams/Groups Tools ==========

    def list_teams(self) -> List[Dict]:
        """Get list of joined Teams."""
        result = self.call_tool("listJoinedTeams", {})
        # Handle nested response format {'teams': [...], 'count': N}
        if isinstance(result, dict) and "teams" in result:
            return result["teams"]
        return result if isinstance(result, list) else []

    def list_channels(self, team_id: str) -> List[Dict]:
        """Get channels for a team."""
        result = self.call_tool("listTeamChannels", {"teamId": team_id})
        # Handle nested response format {'channels': [...], 'count': N}
        if isinstance(result, dict) and "channels" in result:
            return result["channels"]
        return result if isinstance(result, list) else []

    def send_channel_message(
        self,
        team_id: str,
        channel_id: str,
        content: str,
        content_type: str = "text",
    ) -> Dict:
        """Send a message to a Teams channel."""
        return self.call_tool(
            "sendChannelMessage",
            {
                "teamId": team_id,
                "channelId": channel_id,
                "content": content,
                "contentType": content_type,
            },
        )

    def reply_to_channel_message(
        self,
        team_id: str,
        channel_id: str,
        message_id: str,
        content: str,
        content_type: str = "text",
    ) -> Dict:
        """Reply to a message in a Teams channel."""
        return self.call_tool(
            "replyToMessage",
            {
                "teamId": team_id,
                "channelId": channel_id,
                "messageId": message_id,
                "content": content,
                "contentType": content_type,
            },
        )

    def get_channel_messages(
        self,
        team_id: str,
        channel_id: str,
        limit: int = 20,
    ) -> List[Dict]:
        """Get messages from a Teams channel."""
        result = self.call_tool(
            "getChannelMessages",
            {"teamId": team_id, "channelId": channel_id, "limit": limit},
        )
        # Handle nested response format {'messages': [...], 'count': N}
        if isinstance(result, dict) and "messages" in result:
            return result["messages"]
        return result if isinstance(result, list) else []

    def list_chats(self) -> List[Dict]:
        """Get list of chats."""
        result = self.call_tool("listChats", {})
        # Handle nested response format {'chats': [...], 'count': N}
        if isinstance(result, dict) and "chats" in result:
            return result["chats"]
        return result if isinstance(result, list) else []

    def create_chat(
        self,
        member_emails: List[str],
        chat_type: str = "oneOnOne",
        topic: Optional[str] = None,
    ) -> Dict:
        """
        Create a new chat (1:1 or group).

        Args:
            member_emails: List of email addresses to add to the chat
            chat_type: Chat type ('oneOnOne' or 'group')
            topic: Chat topic (for group chats)

        Returns:
            Created chat object
        """
        # Format members as expected by the API
        members = [{"email": email} for email in member_emails]
        args: Dict[str, Any] = {
            "members": members,
            "chatType": chat_type,
        }
        if topic:
            args["topic"] = topic
        result = self.call_tool("createChat", args)
        # Handle nested response format {'chat': {...}, 'success': True}
        if isinstance(result, dict) and "chat" in result:
            return result["chat"]
        return result

    def send_chat_message(self, chat_id: str, content: str) -> Dict:
        """Send a message to a chat."""
        result = self.call_tool(
            "sendChatMessage",
            {"chatId": chat_id, "content": content},
        )
        # Handle nested response format {'message': {...}, 'success': True}
        if isinstance(result, dict) and "message" in result:
            return result["message"]
        return result

    def get_chat_messages(self, chat_id: str, limit: int = 20) -> List[Dict]:
        """Get messages from a chat."""
        result = self.call_tool(
            "getChatMessages",
            {"chatId": chat_id, "limit": limit},
        )
        # Handle nested response format {'messages': [...], 'count': N}
        if isinstance(result, dict) and "messages" in result:
            return result["messages"]
        return result if isinstance(result, list) else []

    def create_online_meeting(
        self,
        subject: str,
        start_time: str,
        end_time: str,
        attendees: Optional[List[str]] = None,
    ) -> Dict:
        """Create an online Teams meeting."""
        args: Dict[str, Any] = {
            "subject": subject,
            "startDateTime": start_time,
            "endDateTime": end_time,
        }
        if attendees:
            args["attendees"] = attendees
        return self.call_tool("createOnlineMeeting", args)

    # ========== Health Check ==========

    def health_check(self) -> bool:
        """Check if MCP connection is working."""
        try:
            self.get_inbox(limit=1)
            return True
        except MCPStdioAuthenticationError:
            return False
        except MCPStdioServerError:
            return False
        except MCPStdioConnectionError:
            return False

    def test_connection(self) -> Dict[str, Any]:
        """Test connection and return status."""
        try:
            inbox = self.get_inbox(limit=1)
            return {
                "status": "success",
                "transport": "stdio",
                "adapter_path": self.adapter_path,
                "inbox_accessible": True,
                "message_count": len(inbox) if isinstance(inbox, list) else 0,
            }
        except MCPStdioAuthenticationError as e:
            return {
                "status": "error",
                "error": "Authentication failed",
                "message": str(e),
            }
        except MCPStdioServerError as e:
            return {
                "status": "error",
                "error": "Server error",
                "message": str(e),
            }
        except MCPStdioConnectionError as e:
            return {
                "status": "error",
                "error": "Connection error",
                "message": str(e),
            }

    def close(self):
        """Close the MCP adapter process."""
        if self._process:
            try:
                self._process.stdin.close()
            except Exception:
                pass

            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass

            self._process = None

        self._initialized = False

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False

    def __del__(self):
        """Destructor - ensure process is cleaned up."""
        self.close()
