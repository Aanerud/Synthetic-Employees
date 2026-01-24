"""Key Account Manager Workflow - handles external client requests.

The KAM workflow detects external client emails, extracts requirements,
creates projects, and delegates tasks to appropriate team members.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from ..agents.persona_loader import LoadedPersona, PersonaRegistry
from ..database.db_service import DatabaseService
from ..projects.models import ExtractedRequirements, Priority, Project
from ..projects.project_service import ProjectService

logger = logging.getLogger(__name__)


class KeyAccountManagerWorkflow:
    """
    Workflow for Key Account Managers handling external client requests.

    Flow:
    1. Detect if email is an external client request
    2. Extract requirements using LLM
    3. Create project and tasks
    4. Delegate tasks to team members
    5. Send acknowledgment to client
    """

    def __init__(
        self,
        persona: LoadedPersona,
        mcp_client: Any,
        db: DatabaseService,
        persona_registry: PersonaRegistry,
        llm_service: Optional[Any] = None,
    ):
        """
        Initialize the KAM workflow.

        Args:
            persona: The KAM persona
            mcp_client: MCP client for API calls
            db: Database service
            persona_registry: Registry of personas for task delegation
            llm_service: Optional LLM service for intelligent extraction
        """
        self.persona = persona
        self.mcp_client = mcp_client
        self.db = db
        self.persona_registry = persona_registry
        self.llm_service = llm_service
        self.project_service = ProjectService(db, persona_registry, mcp_client)

    def is_external_email(self, email_data: Dict[str, Any]) -> bool:
        """
        Check if an email is from an external sender.

        External = different domain than the agent's email.
        """
        sender = email_data.get("from", {})
        if "emailAddress" in sender:
            sender_email = sender.get("emailAddress", {}).get("address", "")
        else:
            sender_email = sender.get("email", "")

        if not sender_email:
            return False

        agent_domain = self.persona.email.split("@")[1].lower()
        sender_domain = sender_email.split("@")[1].lower() if "@" in sender_email else ""

        return sender_domain != agent_domain

    def is_client_request(self, email_data: Dict[str, Any]) -> bool:
        """
        Determine if an email is a client request that needs project creation.

        Uses heuristics to identify project-worthy requests.
        """
        if not self.is_external_email(email_data):
            return False

        subject = email_data.get("subject", "").lower()
        body_preview = email_data.get("bodyPreview", "").lower()
        full_text = f"{subject} {body_preview}"

        # Request indicators
        request_keywords = [
            "request", "need", "require", "want", "looking for",
            "help with", "assistance", "project", "proposal",
            "quote", "estimate", "review", "edit", "translate",
            "content", "copy", "document", "deliverable",
        ]

        # Check for request indicators
        for keyword in request_keywords:
            if keyword in full_text:
                return True

        # Check for question marks (indicates inquiry)
        if "?" in full_text:
            return True

        return False

    def process_external_email(self, email_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process an external client email.

        If it's a client request:
        1. Extract requirements
        2. Create project
        3. Delegate tasks
        4. Send acknowledgment

        Returns:
            Result dict with project info and actions taken
        """
        result = {
            "email_id": email_data.get("id"),
            "is_external": self.is_external_email(email_data),
            "is_client_request": False,
            "project_created": False,
            "tasks_delegated": 0,
            "acknowledgment_sent": False,
        }

        if not result["is_external"]:
            return result

        result["is_client_request"] = self.is_client_request(email_data)

        if not result["is_client_request"]:
            return result

        # Extract requirements
        requirements = self._extract_requirements(email_data)
        if not requirements:
            result["error"] = "Could not extract requirements"
            return result

        # Create project
        try:
            project = self.project_service.create_project_from_email(
                email_data=email_data,
                owner_email=self.persona.email,
                requirements=requirements,
            )
            result["project_created"] = True
            result["project_id"] = project.id
            result["project_title"] = project.title
        except Exception as e:
            result["error"] = f"Failed to create project: {e}"
            logger.error(f"Project creation failed: {e}")
            return result

        # Setup Teams channel for project (if available)
        try:
            self._setup_project_channel(project)
        except Exception as e:
            logger.warning(f"Could not setup Teams channel: {e}")

        # Delegate tasks
        try:
            delegation_result = self.project_service.delegate_project_tasks(project)
            result["tasks_delegated"] = delegation_result["tasks_delegated"]
            result["delegation_details"] = delegation_result
        except Exception as e:
            logger.error(f"Task delegation failed: {e}")

        # Send acknowledgment to client
        try:
            self._send_client_acknowledgment(email_data, project)
            result["acknowledgment_sent"] = True
        except Exception as e:
            logger.error(f"Failed to send acknowledgment: {e}")

        # Log the activity
        self.db.log_activity(
            self.persona.email,
            "kam_project_created",
            action_data=result,
            result="success",
        )

        return result

    def _extract_requirements(
        self, email_data: Dict[str, Any]
    ) -> Optional[ExtractedRequirements]:
        """
        Extract project requirements from email.

        Uses LLM if available, otherwise falls back to heuristics.
        """
        subject = email_data.get("subject", "")
        body = email_data.get("body", {}).get("content", "")
        body_preview = email_data.get("bodyPreview", "")

        # Use body preview if full body not available
        if not body:
            body = body_preview

        # Strip HTML if present
        body = re.sub(r"<[^>]+>", " ", body)
        body = re.sub(r"\s+", " ", body).strip()

        # Try LLM extraction
        if self.llm_service:
            try:
                return self._extract_with_llm(subject, body)
            except Exception as e:
                logger.warning(f"LLM extraction failed, using heuristics: {e}")

        # Fallback to heuristic extraction
        return self._extract_with_heuristics(subject, body)

    def _extract_with_llm(
        self, subject: str, body: str
    ) -> Optional[ExtractedRequirements]:
        """Extract requirements using LLM."""
        prompt = f"""Analyze this client email and extract project requirements.

Subject: {subject}

Body:
{body[:2000]}

Extract:
1. A clear project title (short, descriptive)
2. Project description (1-2 sentences)
3. Individual tasks needed (with skill requirements if apparent)
4. Priority level (low, normal, high, urgent)
5. Any mentioned deadlines

Respond in this exact format:
TITLE: [project title]
DESCRIPTION: [description]
TASKS:
- [task 1 title] | [skill needed]
- [task 2 title] | [skill needed]
PRIORITY: [low/normal/high/urgent]
DUE: [date if mentioned, or "none"]
"""

        response = self.llm_service.generate(prompt)
        return self._parse_llm_response(response, body)

    def _parse_llm_response(
        self, response: str, raw_text: str
    ) -> Optional[ExtractedRequirements]:
        """Parse LLM response into ExtractedRequirements."""
        lines = response.strip().split("\n")
        title = ""
        description = ""
        tasks = []
        priority = Priority.NORMAL
        due_date = None

        for line in lines:
            line = line.strip()
            if line.startswith("TITLE:"):
                title = line[6:].strip()
            elif line.startswith("DESCRIPTION:"):
                description = line[12:].strip()
            elif line.startswith("- "):
                parts = line[2:].split("|")
                task_title = parts[0].strip()
                skill = parts[1].strip() if len(parts) > 1 else "general"
                tasks.append({"title": task_title, "skill": skill})
            elif line.startswith("PRIORITY:"):
                priority_str = line[9:].strip().lower()
                try:
                    priority = Priority(priority_str)
                except ValueError:
                    priority = Priority.NORMAL

        if not title:
            return None

        return ExtractedRequirements(
            project_title=title,
            project_description=description,
            tasks=tasks or [{"title": "Review request", "skill": "general"}],
            priority=priority,
            due_date=due_date,
            raw_text=raw_text,
        )

    def _clean_task_title(self, raw: str, max_len: int = 80) -> str:
        """
        Clean up a raw sentence into a proper task title.

        - Removes common prefixes like "We need", "Please", "Could you"
        - Truncates at max_len, preserving word boundaries
        - Capitalizes first letter
        """
        # Common prefixes to remove for cleaner task titles
        prefixes_to_remove = [
            r"^we\s+(need\s+to|are\s+preparing|would\s+like\s+to|want\s+to)\s+",
            r"^please\s+(help\s+us\s+)?(to\s+)?",
            r"^could\s+you\s+(please\s+)?(help\s+us\s+)?(to\s+)?",
            r"^i\s+(need|want|would\s+like)\s+(you\s+to\s+)?",
            r"^we'd\s+(also\s+)?appreciate\s+if\s+(you|your\s+team)\s+(could|would)\s+",
            r"^it\s+would\s+be\s+great\s+if\s+(you|your\s+team)\s+(could|would)\s+",
        ]

        cleaned = raw.strip()

        # Remove common prefixes (case-insensitive)
        for prefix in prefixes_to_remove:
            cleaned = re.sub(prefix, "", cleaned, flags=re.IGNORECASE)

        # Strip leading/trailing whitespace and punctuation
        cleaned = cleaned.strip(" ,;:-")

        # Capitalize first letter
        if cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:] if len(cleaned) > 1 else cleaned.upper()

        # Truncate at word boundary if too long
        if len(cleaned) > max_len:
            truncated = cleaned[:max_len]
            # Find last space to avoid cutting words
            last_space = truncated.rfind(" ")
            if last_space > max_len * 0.6:  # Only use space if it's not too far back
                truncated = truncated[:last_space]
            cleaned = truncated.rstrip(" ,;:-") + "..."

        return cleaned if cleaned else "Process request"

    def _extract_with_heuristics(
        self, subject: str, body: str
    ) -> ExtractedRequirements:
        """Extract requirements using simple heuristics."""
        # Use subject as title, clean it up
        title = subject
        for prefix in ["Re:", "Fw:", "Fwd:", "RE:", "FW:"]:
            title = title.replace(prefix, "").strip()

        if not title:
            title = "Client Request"

        # Extract description from first paragraph
        paragraphs = body.split("\n\n")
        description = paragraphs[0][:200] if paragraphs else body[:200]

        # Try to identify tasks from body
        tasks = []
        seen_task_titles = set()  # Track to avoid duplicate/overlapping tasks
        task_indicators = ["need", "want", "require", "please", "could you", "appreciate"]

        sentences = re.split(r"[.!?]", body)
        for sentence in sentences:
            sentence_lower = sentence.lower().strip()
            for indicator in task_indicators:
                if indicator in sentence_lower and len(sentence.strip()) > 20:
                    # Clean up the task title
                    task_title = self._clean_task_title(sentence.strip())

                    # Skip if we've already captured a similar task
                    title_key = task_title[:30].lower()
                    if title_key in seen_task_titles:
                        break
                    seen_task_titles.add(title_key)

                    # Determine skill needed based on keywords
                    skill = "general"
                    if any(w in sentence_lower for w in ["edit", "review", "final"]):
                        skill = "editing"
                    elif any(w in sentence_lower for w in ["proof", "proofread", "check"]):
                        skill = "proofreading"
                    elif any(w in sentence_lower for w in ["write", "copy", "content", "create", "marketing", "flyer"]):
                        skill = "writing"
                    elif any(w in sentence_lower for w in ["translate", "translation"]):
                        skill = "translation"
                    elif any(w in sentence_lower for w in ["design", "visual", "graphic"]):
                        skill = "design"
                    elif any(w in sentence_lower for w in ["research", "find", "search"]):
                        skill = "research"

                    tasks.append({
                        "title": task_title,
                        "skill": skill,
                    })
                    break

        # If no tasks found, create a generic one
        if not tasks:
            tasks = [{"title": f"Process request: {title}", "skill": "general"}]

        # Determine priority
        priority = Priority.NORMAL
        body_lower = body.lower()
        if any(w in body_lower for w in ["urgent", "asap", "immediately", "critical"]):
            priority = Priority.URGENT
        elif any(w in body_lower for w in ["important", "priority", "soon"]):
            priority = Priority.HIGH

        return ExtractedRequirements(
            project_title=title,
            project_description=description,
            tasks=tasks[:5],  # Max 5 tasks
            priority=priority,
            raw_text=body,
        )

    def _setup_project_channel(self, project: Project) -> None:
        """
        Setup a Teams channel for project communication.

        Note: Creating channels requires admin permissions.
        For now, we'll use an existing channel.
        """
        try:
            teams = self.mcp_client.list_teams()
            if not teams:
                return

            team_id = teams[0].get("id")
            channels = self.mcp_client.list_channels(team_id)

            if not channels:
                return

            # Find or use general channel
            channel_id = None
            for channel in channels:
                if "general" in channel.get("displayName", "").lower():
                    channel_id = channel.get("id")
                    break

            if not channel_id:
                channel_id = channels[0].get("id")

            # Update project with channel info
            self.db.update_project_teams_info(project.id, team_id, channel_id)

            # Post project announcement
            message = (
                f"**New Project Created**\n\n"
                f"**{project.title}**\n"
                f"Client: {project.client_name or project.client_email or 'External'}\n"
                f"Priority: {project.priority.value.title()}\n\n"
                f"{project.description or ''}\n\n"
                f"Tasks will be assigned shortly. Please watch for your assignment."
            )

            self.mcp_client.send_channel_message(
                team_id=team_id,
                channel_id=channel_id,
                content=message,
            )

        except Exception as e:
            logger.warning(f"Teams channel setup failed: {e}")

    def _send_client_acknowledgment(
        self, email_data: Dict[str, Any], project: Project
    ) -> None:
        """Send acknowledgment email to the client."""
        sender = email_data.get("from", {})
        if "emailAddress" in sender:
            client_name = sender.get("emailAddress", {}).get("name", "")
            if not client_name:
                client_name = sender.get("emailAddress", {}).get("address", "").split("@")[0]
        else:
            client_name = sender.get("name", sender.get("email", "").split("@")[0])

        # Reply to the original email
        body = f"""Dear {client_name},

Thank you for reaching out. I've received your request and have created a project to track it.

**Project Reference:** {project.id}
**Title:** {project.title}

Our team has been notified and will begin working on this shortly. I'll keep you updated on our progress.

If you have any questions or additional information to share, please don't hesitate to reply to this email.

Best regards,
{self.persona.name}
{self.persona.job_title}"""

        self.mcp_client.reply_to_mail(
            message_id=email_data["id"],
            body=body,
        )

    def check_project_status(self) -> List[Dict[str, Any]]:
        """
        Check status of all active projects owned by this KAM.

        Returns summary of each project's status.
        """
        projects = self.project_service.get_projects_for_owner(self.persona.email)

        statuses = []
        for project in projects:
            total_tasks = len(project.tasks)
            completed_tasks = len(project.completed_tasks)
            pending_tasks = len(project.pending_tasks)

            statuses.append({
                "project_id": project.id,
                "title": project.title,
                "status": project.status.value,
                "client": project.client_name or project.client_email,
                "total_tasks": total_tasks,
                "completed_tasks": completed_tasks,
                "pending_tasks": pending_tasks,
                "progress_percent": (
                    int(completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
                ),
            })

        return statuses

    def send_project_update_to_client(self, project: Project) -> bool:
        """
        Send a progress update to the client for a project.
        """
        if not project.client_email:
            return False

        total = len(project.tasks)
        completed = len(project.completed_tasks)
        progress = int(completed / total * 100) if total > 0 else 0

        subject = f"Project Update: {project.title} [{progress}% Complete]"
        body = f"""Dear {project.client_name or 'Valued Client'},

I wanted to provide you with an update on your project.

**Project:** {project.title}
**Status:** {project.status.value.replace('_', ' ').title()}
**Progress:** {completed}/{total} tasks completed ({progress}%)

"""
        if project.pending_tasks:
            body += "**Remaining Tasks:**\n"
            for task in project.pending_tasks[:5]:
                status = task.status.value.replace("_", " ").title()
                body += f"- {task.title} ({status})\n"
            if len(project.pending_tasks) > 5:
                body += f"- ... and {len(project.pending_tasks) - 5} more\n"

        body += f"""
We're working diligently to complete everything. Please let me know if you have any questions.

Best regards,
{self.persona.name}
{self.persona.job_title}"""

        try:
            self.mcp_client.send_mail(
                to=project.client_email,
                subject=subject,
                body=body,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send project update: {e}")
            return False
