"""Project Service - manages project lifecycle and task coordination."""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..agents.persona_loader import LoadedPersona, PersonaRegistry
from ..database.db_service import DatabaseService
from .models import (
    ExtractedRequirements,
    Priority,
    Project,
    ProjectStatus,
    ProjectTask,
    TaskStatus,
)

# Import communication channel selection
try:
    from ..behaviors.communication_channel import (
        CommunicationChannel,
        CommunicationChannelSelector,
        MessageContext,
        MessageType,
        MessageTemplates,
        decide_communication_channel,
    )
    CHANNEL_SELECTION_AVAILABLE = True
except ImportError:
    CHANNEL_SELECTION_AVAILABLE = False

logger = logging.getLogger(__name__)


class ProjectService:
    """
    Service for managing projects and coordinating tasks.

    Handles:
    - Creating projects from client emails
    - Breaking down requirements into tasks
    - Finding appropriate agents for tasks
    - Assigning tasks via email or Teams
    - Tracking project progress
    """

    def __init__(
        self,
        db: DatabaseService,
        persona_registry: PersonaRegistry,
        mcp_client: Optional[Any] = None,
    ):
        """
        Initialize the project service.

        Args:
            db: Database service for persistence
            persona_registry: Registry of available personas
            mcp_client: Optional MCP client for sending messages
        """
        self.db = db
        self.persona_registry = persona_registry
        self.mcp_client = mcp_client

    def create_project_from_email(
        self,
        email_data: Dict[str, Any],
        owner_email: str,
        requirements: ExtractedRequirements,
    ) -> Project:
        """
        Create a new project from an external client email.

        Args:
            email_data: The email data that triggered this project
            owner_email: Email of the project owner (Key Account Manager)
            requirements: Extracted requirements from the email

        Returns:
            The created Project
        """
        project_id = str(uuid.uuid4())[:8]

        # Extract client info
        sender = email_data.get("from", {})
        if "emailAddress" in sender:
            client_email = sender.get("emailAddress", {}).get("address")
            client_name = sender.get("emailAddress", {}).get("name")
        else:
            client_email = sender.get("email")
            client_name = sender.get("name")

        # Create project in database
        self.db.create_project(
            project_id=project_id,
            title=requirements.project_title,
            owner_email=owner_email,
            description=requirements.project_description,
            client_email=client_email,
            client_name=client_name,
            source_email_id=email_data.get("id"),
            priority=requirements.priority.value,
            due_date=requirements.due_date,
        )

        # Create tasks from requirements
        for task_def in requirements.tasks:
            task_id = str(uuid.uuid4())[:8]
            self.db.create_project_task(
                task_id=task_id,
                project_id=project_id,
                title=task_def.get("title", "Untitled Task"),
                description=task_def.get("description"),
                skill_required=task_def.get("skill"),
                priority=requirements.priority.value,
            )

        # Load and return the full project
        return self.get_project(project_id)

    def get_project(self, project_id: str) -> Optional[Project]:
        """Get a project with all its tasks."""
        project_data = self.db.get_project(project_id)
        if not project_data:
            return None

        project = Project.from_dict(project_data)

        # Load tasks
        tasks_data = self.db.get_tasks_for_project(project_id)
        project.tasks = [ProjectTask.from_dict(t) for t in tasks_data]

        return project

    def get_projects_for_owner(
        self, owner_email: str, include_completed: bool = False
    ) -> List[Project]:
        """Get all projects owned by an agent."""
        if include_completed:
            projects_data = self.db.get_projects_by_owner(owner_email)
        else:
            projects_data = self.db.get_projects_by_owner(owner_email, status="open")
            projects_data.extend(
                self.db.get_projects_by_owner(owner_email, status="in_progress")
            )

        projects = []
        for data in projects_data:
            project = Project.from_dict(data)
            tasks_data = self.db.get_tasks_for_project(project.id)
            project.tasks = [ProjectTask.from_dict(t) for t in tasks_data]
            projects.append(project)

        return projects

    def find_agent_for_skill(self, skill: str) -> Optional[LoadedPersona]:
        """
        Find an available agent with the required skill.

        Args:
            skill: The skill required for the task

        Returns:
            A LoadedPersona if found, None otherwise
        """
        skill_lower = skill.lower()

        # Map skills to likely roles/departments
        skill_role_mapping = {
            "editing": ["editor", "senior editor", "editorial"],
            "proofreading": ["proofreader", "editor"],
            "writing": ["writer", "editor", "copywriter"],
            "review": ["editor", "senior editor", "reviewer"],
            "translation": ["translator", "editor"],
            "development": ["developer", "senior developer", "engineer"],
            "design": ["designer", "ux designer"],
            "marketing": ["marketing", "content"],
            "legal": ["legal", "compliance"],
        }

        # Find matching roles for the skill
        target_roles = []
        for skill_key, roles in skill_role_mapping.items():
            if skill_key in skill_lower or skill_lower in skill_key:
                target_roles.extend(roles)

        # If no specific mapping, use the skill as the role
        if not target_roles:
            target_roles = [skill_lower]

        # Search for personas with matching roles
        all_personas = self.persona_registry.list_all()

        for persona in all_personas:
            role_lower = persona.role.lower()
            for target in target_roles:
                if target in role_lower:
                    # Check if this agent is not overloaded
                    tasks = self.db.get_tasks_assigned_to(persona.email, status="assigned")
                    tasks.extend(
                        self.db.get_tasks_assigned_to(persona.email, status="in_progress")
                    )
                    if len(tasks) < 5:  # Max 5 concurrent tasks
                        return persona

        return None

    def assign_task(
        self,
        task: ProjectTask,
        assignee: LoadedPersona,
        via: str = "auto",
    ) -> bool:
        """
        Assign a task to an agent.

        Args:
            task: The task to assign
            assignee: The persona to assign to
            via: How to notify - 'auto' uses intelligent selection,
                 or specify 'email', 'teams', 'direct'

        Returns:
            True if successful
        """
        # Get project for context
        project = self.get_project(task.project_id)
        if not project:
            return False

        # Intelligently select communication channel if 'auto'
        actual_via = via
        if via == "auto" and CHANNEL_SELECTION_AVAILABLE:
            decision = self._select_assignment_channel(task, assignee, project)
            actual_via = decision.channel.value if decision.channel == CommunicationChannel.EMAIL else "teams"
            logger.info(
                f"Channel decision for task {task.id}: {actual_via} - {decision.reason}"
            )
        elif via == "auto":
            actual_via = "email"  # Fallback if channel selection not available

        # Update database
        self.db.assign_task(
            task_id=task.id,
            assignee_email=assignee.email,
            assigned_via=actual_via,
        )

        # Sync in-memory object to prevent stale data issues
        # (e.g., when assigning multiple tasks in a loop)
        task.assigned_to = assignee.email
        task.status = TaskStatus.ASSIGNED

        # Send notification based on method
        if self.mcp_client:
            try:
                if actual_via == "email":
                    self._notify_via_email(task, assignee, project)
                    # Also send a quick Teams heads-up if channel available
                    self._send_teams_heads_up(task, assignee, project)
                elif actual_via == "teams":
                    self._notify_via_teams(task, assignee, project)
            except Exception as e:
                logger.error(f"Failed to send assignment notification: {e}")
                # Assignment still happened in DB, just notification failed

        logger.info(f"Assigned task {task.id} to {assignee.email} via {actual_via}")
        return True

    def _select_assignment_channel(
        self,
        task: ProjectTask,
        assignee: LoadedPersona,
        project: Project,
    ):
        """Select the appropriate channel for task assignment."""
        # Build description to estimate content length
        desc_length = len(task.title) + len(task.description or "") + len(project.description or "")

        context = MessageContext(
            message_type=MessageType.FORMAL_ASSIGNMENT,
            content_length=desc_length,
            is_external_recipient=False,  # Internal assignment
            project_context=True,
            requires_tracking=True,  # Task assignments need tracking
        )

        selector = CommunicationChannelSelector()
        return selector.select_channel(context)

    def _send_teams_heads_up(
        self, task: ProjectTask, assignee: LoadedPersona, project: Project
    ) -> None:
        """Send a quick Teams notification about the assignment (in addition to email)."""
        try:
            if not project.teams_team_id or not project.teams_channel_id:
                return

            # Brief heads-up in channel
            message = f"@{assignee.name} - heads up, just sent you a task assignment for **{task.title}**. Check your email for details!"

            self.mcp_client.send_channel_message(
                team_id=project.teams_team_id,
                channel_id=project.teams_channel_id,
                content=message,
            )
        except Exception as e:
            # Non-critical, just log and continue
            logger.debug(f"Could not send Teams heads-up: {e}")

    def _notify_via_email(
        self, task: ProjectTask, assignee: LoadedPersona, project: Project
    ) -> None:
        """Send assignment notification via email."""
        subject = f"Task Assignment: {task.title} [Project: {project.title}]"
        body = f"""Hi {assignee.name},

You have been assigned a new task for the project "{project.title}":

Task: {task.title}
{f"Description: {task.description}" if task.description else ""}
Priority: {task.priority.value.title()}
{f"Due Date: {task.due_date.strftime('%Y-%m-%d')}" if task.due_date else ""}

Project Background:
{project.description or "No additional details."}

Client: {project.client_name or project.client_email or "Internal"}

Please review and begin work when ready. Update your status in the project channel.

Best regards,
Project Coordination System"""

        self.mcp_client.send_mail(
            to=assignee.email,
            subject=subject,
            body=body,
        )

    def _notify_via_teams(
        self, task: ProjectTask, assignee: LoadedPersona, project: Project
    ) -> None:
        """Send assignment notification via Teams."""
        if project.teams_team_id and project.teams_channel_id:
            message = (
                f"**New Task Assignment**\n\n"
                f"@{assignee.name} has been assigned: **{task.title}**\n\n"
                f"Priority: {task.priority.value.title()}\n"
                f"{task.description or ''}"
            )

            self.mcp_client.send_channel_message(
                team_id=project.teams_team_id,
                channel_id=project.teams_channel_id,
                content=message,
            )

    def update_task_status(
        self, task_id: str, status: TaskStatus, notify: bool = True
    ) -> bool:
        """
        Update a task's status.

        Args:
            task_id: The task ID
            status: New status
            notify: Whether to send notifications

        Returns:
            True if successful
        """
        task_data = self.db.get_project_task(task_id)
        if not task_data:
            return False

        completed_at = datetime.now() if status == TaskStatus.COMPLETED else None
        self.db.update_task_status(task_id, status.value, completed_at)

        # Check if all tasks complete -> update project status
        if status == TaskStatus.COMPLETED:
            project = self.get_project(task_data["project_id"])
            if project and all(t.status == TaskStatus.COMPLETED for t in project.tasks):
                self.update_project_status(project.id, ProjectStatus.REVIEW)

        return True

    def update_project_status(
        self, project_id: str, status: ProjectStatus
    ) -> bool:
        """Update a project's status."""
        completed_at = datetime.now() if status == ProjectStatus.COMPLETED else None
        self.db.update_project_status(project_id, status.value, completed_at)
        return True

    def add_comment(
        self,
        project_id: str,
        author_email: str,
        content: str,
        task_id: Optional[str] = None,
        source: str = "internal",
    ) -> int:
        """Add a comment to a project."""
        return self.db.add_project_comment(
            project_id=project_id,
            author_email=author_email,
            content=content,
            task_id=task_id,
            source=source,
        )

    def delegate_project_tasks(self, project: Project) -> Dict[str, Any]:
        """
        Automatically delegate all pending tasks in a project.

        Finds appropriate agents for each task and assigns them.
        Uses intelligent channel selection (email for detailed assignments,
        with Teams heads-up for visibility).

        Returns:
            Summary of delegation results
        """
        results = {
            "project_id": project.id,
            "tasks_delegated": 0,
            "tasks_failed": 0,
            "assignments": [],
        }

        for task in project.tasks:
            if task.status != TaskStatus.PENDING:
                continue

            # Find agent for this task
            skill = task.skill_required or "general"
            agent = self.find_agent_for_skill(skill)

            if agent:
                # Use 'auto' for intelligent channel selection
                success = self.assign_task(task, agent, via="auto")
                if success:
                    results["tasks_delegated"] += 1
                    results["assignments"].append({
                        "task_id": task.id,
                        "task_title": task.title,
                        "assigned_to": agent.email,
                        "via": "auto",  # Indicates intelligent selection was used
                    })
                else:
                    results["tasks_failed"] += 1
            else:
                results["tasks_failed"] += 1
                logger.warning(
                    f"Could not find agent for task {task.id} requiring skill: {skill}"
                )

        # Update project status if tasks were delegated
        if results["tasks_delegated"] > 0:
            self.update_project_status(project.id, ProjectStatus.IN_PROGRESS)

        return results

    def send_progress_update(
        self,
        project: Project,
        author_email: str,
        author_name: str,
        message: str,
        task_id: Optional[str] = None,
        channel: str = "auto",
    ) -> Dict[str, Any]:
        """
        Send a progress update using intelligent channel selection.

        Short updates go via Teams, detailed updates via email.

        Args:
            project: The project
            author_email: Who is sending the update
            author_name: Display name
            message: The update message
            task_id: Optional specific task reference
            channel: 'auto', 'email', or 'teams'

        Returns:
            Result with channel used and success status
        """
        result = {
            "channel_used": None,
            "success": False,
            "email_sent": False,
            "teams_sent": False,
        }

        if not self.mcp_client:
            return result

        # Select channel
        selected_channel = channel
        if channel == "auto" and CHANNEL_SELECTION_AVAILABLE:
            decision = decide_communication_channel(
                message_type=MessageType.STATUS_UPDATE,
                content_length=len(message),
                is_external=False,
            )
            selected_channel = "teams" if decision.channel in (
                CommunicationChannel.TEAMS_CHAT,
                CommunicationChannel.TEAMS_CHANNEL,
            ) else "email"
            logger.info(f"Progress update channel: {selected_channel} - {decision.reason}")
        elif channel == "auto":
            # Fallback: short messages to Teams, long to email
            selected_channel = "teams" if len(message) < 300 else "email"

        result["channel_used"] = selected_channel

        try:
            if selected_channel == "teams":
                # Try Teams channel first
                if project.teams_team_id and project.teams_channel_id:
                    teams_message = f"**Update from {author_name}**\n{message}"
                    self.mcp_client.send_channel_message(
                        team_id=project.teams_team_id,
                        channel_id=project.teams_channel_id,
                        content=teams_message,
                    )
                    result["teams_sent"] = True
                    result["success"] = True
                else:
                    # Fall back to email if no Teams channel
                    selected_channel = "email"
                    result["channel_used"] = "email (Teams unavailable)"

            if selected_channel == "email":
                # Send to project owner
                subject = f"Project Update: {project.title}"
                if task_id:
                    task = self.db.get_project_task(task_id)
                    if task:
                        subject = f"Task Update: {task['title']} [Project: {project.title}]"

                body = f"""Project: {project.title}

Update from {author_name}:

{message}

---
This is an automated project update."""

                self.mcp_client.send_mail(
                    to=project.owner_email,
                    subject=subject,
                    body=body,
                )
                result["email_sent"] = True
                result["success"] = True

        except Exception as e:
            logger.error(f"Failed to send progress update: {e}")
            result["error"] = str(e)

        # Log the comment in database regardless of channel
        self.add_comment(
            project_id=project.id,
            author_email=author_email,
            content=message,
            task_id=task_id,
            source=selected_channel,
        )

        return result

    def send_quick_ack(
        self,
        recipient_email: str,
        sender_name: str,
        task_title: str,
        project: Project,
    ) -> bool:
        """
        Send a quick acknowledgment - perfect for Teams.

        Example: "Got it! Starting work on the marketing flyer now."

        Args:
            recipient_email: Who to notify
            sender_name: Who is acknowledging
            task_title: What task
            project: The project context

        Returns:
            True if sent successfully
        """
        if not self.mcp_client:
            return False

        # Always prefer Teams for quick acks
        try:
            if project.teams_team_id and project.teams_channel_id:
                # Use Teams channel
                if CHANNEL_SELECTION_AVAILABLE:
                    message = MessageTemplates.teams_acknowledgment(
                        sender_name="",  # We'll use our own format
                        task_ref=task_title,
                    )
                else:
                    message = f"Got it! Starting on {task_title} now."

                self.mcp_client.send_channel_message(
                    team_id=project.teams_team_id,
                    channel_id=project.teams_channel_id,
                    content=f"@{sender_name}: {message}",
                )
                return True
            else:
                # Fall back to brief email
                self.mcp_client.send_mail(
                    to=recipient_email,
                    subject=f"Re: {task_title}",
                    body=f"Got it, thanks! I'll start on this right away.\n\nBest,\n{sender_name}",
                )
                return True
        except Exception as e:
            logger.error(f"Failed to send quick ack: {e}")
            return False
