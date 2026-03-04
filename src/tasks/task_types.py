"""Task type definitions and instructions for employee wake-up cycles."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TaskType(Enum):
    """Types of tasks an employee can perform during a wake-up cycle."""

    MORNING_ROUTINE = "morning_routine"
    CHECK_INBOX = "check_inbox"
    CHECK_TEAMS = "check_teams"
    CHECK_CALENDAR = "check_calendar"
    PROACTIVE_WORK = "proactive_work"
    RESPOND_TO_PENDING = "respond_to_pending"
    END_OF_DAY = "end_of_day"


@dataclass
class Task:
    """A task to be performed by an employee."""

    task_type: TaskType
    instructions: str
    priority: int = 5  # 1=highest, 9=lowest
    pulse_name: Optional[str] = None  # If triggered by a pulse event


# Base task instructions per type
TASK_INSTRUCTIONS = {
    TaskType.MORNING_ROUTINE: """This is your first check-in of the day. Do the following in order:
1. Check your inbox for urgent or important emails. Respond to anything marked urgent or from your manager.
2. Check your calendar for today's meetings. Accept or decline any pending meeting invites.
3. Check Teams for any unread messages that need quick responses.
4. Note any items that need follow-up later today.

Focus on getting oriented for the day. Be efficient but thorough.""",
    TaskType.CHECK_INBOX: """Check your email inbox for new messages.
1. Read any unread emails.
2. Respond to emails that need a quick reply (under 5 minutes to compose).
3. Flag complex emails that need more thought for a later cycle.
4. Mark read emails as read.

Prioritize: manager emails > client emails > team emails > FYI/newsletters.""",
    TaskType.CHECK_TEAMS: """Check your Teams messages for unread conversations.
1. Read any unread messages in your chats and channels.
2. Respond to quick questions and acknowledgments.
3. React to messages where appropriate (thumbs up, etc.).
4. Flag conversations needing detailed responses for later.

Keep Teams responses brief and conversational.""",
    TaskType.CHECK_CALENDAR: """Review your calendar for upcoming events.
1. Check for any new meeting invites and respond (accept/decline/tentative).
2. Review tomorrow's schedule for conflicts.
3. If you have a meeting in the next hour, prepare mentally.

Consider your workload when accepting meetings.""",
    TaskType.PROACTIVE_WORK: """Perform a role-specific proactive task.
1. Check your inbox and Teams for items related to your specialty.
2. Follow up on active projects or assignments.
3. Reach out to colleagues if coordination is needed.
4. Share progress updates where appropriate.

Focus on your role's core responsibilities and take initiative.""",
    TaskType.RESPOND_TO_PENDING: """You have items flagged from previous cycles that need attention.
Review the pending items in your memory context and address them:
1. Compose thoughtful replies to flagged emails.
2. Follow up on items you were waiting on.
3. Complete any deferred tasks.

Take your time - these items were flagged because they needed more thought.""",
    TaskType.END_OF_DAY: """End of day wrap-up:
1. Check inbox one final time for any urgent items.
2. Send any end-of-day status updates if relevant to your role.
3. Review tomorrow's calendar to be prepared.
4. Note anything that needs attention first thing tomorrow.

Keep it brief - you're wrapping up for the day.""",
}


def get_task_instructions(
    task_type: TaskType, custom_instructions: Optional[str] = None
) -> str:
    """Get task instructions, optionally appending custom instructions."""
    base = TASK_INSTRUCTIONS.get(task_type, "Perform your assigned task.")
    if custom_instructions:
        return f"{base}\n\n## Additional Context\n{custom_instructions}"
    return base
