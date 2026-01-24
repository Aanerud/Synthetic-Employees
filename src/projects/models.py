"""Project and task data models."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ProjectStatus(Enum):
    """Project status states."""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskStatus(Enum):
    """Task status states."""
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Priority(Enum):
    """Priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class ProjectTask:
    """
    A task within a project.

    Attributes:
        id: Unique task identifier
        project_id: Parent project ID
        title: Task title
        description: Detailed description
        status: Current task status
        assigned_to: Email of assigned agent
        assigned_via: How the task was assigned (email, teams, direct)
        assignment_message_id: ID of the assignment message
        skill_required: Skill needed for this task
        priority: Task priority
        due_date: When the task is due
        created_at: When the task was created
        completed_at: When the task was completed
    """
    id: str
    project_id: str
    title: str
    description: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    assigned_to: Optional[str] = None
    assigned_via: Optional[str] = None
    assignment_message_id: Optional[str] = None
    skill_required: Optional[str] = None
    priority: Priority = Priority.NORMAL
    due_date: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectTask":
        """Create a ProjectTask from a dictionary."""
        status = data.get("status", "pending")
        priority = data.get("priority", "normal")

        return cls(
            id=data["id"],
            project_id=data["project_id"],
            title=data["title"],
            description=data.get("description"),
            status=TaskStatus(status) if isinstance(status, str) else status,
            assigned_to=data.get("assigned_to"),
            assigned_via=data.get("assigned_via"),
            assignment_message_id=data.get("assignment_message_id"),
            skill_required=data.get("skill_required"),
            priority=Priority(priority) if isinstance(priority, str) else priority,
            due_date=_parse_datetime(data.get("due_date")),
            created_at=_parse_datetime(data.get("created_at")) or datetime.now(),
            completed_at=_parse_datetime(data.get("completed_at")),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "assigned_to": self.assigned_to,
            "assigned_via": self.assigned_via,
            "assignment_message_id": self.assignment_message_id,
            "skill_required": self.skill_required,
            "priority": self.priority.value,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


@dataclass
class Project:
    """
    A project created from an external client request.

    Attributes:
        id: Unique project identifier
        title: Project title
        description: Project description
        status: Current project status
        owner_email: Email of the project owner (usually Key Account Manager)
        client_email: Email of the external client
        client_name: Name of the client
        source_email_id: ID of the email that created this project
        teams_team_id: Teams team ID for project channel
        teams_channel_id: Teams channel ID for project communication
        priority: Project priority
        due_date: Project due date
        created_at: When the project was created
        completed_at: When the project was completed
        tasks: List of tasks in this project
    """
    id: str
    title: str
    owner_email: str
    description: Optional[str] = None
    status: ProjectStatus = ProjectStatus.OPEN
    client_email: Optional[str] = None
    client_name: Optional[str] = None
    source_email_id: Optional[str] = None
    teams_team_id: Optional[str] = None
    teams_channel_id: Optional[str] = None
    priority: Priority = Priority.NORMAL
    due_date: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    tasks: List[ProjectTask] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
        """Create a Project from a dictionary."""
        status = data.get("status", "open")
        priority = data.get("priority", "normal")

        return cls(
            id=data["id"],
            title=data["title"],
            owner_email=data["owner_email"],
            description=data.get("description"),
            status=ProjectStatus(status) if isinstance(status, str) else status,
            client_email=data.get("client_email"),
            client_name=data.get("client_name"),
            source_email_id=data.get("source_email_id"),
            teams_team_id=data.get("teams_team_id"),
            teams_channel_id=data.get("teams_channel_id"),
            priority=Priority(priority) if isinstance(priority, str) else priority,
            due_date=_parse_datetime(data.get("due_date")),
            created_at=_parse_datetime(data.get("created_at")) or datetime.now(),
            completed_at=_parse_datetime(data.get("completed_at")),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "owner_email": self.owner_email,
            "description": self.description,
            "status": self.status.value,
            "client_email": self.client_email,
            "client_name": self.client_name,
            "source_email_id": self.source_email_id,
            "teams_team_id": self.teams_team_id,
            "teams_channel_id": self.teams_channel_id,
            "priority": self.priority.value,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @property
    def is_complete(self) -> bool:
        """Check if project is complete."""
        return self.status in (ProjectStatus.COMPLETED, ProjectStatus.CANCELLED)

    @property
    def pending_tasks(self) -> List[ProjectTask]:
        """Get tasks that are not yet completed."""
        return [t for t in self.tasks if t.status not in (TaskStatus.COMPLETED, TaskStatus.CANCELLED)]

    @property
    def completed_tasks(self) -> List[ProjectTask]:
        """Get completed tasks."""
        return [t for t in self.tasks if t.status == TaskStatus.COMPLETED]


@dataclass
class ExtractedRequirements:
    """Requirements extracted from a client email."""
    project_title: str
    project_description: str
    tasks: List[Dict[str, str]]  # [{"title": "...", "skill": "...", "description": "..."}]
    priority: Priority = Priority.NORMAL
    due_date: Optional[datetime] = None
    raw_text: Optional[str] = None


def _parse_datetime(value: Any) -> Optional[datetime]:
    """Parse a datetime from string or return None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None
    return None
