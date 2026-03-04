"""MCP client for interacting with Microsoft 365 via MCP protocol."""

import json
import logging
import os
import uuid
from typing import Any, Dict, List, Optional

import requests

from ..utils.retry import (
    MCP_RETRY_CONFIG,
    with_retry,
    is_retryable_status_code,
    create_retryable_error_from_response,
)

logger = logging.getLogger(__name__)


class MCPClientError(Exception):
    """Base exception for MCP client errors."""

    pass


class MCPAuthenticationError(MCPClientError):
    """Authentication failed (invalid bearer token)."""

    pass


class MCPServerError(MCPClientError):
    """MCP server error."""

    pass


class MCPClient:
    """HTTP client for MCP server using the Model Context Protocol."""

    def __init__(self, bearer_token: str, server_url: Optional[str] = None):
        self.bearer_token = bearer_token
        self.server_url = server_url or os.getenv("MCP_SERVER_URL", "http://localhost:3000")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.bearer_token}",
                "Content-Type": "application/json",
            }
        )

    @with_retry(config=MCP_RETRY_CONFIG)
    def _call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Call an MCP tool using the MCP protocol.

        This method includes automatic retry with exponential backoff for
        transient failures (429, 500, 502, 503, 504, connection errors).
        """
        try:
            # MCP protocol uses JSON-RPC 2.0 style messages
            message = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                },
                "id": str(uuid.uuid4())
            }

            response = self.session.post(
                f"{self.server_url}/api/mcp",
                json=message,
                timeout=30,
            )

            if response.status_code == 401:
                raise MCPAuthenticationError("Invalid bearer token")

            # Handle retryable status codes
            if is_retryable_status_code(response.status_code, MCP_RETRY_CONFIG):
                logger.warning(
                    f"MCP call {tool_name} failed with {response.status_code}, will retry"
                )
                raise create_retryable_error_from_response(
                    response, f"MCP call failed: {response.status_code}"
                )

            response.raise_for_status()
            result = response.json()

            # Handle JSON-RPC response
            if "error" in result:
                error = result["error"]
                raise MCPServerError(f"Tool error: {error.get('message', str(error))}")

            # Extract result from JSON-RPC response
            raw_result = result.get("result", result)

            # MCP server returns {content: [{type: "text", text: "..."}], isError: bool}
            if isinstance(raw_result, dict) and "content" in raw_result:
                if raw_result.get("isError"):
                    error_text = ""
                    for item in raw_result.get("content", []):
                        error_text += item.get("text", "")
                    raise MCPServerError(f"Tool error: {error_text}")

                # Parse text content - may be JSON string
                texts = []
                for item in raw_result.get("content", []):
                    if item.get("type") == "text":
                        text = item.get("text", "")
                        try:
                            texts.append(json.loads(text))
                        except (json.JSONDecodeError, TypeError):
                            texts.append(text)

                if len(texts) == 1:
                    return texts[0]
                return texts if texts else raw_result

            return raw_result

        except requests.exceptions.RequestException as e:
            # Connection errors are retryable
            if isinstance(e, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
                logger.warning(f"MCP connection error for {tool_name}, will retry: {e}")
                raise  # Let the retry decorator handle it
            raise MCPServerError(f"Request failed: {str(e)}")

    # Email Tools

    def get_inbox(self, limit: int = 10, filter_query: Optional[str] = None) -> List[Dict]:
        """Get inbox messages via REST API."""
        try:
            params = {"maxResults": limit}
            if filter_query:
                params["filter"] = filter_query
            response = self.session.get(
                f"{self.server_url}/api/v1/mail/messages",
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            # Normalize: may be a list or a dict with messages key
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "value" in data:
                return data["value"]
            if isinstance(data, dict) and "messages" in data:
                return data["messages"]
            return [data] if data else []
        except requests.exceptions.RequestException as e:
            raise MCPServerError(f"Failed to get inbox: {e}")

    def send_mail(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[List[str]] = None,
        importance: Optional[str] = None,
    ) -> Dict:
        """Send an email via REST API."""
        try:
            payload = {"to": to, "subject": subject, "body": body}
            if cc:
                payload["cc"] = cc
            if importance:
                payload["importance"] = importance
            response = self.session.post(
                f"{self.server_url}/api/v1/mail/send",
                json=payload,
                timeout=30,
            )
            if response.status_code == 401:
                raise MCPAuthenticationError("Invalid bearer token")
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if isinstance(e, MCPAuthenticationError):
                raise
            raise MCPServerError(f"Failed to send mail: {e}")

    def reply_to_mail(self, message_id: str, body: str, reply_all: bool = False) -> Dict:
        """Reply to an email via REST API."""
        try:
            payload = {"messageId": message_id, "body": body, "replyAll": reply_all}
            response = self.session.post(
                f"{self.server_url}/api/v1/mail/reply",
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise MCPServerError(f"Failed to reply: {e}")

    def search_mail(
        self, query: str, limit: int = 10, folder: Optional[str] = None
    ) -> List[Dict]:
        """Search mailbox."""
        args = {"query": query, "limit": limit}
        if folder:
            args["folder"] = folder
        return self._call_tool("searchMail", args)

    def mark_as_read(self, message_id: str) -> Dict:
        """Mark email as read."""
        return self._call_tool("markEmailRead", {"messageId": message_id, "isRead": True})

    def delete_mail(self, message_id: str) -> Dict:
        """Delete an email."""
        return self._call_tool("deleteMail", {"messageId": message_id})

    # Calendar Tools

    def get_events(
        self,
        timeframe: str = "today",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> List[Dict]:
        """Get calendar events."""
        args = {"timeframe": timeframe}
        if start_time:
            args["startTime"] = start_time
        if end_time:
            args["endTime"] = end_time
        return self._call_tool("getEvents", args)

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
        args = {
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
        return self._call_tool("createEvent", args)

    def update_event(self, event_id: str, changes: Dict[str, Any]) -> Dict:
        """Update a calendar event."""
        args = {"eventId": event_id, **changes}
        return self._call_tool("updateEvent", args)

    def delete_event(self, event_id: str) -> Dict:
        """Cancel/delete a calendar event."""
        return self._call_tool("deleteEvent", {"eventId": event_id})

    def respond_to_event(self, event_id: str, response: str, comment: Optional[str] = None) -> Dict:
        """Respond to meeting invite (accept/decline/tentative)."""
        # Server uses separate tools per response type
        tool_map = {
            "accept": "acceptEvent",
            "decline": "declineEvent",
            "tentativelyAccept": "tentativelyAcceptEvent",
            "tentative": "tentativelyAcceptEvent",
        }
        tool = tool_map.get(response, "acceptEvent")
        args = {"eventId": event_id}
        if comment:
            args["comment"] = comment
        return self._call_tool(tool, args)

    # Search Tools

    def search_all(self, query: str, limit: int = 10) -> Dict:
        """Unified search across emails, files, and calendar."""
        args = {"query": query, "limit": limit}
        return self._call_tool("search", args)

    # People Tools

    def search_people(self, query: str, limit: int = 10) -> List[Dict]:
        """Search for people in the organization."""
        args = {"query": query, "limit": limit}
        return self._call_tool("searchPeople", args)

    def find_people(self, name: Optional[str] = None, skills: Optional[List[str]] = None, limit: int = 10) -> List[Dict]:
        """Find people by name or skills."""
        args = {"limit": limit}
        if name:
            args["name"] = name
        if skills:
            args["skills"] = skills
        return self._call_tool("findPeople", args)

    def get_relevant_people(self, limit: int = 10) -> List[Dict]:
        """Get people relevant to the current user."""
        args = {"limit": limit}
        return self._call_tool("getRelevantPeople", args)

    def get_person_by_id(self, person_id: str) -> Dict:
        """Get a specific person by ID."""
        return self._call_tool("getPersonById", {"personId": person_id})

    # File Tools

    def search_files(self, query: str, limit: int = 10) -> List[Dict]:
        """Search OneDrive/SharePoint files."""
        args = {"query": query, "limit": limit}
        return self._call_tool("searchFiles", args)

    def get_file(self, file_id: str) -> Dict:
        """Download file content."""
        return self._call_tool("getFile", {"fileId": file_id})

    # Health Check

    def health_check(self) -> bool:
        """Check if MCP server is reachable and token is valid."""
        try:
            # Try a simple operation
            self.get_inbox(limit=1)
            return True
        except MCPAuthenticationError:
            return False
        except MCPServerError:
            return False

    def test_connection(self) -> Dict[str, Any]:
        """Test connection and return status."""
        try:
            # Test inbox access
            inbox = self.get_inbox(limit=1)
            return {
                "status": "success",
                "server": self.server_url,
                "inbox_accessible": True,
                "message_count": len(inbox) if isinstance(inbox, list) else 0,
            }
        except MCPAuthenticationError as e:
            return {
                "status": "error",
                "error": "Authentication failed",
                "message": str(e),
            }
        except MCPServerError as e:
            return {
                "status": "error",
                "error": "Server error",
                "message": str(e),
            }

    def close(self) -> None:
        """Close the client connection (no-op for HTTP client, for API compatibility)."""
        # HTTP client doesn't maintain persistent connections, so nothing to close
        pass


# CrewAI Tool Wrapper
class MCPTool:
    """Wrapper to use MCP client as a CrewAI tool."""

    def __init__(self, mcp_client: MCPClient):
        self.mcp_client = mcp_client

    def get_inbox(self, limit: int = 10) -> str:
        """Get inbox messages (CrewAI tool format)."""
        try:
            messages = self.mcp_client.get_inbox(limit=limit)
            if not messages:
                return "No messages in inbox."

            result = [f"Found {len(messages)} messages:\n"]
            for i, msg in enumerate(messages, 1):
                result.append(f"\n{i}. From: {msg.get('from', 'Unknown')}")
                result.append(f"   Subject: {msg.get('subject', '(no subject)')}")
                result.append(f"   Received: {msg.get('receivedDateTime', 'Unknown')}")
                if msg.get('isRead') is False:
                    result.append("   Status: UNREAD")

            return "\n".join(result)
        except Exception as e:
            return f"Error getting inbox: {str(e)}"

    def send_email(self, to: str, subject: str, body: str) -> str:
        """Send an email (CrewAI tool format)."""
        try:
            self.mcp_client.send_mail(to=to, subject=subject, body=body)
            return f"✓ Email sent to {to}: {subject}"
        except Exception as e:
            return f"Error sending email: {str(e)}"

    def get_calendar(self, timeframe: str = "today") -> str:
        """Get calendar events (CrewAI tool format)."""
        try:
            events = self.mcp_client.get_events(timeframe=timeframe)
            if not events:
                return f"No events {timeframe}."

            result = [f"Found {len(events)} events {timeframe}:\n"]
            for i, event in enumerate(events, 1):
                result.append(f"\n{i}. {event.get('subject', '(no subject)')}")
                result.append(f"   Start: {event.get('start', 'Unknown')}")
                result.append(f"   End: {event.get('end', 'Unknown')}")
                attendees = event.get('attendees', [])
                if attendees:
                    result.append(f"   Attendees: {len(attendees)}")

            return "\n".join(result)
        except Exception as e:
            return f"Error getting calendar: {str(e)}"
