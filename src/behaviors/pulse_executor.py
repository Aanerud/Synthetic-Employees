"""Pulse Executor - executes scheduled pulse events for agents.

The PulseExecutor checks which pulses should fire based on current time,
rolls probability dice, and executes the appropriate actions.
"""

import logging
import random
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..agents.persona_loader import LoadedPersona
from ..database.db_service import DatabaseService
from .pulse import DailyRoutine, PulseEvent, PulseExecution
from .pulse_definitions import get_routine_for_role

logger = logging.getLogger(__name__)


class PulseExecutor:
    """
    Executes pulse events for an agent based on their role's daily routine.

    The executor:
    1. Gets the routine for the agent's role
    2. Finds pulses that are due for the current hour
    3. Rolls probability to determine which pulses fire
    4. Executes the actions and records results
    """

    def __init__(
        self,
        persona: LoadedPersona,
        mcp_client: Any,
        db: DatabaseService,
        llm_service: Optional[Any] = None,
    ):
        """
        Initialize the pulse executor.

        Args:
            persona: The agent's loaded persona
            mcp_client: MCP client for API calls
            db: Database service for persistence
            llm_service: Optional LLM service for intelligent responses
        """
        self.persona = persona
        self.mcp_client = mcp_client
        self.db = db
        self.llm_service = llm_service
        self.routine = get_routine_for_role(persona.role)
        self._execution_cache: Dict[str, datetime] = {}

    def execute_due_pulses(self) -> List[Dict[str, Any]]:
        """
        Execute all pulses that are due for the current time.

        Returns:
            List of execution results
        """
        results = []
        current_hour = datetime.now().hour

        # Get pulses for current hour
        due_pulses = self.routine.get_pulses_for_hour(current_hour)

        for pulse in due_pulses:
            # Check if we should execute this pulse
            last_executed = self._get_last_execution(pulse.name)

            if not pulse.should_fire(current_hour, last_executed):
                continue

            # Roll probability
            if random.random() > pulse.probability:
                logger.debug(
                    f"Pulse {pulse.name} skipped (probability roll: {pulse.probability})"
                )
                continue

            # Execute the pulse
            try:
                result = self._execute_pulse(pulse)
                self._mark_executed(pulse)
                results.append(result)
                logger.info(f"Pulse {pulse.name} executed for {self.persona.email}")
            except Exception as e:
                error_result = {
                    "pulse": pulse.name,
                    "action": pulse.action,
                    "status": "error",
                    "error": str(e),
                }
                results.append(error_result)
                logger.error(f"Pulse {pulse.name} failed: {e}")

        return results

    def _get_last_execution(self, pulse_name: str) -> Optional[datetime]:
        """Get the last execution time for a pulse from cache or database."""
        # Check cache first
        if pulse_name in self._execution_cache:
            return self._execution_cache[pulse_name]

        # Check database for recent activity
        recent_activity = self.db.get_recent_activity(
            self.persona.email, minutes=1440  # Last 24 hours
        )
        for entry in recent_activity:
            if entry.action_type == f"pulse:{pulse_name}":
                return entry.timestamp

        return None

    def _mark_executed(self, pulse: PulseEvent) -> None:
        """Mark a pulse as executed."""
        now = datetime.now()
        self._execution_cache[pulse.name] = now

        # Log to database
        self.db.log_activity(
            self.persona.email,
            f"pulse:{pulse.name}",
            action_data={"action": pulse.action, "params": pulse.params},
            result="success",
        )

    def _execute_pulse(self, pulse: PulseEvent) -> Dict[str, Any]:
        """
        Execute a single pulse event.

        Routes the pulse action to the appropriate handler method.
        """
        result = {
            "pulse": pulse.name,
            "action": pulse.action,
            "status": "success",
            "data": {},
        }

        # Route to specific action handlers
        action_handlers = {
            "check_external_emails": self._action_check_external_emails,
            "post_standup_teams": self._action_post_standup,
            "check_project_status": self._action_check_project_status,
            "check_pending_projects": self._action_check_pending_projects,
            "check_delegated_tasks": self._action_check_delegated_tasks,
            "send_client_updates": self._action_send_client_updates,
            "check_inbox": self._action_check_inbox,
            "check_inbox_assignments": self._action_check_inbox_assignments,
            "post_progress_update": self._action_post_progress_update,
            "review_content_queue": self._action_review_content_queue,
            "review_pending_content": self._action_review_pending_content,
            "distribute_assignments": self._action_distribute_assignments,
            "review_junior_work": self._action_review_junior_work,
            "process_editing_tasks": self._action_process_editing_tasks,
            "check_pull_requests": self._action_check_pull_requests,
            "respond_to_reviews": self._action_respond_to_reviews,
            "review_backlog": self._action_review_backlog,
            "coordinate_sprint": self._action_coordinate_sprint,
            "process_proofreading_queue": self._action_process_proofreading_queue,
            "post_completion_update": self._action_post_completion_update,
            "post_presence_update": self._action_post_presence_update,
        }

        handler = action_handlers.get(pulse.action)
        if handler:
            result["data"] = handler(pulse.params)
        else:
            logger.warning(f"Unknown pulse action: {pulse.action}")
            result["status"] = "skipped"
            result["data"] = {"reason": f"Unknown action: {pulse.action}"}

        return result

    # ==========================================================================
    # Action Handlers
    # ==========================================================================

    def _action_check_external_emails(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Check inbox for external client emails."""
        try:
            # Get recent unread emails
            inbox = self.mcp_client.get_inbox(
                limit=20, filter_query="isRead eq false"
            )

            external_emails = []
            domain = self.persona.email.split("@")[1]

            for email in inbox if isinstance(inbox, list) else []:
                sender = email.get("from", {}).get("emailAddress", {}).get("address", "")
                # External email = different domain
                if sender and domain not in sender.lower():
                    external_emails.append({
                        "id": email.get("id"),
                        "from": sender,
                        "subject": email.get("subject", ""),
                    })

            return {
                "checked": len(inbox) if isinstance(inbox, list) else 0,
                "external_found": len(external_emails),
                "external_emails": external_emails[:5],  # First 5
            }
        except Exception as e:
            logger.error(f"Error checking external emails: {e}")
            return {"error": str(e)}

    def _action_post_standup(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Post a standup message to Teams channel."""
        try:
            # Get teams and find the right channel
            teams = self.mcp_client.list_teams()
            if not teams:
                return {"skipped": True, "reason": "No teams found"}

            team_id = teams[0].get("id")
            channels = self.mcp_client.list_channels(team_id)

            target_channel = params.get("channel", "general").lower()
            channel_id = None

            for channel in channels if isinstance(channels, list) else []:
                if target_channel in channel.get("displayName", "").lower():
                    channel_id = channel.get("id")
                    break

            if not channel_id and channels:
                channel_id = channels[0].get("id")

            if not channel_id:
                return {"skipped": True, "reason": "No suitable channel found"}

            # Generate standup message
            message = self._generate_standup_message()

            self.mcp_client.send_channel_message(
                team_id=team_id,
                channel_id=channel_id,
                content=message,
            )

            return {
                "posted": True,
                "team_id": team_id,
                "channel_id": channel_id,
            }
        except Exception as e:
            logger.error(f"Error posting standup: {e}")
            return {"error": str(e)}

    def _generate_standup_message(self) -> str:
        """Generate a standup message for the persona."""
        greetings = ["Good morning team!", "Morning everyone!", "Hi team!"]
        greeting = random.choice(greetings)

        statuses = [
            "Reviewing inbox and planning for the day.",
            "Catching up on messages and starting on today's tasks.",
            "Online and ready to tackle today's priorities.",
        ]
        status = random.choice(statuses)

        return f"{greeting} {self.persona.name} here. {status}"

    def _action_check_project_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Check status of active projects."""
        # This will be expanded when project service is implemented
        return {"checked": True, "active_projects": 0}

    def _action_check_pending_projects(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Check for projects awaiting response."""
        return {"checked": True, "pending": 0}

    def _action_check_delegated_tasks(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Check status of delegated tasks."""
        return {"checked": True, "delegated_tasks": 0}

    def _action_send_client_updates(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send progress updates to clients."""
        return {"sent": 0}

    def _action_check_inbox(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Generic inbox check."""
        try:
            inbox = self.mcp_client.get_inbox(
                limit=10, filter_query="isRead eq false"
            )
            return {
                "unread_count": len(inbox) if isinstance(inbox, list) else 0,
            }
        except Exception as e:
            return {"error": str(e)}

    def _action_check_inbox_assignments(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Check inbox for work assignments."""
        try:
            inbox = self.mcp_client.get_inbox(limit=10)
            assignments = []

            for email in inbox if isinstance(inbox, list) else []:
                subject = email.get("subject", "").lower()
                if any(kw in subject for kw in ["assign", "task", "review", "request"]):
                    assignments.append({
                        "id": email.get("id"),
                        "subject": email.get("subject"),
                    })

            return {"assignments_found": len(assignments)}
        except Exception as e:
            return {"error": str(e)}

    def _action_post_progress_update(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Post a progress update to Teams."""
        # Similar to standup but more focused on work progress
        return self._action_post_standup(params)

    def _action_review_content_queue(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Review the content queue (editorial role)."""
        return {"reviewed": True}

    def _action_review_pending_content(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Review pending content for quality."""
        return {"reviewed": 0}

    def _action_distribute_assignments(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Distribute work assignments to team."""
        return {"distributed": 0}

    def _action_review_junior_work(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Review work from junior team members."""
        return {"reviewed": 0}

    def _action_process_editing_tasks(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Process editing tasks in queue."""
        return {"processed": 0}

    def _action_check_pull_requests(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Check for pending pull request reviews."""
        return {"pending_reviews": 0}

    def _action_respond_to_reviews(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Respond to code review comments."""
        return {"responded": 0}

    def _action_review_backlog(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Review product backlog."""
        return {"reviewed": True}

    def _action_coordinate_sprint(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Coordinate sprint activities."""
        return {"coordinated": True}

    def _action_process_proofreading_queue(
        self, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process proofreading tasks."""
        return {"processed": 0}

    def _action_post_completion_update(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Post update about completed work."""
        return self._action_post_standup(params)

    def _action_post_presence_update(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Post a presence/availability update."""
        try:
            teams = self.mcp_client.list_teams()
            if not teams:
                return {"skipped": True}

            team_id = teams[0].get("id")
            channels = self.mcp_client.list_channels(team_id)

            if not channels:
                return {"skipped": True}

            channel_id = channels[0].get("id")

            presence_messages = [
                f"{self.persona.name} is online and available.",
                f"Hi team, {self.persona.name} here - let me know if you need anything!",
            ]

            self.mcp_client.send_channel_message(
                team_id=team_id,
                channel_id=channel_id,
                content=random.choice(presence_messages),
            )

            return {"posted": True}
        except Exception as e:
            return {"error": str(e)}
