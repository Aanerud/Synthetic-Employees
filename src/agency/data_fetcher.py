"""Pre-tick data fetcher.

Fetches inbox, calendar, and Teams data via the per-employee
MCPClient before passing it as context to the Agency CLI brain.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from src.mcp_client.client import MCPClient, MCPClientError

# DataFetcher works with any client that has get_inbox() and get_events() methods
# This includes both MCPClient (HTTP, mock) and MCPStdioClient (stdio, real Graph API)

logger = logging.getLogger(__name__)


def _format_email(msg: Dict[str, Any]) -> str:
    """Format a single email message for the agent context."""
    from_data = msg.get("from", {})
    sender = (
        from_data.get("email")
        or from_data.get("emailAddress", {}).get("address", "unknown")
    )
    sender_name = (
        from_data.get("name")
        or from_data.get("emailAddress", {}).get("name", "")
    )
    subject = msg.get("subject", "(no subject)")
    preview = msg.get("bodyPreview", msg.get("preview", ""))[:300]
    msg_id = msg.get("id", "")
    is_read = msg.get("isRead", True)
    received = msg.get("receivedDateTime", "")

    status = "UNREAD" if not is_read else "read"
    sender_str = f"{sender_name} <{sender}>" if sender_name else sender
    has_attachments = msg.get("hasAttachments", False)

    lines = [
        f"- [{status}] ID: {msg_id}",
        f"  From: {sender_str}",
        f"  Subject: {subject}",
        f"  Received: {received}",
    ]
    if has_attachments:
        lines.append(f"  Attachments: YES (use the email to view details)")
    lines.append(f"  Preview: {preview}")

    return "\n".join(lines)


def _format_event(event: Dict[str, Any]) -> str:
    """Format a single calendar event for the agent context."""
    subject = event.get("subject", "(no subject)")
    start = event.get("start", {})
    end = event.get("end", {})
    start_time = start.get("dateTime", start) if isinstance(start, dict) else start
    end_time = end.get("dateTime", end) if isinstance(end, dict) else end
    organizer = event.get("organizer", {}).get("emailAddress", {}).get("address", "")
    attendees = event.get("attendees", [])
    event_id = event.get("id", "")
    response = event.get("responseStatus", {}).get("response", "none")

    attendee_str = ", ".join(
        a.get("emailAddress", {}).get("address", "")
        for a in attendees[:5]
    ) if attendees else "none"

    return (
        f"- ID: {event_id}\n"
        f"  Subject: {subject}\n"
        f"  Time: {start_time} to {end_time}\n"
        f"  Organizer: {organizer}\n"
        f"  Attendees: {attendee_str}\n"
        f"  Your response: {response}"
    )


class DataFetcher:
    """Fetches M365 data for an employee before their Agency tick."""

    def __init__(self, mcp_client: MCPClient):
        self.mcp = mcp_client

    def fetch_inbox(self, limit: int = 10) -> str:
        """Fetch inbox and format as text context."""
        try:
            messages = self.mcp.get_inbox(limit=limit)
            if not messages:
                return "Your inbox is empty. No new messages."

            unread = sum(1 for m in messages if not m.get("isRead", True))
            lines = [f"You have {len(messages)} recent emails ({unread} unread):\n"]
            for msg in messages:
                lines.append(_format_email(msg))
            return "\n\n".join(lines)

        except MCPClientError as e:
            logger.warning("Failed to fetch inbox: %s", e)
            return f"[Error fetching inbox: {e}]"

    def fetch_calendar(self, timeframe: str = "today") -> str:
        """Fetch calendar events and format as text context."""
        try:
            events = self.mcp.get_events(timeframe=timeframe)
            if not events:
                return f"No calendar events {timeframe}."

            lines = [f"Your calendar for {timeframe} ({len(events)} events):\n"]
            for event in events:
                lines.append(_format_event(event))
            return "\n\n".join(lines)

        except MCPClientError as e:
            logger.warning("Failed to fetch calendar: %s", e)
            return f"[Error fetching calendar: {e}]"

    def fetch_all(self, inbox_limit: int = 10) -> Dict[str, str]:
        """Fetch all data sources and return as dict of text contexts."""
        return {
            "inbox": self.fetch_inbox(limit=inbox_limit),
            "calendar": self.fetch_calendar(timeframe="today"),
        }
