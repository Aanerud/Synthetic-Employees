"""Context assembler for Agency CLI prompts.

Builds a memory context string from the database for injection into
Agency agent templates via the {{MemoryContext}} variable.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.database.db_service import DatabaseService

logger = logging.getLogger(__name__)


class ContextAssembler:
    """Assembles memory context from the database for Agency prompts."""

    def __init__(self, db: DatabaseService):
        self.db = db

    def build_context(
        self,
        email: str,
        include_conversations: bool = True,
        include_tasks: bool = True,
        include_knowledge: bool = True,
        include_pending: bool = True,
        include_processed_ids: bool = True,
        max_conversations: int = 5,
        max_tasks: int = 10,
        max_knowledge: int = 10,
        lookback_hours: int = 48,
    ) -> str:
        """Build memory context string for an employee.

        Args:
            email: Employee email address.
            include_conversations: Include recent conversation summaries.
            include_tasks: Include active project tasks.
            include_knowledge: Include known facts about contacts.
            include_pending: Include flagged pending items.
            include_processed_ids: Include recently processed message IDs.
            max_conversations: Max number of conversations to include.
            max_tasks: Max number of tasks to include.
            max_knowledge: Max number of knowledge items to include.
            lookback_hours: How far back to look for context.

        Returns:
            Formatted context string for the MemoryContext variable.
        """
        parts: List[str] = []
        cutoff = (
            datetime.now() - timedelta(hours=lookback_hours)
        ).isoformat()

        if include_conversations:
            section = self._build_conversations_section(
                email, cutoff, max_conversations
            )
            if section:
                parts.append(section)

        if include_tasks:
            section = self._build_tasks_section(email, max_tasks)
            if section:
                parts.append(section)

        if include_knowledge:
            section = self._build_knowledge_section(email, max_knowledge)
            if section:
                parts.append(section)

        if include_pending:
            section = self._build_pending_section(email)
            if section:
                parts.append(section)

        if include_processed_ids:
            section = self._build_processed_ids_section(email, cutoff)
            if section:
                parts.append(section)

        # What you did last cycle
        last_actions = self._build_last_cycle_section(email)
        if last_actions:
            parts.insert(0, last_actions)

        if not parts:
            return "No prior context available. This may be your first check-in."

        return "\n\n".join(parts)

    def _build_conversations_section(
        self, email: str, cutoff: str, limit: int
    ) -> Optional[str]:
        """Build recent conversations section."""
        try:
            conversations = self.db.get_recent_conversations(
                email, since=cutoff, limit=limit
            )
        except Exception:
            conversations = []

        if not conversations:
            return None

        lines = ["## Recent Conversations"]
        for conv in conversations:
            summary = conv.get("summary", "No summary")
            participants = conv.get("participants", "")
            context_type = conv.get("context_type", "unknown")
            lines.append(
                f"- [{context_type}] {summary} (with: {participants})"
            )

        return "\n".join(lines)

    def _build_tasks_section(
        self, email: str, limit: int
    ) -> Optional[str]:
        """Build active tasks section."""
        try:
            tasks = self.db.get_tasks_for_agent(email, limit=limit)
        except Exception:
            tasks = []

        if not tasks:
            return None

        lines = ["## Your Active Tasks"]
        for task in tasks:
            title = task.get("title", "Untitled")
            status = task.get("status", "unknown")
            priority = task.get("priority", "normal")
            lines.append(f"- [{status}] {title} (Priority: {priority})")

        return "\n".join(lines)

    def _build_knowledge_section(
        self, email: str, limit: int
    ) -> Optional[str]:
        """Build knowledge about contacts section."""
        try:
            knowledge = self.db.get_knowledge_for_agent(
                email, limit=limit
            )
        except Exception:
            knowledge = []

        if not knowledge:
            return None

        lines = ["## What You Know"]
        for item in knowledge:
            ktype = item.get("knowledge_type", "")
            subject = item.get("subject", "")
            content = item.get("content", "")
            lines.append(f"- [{ktype}] {subject}: {content}")

        return "\n".join(lines)

    def _build_pending_section(self, email: str) -> Optional[str]:
        """Build pending items section from employee_state."""
        try:
            state = self.db.get_employee_state(email)
        except Exception:
            state = None

        if not state:
            return None

        pending_raw = state.get("pending_items")
        if not pending_raw:
            return None

        try:
            pending = json.loads(pending_raw)
        except (json.JSONDecodeError, TypeError):
            return None

        if not pending:
            return None

        lines = ["## Pending Items (from previous cycles)"]
        for item in pending:
            if isinstance(item, dict):
                desc = item.get("description", str(item))
                priority = item.get("priority", "normal")
                lines.append(f"- {desc} (Priority: {priority})")
            else:
                lines.append(f"- {item}")

        return "\n".join(lines)

    def _build_last_cycle_section(self, email: str) -> Optional[str]:
        """Build summary of what the agent did in its last cycle."""
        try:
            logs = self.db.get_activity_log(
                agent_email=email,
                action_type="agency_execution",
                limit=1,
            )
        except Exception:
            logs = []

        if not logs:
            return None

        last = logs[0]
        if not last.action_data:
            return None

        data = last.action_data
        actions = data.get("actions_taken", [])
        if not actions:
            return None

        lines = ["## What You Did Last Cycle"]
        for a in actions[:5]:
            atype = a.get("type", "unknown")
            if atype == "send_email":
                lines.append(f"- Sent email to {a.get('to', '?')}: {a.get('subject', '?')}")
            elif atype == "reply_email":
                lines.append(f"- Replied to message {a.get('message_id', '?')[:20]}...")
            elif atype == "mark_read":
                lines.append(f"- Marked message as read")
            elif atype in ("accept_meeting", "decline_meeting"):
                lines.append(f"- {atype.replace('_', ' ').title()}")
            elif atype == "no_action":
                lines.append(f"- No action taken: {a.get('reason', '')}")
            else:
                lines.append(f"- {atype}")

        return "\n".join(lines)

    def _build_processed_ids_section(
        self, email: str, cutoff: str
    ) -> Optional[str]:
        """Build section of already-processed message IDs."""
        try:
            state = self.db.get_employee_state(email)
        except Exception:
            state = None

        if not state:
            return None

        processed_emails = state.get("processed_email_ids")
        processed_teams = state.get("processed_teams_ids")

        ids = []
        if processed_emails:
            try:
                ids.extend(json.loads(processed_emails))
            except (json.JSONDecodeError, TypeError):
                pass

        if not ids:
            return None

        # Only show last 20 IDs to avoid bloating the prompt
        recent_ids = ids[-20:]
        return (
            f"## Already Processed\n"
            f"Skip these message IDs (already handled): "
            f"{', '.join(str(i) for i in recent_ids)}"
        )
