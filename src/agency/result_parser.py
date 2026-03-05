"""Parse Agency CLI output and update database state.

After each Agency execution, this module processes the structured
JSON output and persists results to the database.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.agency.cli_runner import AgencyResult
from src.database.db_service import DatabaseService

logger = logging.getLogger(__name__)


class ResultParser:
    """Processes Agency execution results and updates database."""

    def __init__(self, db: DatabaseService):
        self.db = db

    def process_result(
        self, email: str, result: AgencyResult
    ) -> Dict[str, Any]:
        """Process an Agency result and persist to database.

        Args:
            email: Employee email address.
            result: AgencyResult from CLI execution.

        Returns:
            Summary dict of what was processed.
        """
        summary = {
            "email": email,
            "success": result.exit_code == 0,
            "parsed": result.parsed_ok,
            "duration": result.duration_seconds,
            "actions_count": len(result.actions_taken),
            "emails_sent": result.emails_sent,
            "teams_messages": result.teams_messages_sent,
            "calendar_actions": result.calendar_actions,
        }

        # Log activity
        self._log_activity(email, result)

        if result.exit_code != 0:
            self._record_error(email, result.error or "Unknown error")
            return summary

        if result.parsed_ok:
            # Update employee state with processed items
            self._update_employee_state(email, result)

            # Process memory updates
            self._process_memory_updates(email, result.memory_updates)

            # Update metrics
            self._update_metrics(email, result)

        return summary

    def _log_activity(self, email: str, result: AgencyResult) -> None:
        """Log the execution to activity_log table."""
        action_data = {
            "exit_code": result.exit_code,
            "duration_seconds": result.duration_seconds,
            "actions_taken": result.actions_taken,
            "emails_sent": result.emails_sent,
            "teams_messages_sent": result.teams_messages_sent,
            "calendar_actions": result.calendar_actions,
        }

        try:
            self.db.log_activity(
                agent_email=email,
                action_type="agency_execution",
                action_data=action_data,
                result="success" if result.exit_code == 0 else "error",
                error_message=result.error,
            )
        except Exception as exc:
            logger.error("Failed to log activity for %s: %s", email, exc)

    def _record_error(self, email: str, error: str) -> None:
        """Record an error in agent_state."""
        try:
            self.db.increment_error_count(email, error)
        except Exception as exc:
            logger.error(
                "Failed to record error for %s: %s", email, exc
            )

    def _update_employee_state(
        self, email: str, result: AgencyResult
    ) -> None:
        """Update employee_state with processed items and pending flags."""
        try:
            # Get existing state
            state = self.db.get_employee_state(email) or {}

            # Update processed IDs from actions
            processed_email_ids = []
            try:
                existing = json.loads(
                    state.get("processed_email_ids", "[]")
                )
                processed_email_ids = list(existing)
            except (json.JSONDecodeError, TypeError):
                pass

            for action in result.actions_taken:
                msg_id = action.get("message_id")
                if msg_id:
                    processed_email_ids.append(msg_id)

                # Store sent emails in knowledge so agent remembers what it sent
                if action.get("type") == "send_email":
                    try:
                        self.db.upsert_agent_knowledge(
                            agent_email=email,
                            knowledge_type="topic",
                            subject=f"sent:{action.get('to', '')}:{action.get('subject', '')}",
                            content=f"Sent email to {action.get('to')} about {action.get('subject')}",
                            source_type="observation",
                            confidence=1.0,
                        )
                    except Exception:
                        pass

            # Keep last 100 processed IDs
            processed_email_ids = processed_email_ids[-100:]

            # Update pending items
            pending_items = json.dumps(result.items_flagged_for_later)

            self.db.upsert_employee_state(
                email=email,
                last_check_in=datetime.now().isoformat(),
                processed_email_ids=json.dumps(processed_email_ids),
                pending_items=pending_items,
            )

        except Exception as exc:
            logger.error(
                "Failed to update employee state for %s: %s", email, exc
            )

    def _process_memory_updates(
        self, email: str, updates: List[Dict[str, Any]]
    ) -> None:
        """Process memory updates from Agency output."""
        for update in updates:
            update_type = update.get("type", "")
            subject = update.get("subject", "")
            content = update.get("content", "")

            if not subject or not content:
                continue

            try:
                if update_type == "conversation":
                    self.db.upsert_conversation_memory(
                        agent_email=email,
                        conversation_id=subject,
                        summary=content,
                    )
                elif update_type in ("knowledge", "relationship"):
                    knowledge_type = (
                        "person"
                        if update_type == "relationship"
                        else "topic"
                    )
                    self.db.upsert_agent_knowledge(
                        agent_email=email,
                        knowledge_type=knowledge_type,
                        subject=subject,
                        content=content,
                        source_type="observation",
                    )
            except Exception as exc:
                logger.error(
                    "Failed to process memory update for %s: %s",
                    email,
                    exc,
                )

    def _update_metrics(self, email: str, result: AgencyResult) -> None:
        """Update aggregated metrics for the employee."""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            self.db.update_agent_metrics(
                agent_email=email,
                metric_date=today,
                emails_sent_delta=result.emails_sent,
                tick_count_delta=1,
            )
        except Exception as exc:
            logger.error(
                "Failed to update metrics for %s: %s", email, exc
            )
