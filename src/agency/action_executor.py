"""Post-tick action executor.

Takes the structured JSON actions returned by the Agency CLI brain
and executes them via the per-employee MCPClient.
"""

import logging
from typing import Any, Dict, List, Optional

from src.mcp_client.client import MCPClient, MCPClientError

logger = logging.getLogger(__name__)


class ActionExecutor:
    """Executes M365 actions decided by the Agency CLI brain."""

    def __init__(self, mcp_client: MCPClient):
        self.mcp = mcp_client

    def execute_actions(
        self, actions: List[Dict[str, Any]], agent_email: str
    ) -> List[Dict[str, Any]]:
        """Execute a list of actions and return results.

        Each action dict should have a "type" field indicating the action.
        Supported types:
        - send_email: {to, subject, body, cc?}
        - reply_email: {message_id, body, reply_all?}
        - mark_read: {message_id}
        - accept_meeting: {event_id, comment?}
        - decline_meeting: {event_id, comment?}
        - create_meeting: {subject, start, end, attendees, body?}

        Returns list of {action, status, result/error} dicts.
        """
        results = []

        for action in actions:
            action_type = action.get("type", "unknown")
            result = self._execute_one(action_type, action, agent_email)
            results.append(result)

        return results

    def _execute_one(
        self, action_type: str, action: Dict[str, Any], agent_email: str
    ) -> Dict[str, Any]:
        """Execute a single action."""
        try:
            if action_type == "send_email":
                return self._send_email(action)
            elif action_type == "reply_email":
                return self._reply_email(action)
            elif action_type == "mark_read":
                return self._mark_read(action)
            elif action_type == "accept_meeting":
                return self._respond_to_meeting(action, "accept")
            elif action_type == "decline_meeting":
                return self._respond_to_meeting(action, "decline")
            elif action_type == "tentative_meeting":
                return self._respond_to_meeting(action, "tentativelyAccept")
            elif action_type == "create_meeting":
                return self._create_meeting(action)
            elif action_type in ("no_action", "flag_for_later"):
                return {
                    "action": action_type,
                    "status": "skipped",
                    "detail": action.get("reason", "No action needed"),
                }
            else:
                logger.warning("Unknown action type: %s", action_type)
                return {
                    "action": action_type,
                    "status": "skipped",
                    "detail": f"Unknown action type: {action_type}",
                }

        except MCPClientError as e:
            logger.error("Action %s failed: %s", action_type, e)
            return {
                "action": action_type,
                "status": "error",
                "error": str(e),
            }
        except Exception as e:
            logger.error("Unexpected error executing %s: %s", action_type, e)
            return {
                "action": action_type,
                "status": "error",
                "error": str(e),
            }

    def _send_email(self, action: Dict) -> Dict:
        to = action.get("to", "")
        subject = action.get("subject", "")
        body = action.get("body", "")
        cc = action.get("cc")

        if not to or not subject:
            return {
                "action": "send_email",
                "status": "error",
                "error": "Missing 'to' or 'subject'",
            }

        result = self.mcp.send_mail(
            to=to, subject=subject, body=body, cc=cc
        )
        logger.info("Sent email to %s: %s", to, subject)
        return {
            "action": "send_email",
            "status": "success",
            "to": to,
            "subject": subject,
        }

    def _reply_email(self, action: Dict) -> Dict:
        message_id = action.get("message_id", "")
        body = action.get("body", "")
        reply_all = action.get("reply_all", False)

        if not message_id or not body:
            return {
                "action": "reply_email",
                "status": "error",
                "error": "Missing 'message_id' or 'body'",
            }

        result = self.mcp.reply_to_mail(
            message_id=message_id, body=body, reply_all=reply_all
        )
        logger.info("Replied to message %s", message_id[:20])
        return {
            "action": "reply_email",
            "status": "success",
            "message_id": message_id,
        }

    def _mark_read(self, action: Dict) -> Dict:
        message_id = action.get("message_id", "")
        if not message_id:
            return {
                "action": "mark_read",
                "status": "error",
                "error": "Missing 'message_id'",
            }

        self.mcp.mark_as_read(message_id)
        return {"action": "mark_read", "status": "success", "message_id": message_id}

    def _respond_to_meeting(self, action: Dict, response: str) -> Dict:
        event_id = action.get("event_id", "")
        comment = action.get("comment")

        if not event_id:
            return {
                "action": f"{response}_meeting",
                "status": "error",
                "error": "Missing 'event_id'",
            }

        # respond_to_event maps response string to correct server tool
        self.mcp.respond_to_event(
            event_id=event_id, response=response, comment=comment
        )
        logger.info("Responded '%s' to event %s", response, event_id[:20])
        return {
            "action": f"{response}_meeting",
            "status": "success",
            "event_id": event_id,
        }

    def _create_meeting(self, action: Dict) -> Dict:
        subject = action.get("subject", "")
        start = action.get("start", "")
        end = action.get("end", "")
        attendees = action.get("attendees", [])

        if not subject or not start or not end:
            return {
                "action": "create_meeting",
                "status": "error",
                "error": "Missing required fields",
            }

        result = self.mcp.create_event(
            subject=subject,
            start=start,
            end=end,
            attendees=attendees,
            body=action.get("body"),
            is_online_meeting=action.get("is_online", True),
        )
        logger.info("Created meeting: %s", subject)
        return {
            "action": "create_meeting",
            "status": "success",
            "subject": subject,
        }
