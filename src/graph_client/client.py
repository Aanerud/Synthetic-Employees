"""Direct Microsoft Graph API client using MSAL authentication."""

from typing import Any, Dict, List, Optional

import requests

from src.auth.token_manager import GraphToken


class GraphClientError(Exception):
    """Base exception for Graph API client errors."""

    pass


class GraphClient:
    """
    Direct Microsoft Graph API client.

    Uses access tokens from TokenManager to make Graph API calls.
    This bypasses the MCP server and calls Graph directly.
    """

    BASE_URL = "https://graph.microsoft.com/v1.0"

    def __init__(self, token: GraphToken):
        """
        Initialize client with a Graph API token.

        Args:
            token: GraphToken from TokenManager.authenticate()
        """
        self.token = token
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token.access_token}",
                "Content-Type": "application/json",
            }
        )

    def _request(
        self, method: str, endpoint: str, json: Optional[Dict] = None, params: Optional[Dict] = None
    ) -> Any:
        """Make a Graph API request."""
        url = f"{self.BASE_URL}{endpoint}"

        try:
            response = self.session.request(method, url, json=json, params=params, timeout=30)

            if response.status_code == 401:
                raise GraphClientError("Token expired or invalid")

            if response.status_code == 403:
                raise GraphClientError("Permission denied - check API permissions")

            if response.status_code >= 400:
                error_body = response.json() if response.content else {}
                error_msg = error_body.get("error", {}).get("message", response.text)
                raise GraphClientError(f"Graph API error ({response.status_code}): {error_msg}")

            if response.status_code == 204:
                return {}  # No content

            return response.json() if response.content else {}

        except requests.exceptions.RequestException as e:
            raise GraphClientError(f"Request failed: {str(e)}")

    # =========================================================================
    # Email Operations
    # =========================================================================

    def get_inbox(self, limit: int = 10, filter_query: Optional[str] = None) -> List[Dict]:
        """
        Get inbox messages.

        Args:
            limit: Maximum messages to return
            filter_query: OData filter query

        Returns:
            List of message objects
        """
        params = {"$top": limit, "$orderby": "receivedDateTime desc"}
        if filter_query:
            params["$filter"] = filter_query

        result = self._request("GET", "/me/mailFolders/inbox/messages", params=params)
        return result.get("value", [])

    def get_message(self, message_id: str) -> Dict:
        """Get a specific message by ID."""
        return self._request("GET", f"/me/messages/{message_id}")

    def send_mail(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[List[str]] = None,
        importance: str = "normal",
        is_html: bool = False,
    ) -> Dict:
        """
        Send an email.

        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body content
            cc: Optional list of CC recipients
            importance: Email importance (low, normal, high)
            is_html: Whether body is HTML content

        Returns:
            Empty dict on success
        """
        message = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML" if is_html else "Text",
                    "content": body,
                },
                "toRecipients": [{"emailAddress": {"address": to}}],
                "importance": importance,
            }
        }

        if cc:
            message["message"]["ccRecipients"] = [
                {"emailAddress": {"address": addr}} for addr in cc
            ]

        return self._request("POST", "/me/sendMail", json=message)

    def reply_to_mail(self, message_id: str, body: str, reply_all: bool = False) -> Dict:
        """
        Reply to an email.

        Args:
            message_id: ID of message to reply to
            body: Reply body content
            reply_all: Whether to reply to all recipients

        Returns:
            Empty dict on success
        """
        endpoint = f"/me/messages/{message_id}/replyAll" if reply_all else f"/me/messages/{message_id}/reply"
        return self._request("POST", endpoint, json={"comment": body})

    def mark_as_read(self, message_id: str) -> Dict:
        """Mark a message as read."""
        return self._request("PATCH", f"/me/messages/{message_id}", json={"isRead": True})

    def delete_mail(self, message_id: str) -> Dict:
        """Delete a message."""
        return self._request("DELETE", f"/me/messages/{message_id}")

    def search_mail(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Search mailbox.

        Args:
            query: Search query string
            limit: Maximum results

        Returns:
            List of matching messages
        """
        params = {"$search": f'"{query}"', "$top": limit}
        result = self._request("GET", "/me/messages", params=params)
        return result.get("value", [])

    # =========================================================================
    # Calendar Operations
    # =========================================================================

    def get_events(
        self,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict]:
        """
        Get calendar events.

        Args:
            start_time: ISO datetime string for start of range
            end_time: ISO datetime string for end of range
            limit: Maximum events to return

        Returns:
            List of event objects
        """
        params = {"$top": limit, "$orderby": "start/dateTime"}

        if start_time and end_time:
            params["$filter"] = f"start/dateTime ge '{start_time}' and end/dateTime le '{end_time}'"

        result = self._request("GET", "/me/calendar/events", params=params)
        return result.get("value", [])

    def create_event(
        self,
        subject: str,
        start: str,
        end: str,
        attendees: Optional[List[str]] = None,
        body: Optional[str] = None,
        location: Optional[str] = None,
        is_online_meeting: bool = False,
    ) -> Dict:
        """
        Create a calendar event.

        Args:
            subject: Event subject/title
            start: ISO datetime string for start
            end: ISO datetime string for end
            attendees: List of attendee email addresses
            body: Event description
            location: Event location
            is_online_meeting: Whether to create Teams meeting

        Returns:
            Created event object
        """
        event = {
            "subject": subject,
            "start": {"dateTime": start, "timeZone": "UTC"},
            "end": {"dateTime": end, "timeZone": "UTC"},
        }

        if attendees:
            event["attendees"] = [
                {"emailAddress": {"address": addr}, "type": "required"} for addr in attendees
            ]

        if body:
            event["body"] = {"contentType": "Text", "content": body}

        if location:
            event["location"] = {"displayName": location}

        if is_online_meeting:
            event["isOnlineMeeting"] = True
            event["onlineMeetingProvider"] = "teamsForBusiness"

        return self._request("POST", "/me/calendar/events", json=event)

    # =========================================================================
    # User Operations
    # =========================================================================

    def get_me(self) -> Dict:
        """Get current user profile."""
        return self._request("GET", "/me")

    def test_connection(self) -> Dict[str, Any]:
        """Test connection and return status."""
        try:
            user = self.get_me()
            return {
                "status": "success",
                "user": user.get("displayName"),
                "email": user.get("mail") or user.get("userPrincipalName"),
            }
        except GraphClientError as e:
            return {
                "status": "error",
                "error": str(e),
            }
