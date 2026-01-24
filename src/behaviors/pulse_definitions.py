"""Role-specific pulse definitions for agent daily routines.

Each role has a unique daily routine that determines their proactive behaviors.
"""

from typing import Dict

from .pulse import DailyRoutine, PulseEvent


# =============================================================================
# Key Account Manager Routine
# =============================================================================

KEY_ACCOUNT_MANAGER_ROUTINE = DailyRoutine(
    role="Key Account Manager",
    description="Manages external client relationships and coordinates internal teams",
    pulses=[
        # Morning: Client inbox review and team standup
        PulseEvent(
            name="inbox_review",
            time_window=(9, 10),
            probability=0.95,
            action="check_external_emails",
            params={"priority": "client_requests"},
            cooldown_minutes=120,
        ),
        PulseEvent(
            name="team_standup",
            time_window=(9, 10),
            probability=0.7,
            action="post_standup_teams",
            params={"channel": "general"},
            cooldown_minutes=1440,  # Once per day
        ),
        PulseEvent(
            name="project_status_check",
            time_window=(10, 12),
            probability=0.6,
            action="check_project_status",
            params={},
            cooldown_minutes=180,
        ),
        # Midday: Client followup
        PulseEvent(
            name="client_followup",
            time_window=(13, 14),
            probability=0.5,
            action="check_pending_projects",
            params={"status": "awaiting_response"},
            cooldown_minutes=240,
        ),
        # Afternoon: Task coordination and client updates
        PulseEvent(
            name="task_coordination",
            time_window=(15, 16),
            probability=0.6,
            action="check_delegated_tasks",
            params={},
            cooldown_minutes=120,
        ),
        PulseEvent(
            name="client_update",
            time_window=(16, 17),
            probability=0.4,
            action="send_client_updates",
            params={"type": "progress"},
            cooldown_minutes=240,
        ),
    ],
)


# =============================================================================
# Editorial Director Routine
# =============================================================================

EDITORIAL_DIRECTOR_ROUTINE = DailyRoutine(
    role="Editorial Director",
    description="Oversees editorial operations and content quality",
    pulses=[
        # Morning: Review content queue and assignments
        PulseEvent(
            name="content_queue_review",
            time_window=(9, 10),
            probability=0.85,
            action="review_content_queue",
            params={},
            cooldown_minutes=240,
        ),
        PulseEvent(
            name="editorial_standup",
            time_window=(10, 11),
            probability=0.6,
            action="post_standup_teams",
            params={"channel": "editorial"},
            cooldown_minutes=1440,
        ),
        # Midday: Quality checks
        PulseEvent(
            name="quality_review",
            time_window=(12, 14),
            probability=0.5,
            action="review_pending_content",
            params={"type": "quality_check"},
            cooldown_minutes=180,
        ),
        # Afternoon: Assignment distribution
        PulseEvent(
            name="assign_work",
            time_window=(14, 16),
            probability=0.5,
            action="distribute_assignments",
            params={},
            cooldown_minutes=240,
        ),
    ],
)


# =============================================================================
# Senior Editor Routine
# =============================================================================

SENIOR_EDITOR_ROUTINE = DailyRoutine(
    role="Senior Editor - Literary",
    description="Handles complex editing tasks and mentors junior editors",
    pulses=[
        # Morning: Check assigned work
        PulseEvent(
            name="check_assignments",
            time_window=(9, 10),
            probability=0.9,
            action="check_inbox_assignments",
            params={},
            cooldown_minutes=120,
        ),
        PulseEvent(
            name="team_update",
            time_window=(10, 11),
            probability=0.5,
            action="post_progress_update",
            params={"channel": "editorial"},
            cooldown_minutes=240,
        ),
        # Midday: Peer review
        PulseEvent(
            name="peer_review",
            time_window=(13, 14),
            probability=0.4,
            action="review_junior_work",
            params={},
            cooldown_minutes=180,
        ),
        # Afternoon: Work on assignments
        PulseEvent(
            name="work_session",
            time_window=(14, 17),
            probability=0.7,
            action="process_editing_tasks",
            params={},
            cooldown_minutes=60,
        ),
    ],
)


# =============================================================================
# Developer Routine
# =============================================================================

DEVELOPER_ROUTINE = DailyRoutine(
    role="Developer",
    description="Writes and reviews code, participates in technical discussions",
    pulses=[
        # Morning: Stand-up and PR review
        PulseEvent(
            name="morning_standup",
            time_window=(9, 10),
            probability=0.8,
            action="post_standup_teams",
            params={"channel": "dev-team"},
            cooldown_minutes=1440,
        ),
        PulseEvent(
            name="pr_review",
            time_window=(10, 12),
            probability=0.6,
            action="check_pull_requests",
            params={},
            cooldown_minutes=180,
        ),
        # Afternoon: Code review responses
        PulseEvent(
            name="code_review_responses",
            time_window=(14, 16),
            probability=0.5,
            action="respond_to_reviews",
            params={},
            cooldown_minutes=120,
        ),
    ],
)


# =============================================================================
# Product Manager Routine
# =============================================================================

PRODUCT_MANAGER_ROUTINE = DailyRoutine(
    role="Product Manager",
    description="Manages product roadmap and stakeholder communications",
    pulses=[
        # Morning: Stakeholder updates
        PulseEvent(
            name="stakeholder_emails",
            time_window=(9, 10),
            probability=0.85,
            action="check_external_emails",
            params={"priority": "stakeholders"},
            cooldown_minutes=120,
        ),
        PulseEvent(
            name="team_sync",
            time_window=(10, 11),
            probability=0.6,
            action="post_standup_teams",
            params={"channel": "product"},
            cooldown_minutes=1440,
        ),
        # Midday: Backlog review
        PulseEvent(
            name="backlog_review",
            time_window=(13, 14),
            probability=0.5,
            action="review_backlog",
            params={},
            cooldown_minutes=240,
        ),
        # Afternoon: Sprint coordination
        PulseEvent(
            name="sprint_coordination",
            time_window=(15, 17),
            probability=0.4,
            action="coordinate_sprint",
            params={},
            cooldown_minutes=180,
        ),
    ],
)


# =============================================================================
# Proofreader Routine
# =============================================================================

PROOFREADER_ROUTINE = DailyRoutine(
    role="Proofreader",
    description="Reviews content for grammar, spelling, and consistency",
    pulses=[
        # Morning: Check new assignments
        PulseEvent(
            name="check_assignments",
            time_window=(9, 10),
            probability=0.9,
            action="check_inbox_assignments",
            params={},
            cooldown_minutes=120,
        ),
        # Work sessions throughout day
        PulseEvent(
            name="morning_proofreading",
            time_window=(10, 12),
            probability=0.8,
            action="process_proofreading_queue",
            params={},
            cooldown_minutes=60,
        ),
        PulseEvent(
            name="afternoon_proofreading",
            time_window=(14, 17),
            probability=0.8,
            action="process_proofreading_queue",
            params={},
            cooldown_minutes=60,
        ),
        # Completion updates
        PulseEvent(
            name="completion_update",
            time_window=(16, 17),
            probability=0.5,
            action="post_completion_update",
            params={"channel": "editorial"},
            cooldown_minutes=240,
        ),
    ],
)


# =============================================================================
# Default/Generic Routine
# =============================================================================

DEFAULT_ROUTINE = DailyRoutine(
    role="Default",
    description="Basic routine for roles without specific definitions",
    pulses=[
        # Morning inbox check
        PulseEvent(
            name="inbox_check",
            time_window=(9, 10),
            probability=0.9,
            action="check_inbox",
            params={},
            cooldown_minutes=120,
        ),
        # Team presence
        PulseEvent(
            name="morning_presence",
            time_window=(9, 11),
            probability=0.3,
            action="post_presence_update",
            params={},
            cooldown_minutes=480,
        ),
        # Afternoon check
        PulseEvent(
            name="afternoon_check",
            time_window=(14, 16),
            probability=0.6,
            action="check_inbox",
            params={},
            cooldown_minutes=120,
        ),
    ],
)


# =============================================================================
# Role to Routine Mapping
# =============================================================================

ROLE_ROUTINES: Dict[str, DailyRoutine] = {
    "Key Account Manager": KEY_ACCOUNT_MANAGER_ROUTINE,
    "Editorial Director": EDITORIAL_DIRECTOR_ROUTINE,
    "Senior Editor - Literary": SENIOR_EDITOR_ROUTINE,
    "Senior Editor": SENIOR_EDITOR_ROUTINE,
    "Developer": DEVELOPER_ROUTINE,
    "Senior Developer": DEVELOPER_ROUTINE,
    "Frontend Developer": DEVELOPER_ROUTINE,
    "Backend Developer": DEVELOPER_ROUTINE,
    "Product Manager": PRODUCT_MANAGER_ROUTINE,
    "Proofreader": PROOFREADER_ROUTINE,
}


def get_routine_for_role(role: str) -> DailyRoutine:
    """
    Get the daily routine for a specific role.

    Falls back to DEFAULT_ROUTINE if no specific routine is defined.
    """
    # Try exact match first
    if role in ROLE_ROUTINES:
        return ROLE_ROUTINES[role]

    # Try partial match (role contains key or key contains role)
    role_lower = role.lower()
    for key, routine in ROLE_ROUTINES.items():
        if key.lower() in role_lower or role_lower in key.lower():
            return routine

    return DEFAULT_ROUTINE
