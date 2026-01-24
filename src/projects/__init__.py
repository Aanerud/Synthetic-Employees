"""Projects module for coordinating work across agents."""

from .models import Project, ProjectTask, ProjectStatus, TaskStatus
from .project_service import ProjectService

__all__ = [
    "Project",
    "ProjectTask",
    "ProjectStatus",
    "TaskStatus",
    "ProjectService",
]
