"""Role definitions for synthetic employees."""

from dataclasses import dataclass
from datetime import timedelta
from typing import List, Optional


@dataclass
class MeetingPreferences:
    """Meeting acceptance preferences for a role."""

    auto_accept_from: List[str]  # Roles to auto-accept meetings from
    decline_outside_hours: bool
    buffer_between_meetings_minutes: int
    max_meetings_per_day: Optional[int] = None


@dataclass
class Role:
    """Defines behavior patterns for a job role."""

    name: str
    responsibilities: List[str]
    email_check_frequency_minutes: int  # How often to check email
    response_time_sla_hours: int  # How quickly to respond
    meeting_preferences: MeetingPreferences
    communication_style: str
    proactive_tasks: List[str]  # Tasks agent initiates


# Executive Roles

CEO = Role(
    name="CEO",
    responsibilities=[
        "Strategic decisions",
        "Team oversight",
        "Stakeholder communication",
        "Company vision",
    ],
    email_check_frequency_minutes=30,
    response_time_sla_hours=1,
    meeting_preferences=MeetingPreferences(
        auto_accept_from=["CTO", "CFO", "COO", "Board Member"],
        decline_outside_hours=True,
        buffer_between_meetings_minutes=15,
        max_meetings_per_day=8,
    ),
    communication_style="concise, strategic, high-level",
    proactive_tasks=[
        "Schedule weekly executive meeting",
        "Send monthly company update",
        "Review department reports",
    ],
)

CTO = Role(
    name="CTO",
    responsibilities=[
        "Technical strategy",
        "Engineering oversight",
        "Architecture decisions",
        "Technology innovation",
    ],
    email_check_frequency_minutes=30,
    response_time_sla_hours=2,
    meeting_preferences=MeetingPreferences(
        auto_accept_from=["CEO", "Tech Lead", "DevOps Engineer"],
        decline_outside_hours=True,
        buffer_between_meetings_minutes=15,
        max_meetings_per_day=6,
    ),
    communication_style="technical but accessible, forward-thinking",
    proactive_tasks=[
        "Schedule engineering team meeting",
        "Review technical roadmap",
        "Approve architecture proposals",
    ],
)

# Engineering Roles

SENIOR_DEVELOPER = Role(
    name="Senior Developer",
    responsibilities=[
        "Write code",
        "Code reviews",
        "Mentor junior developers",
        "Technical decisions",
    ],
    email_check_frequency_minutes=60,
    response_time_sla_hours=4,
    meeting_preferences=MeetingPreferences(
        auto_accept_from=["CTO", "Tech Lead", "Product Manager"],
        decline_outside_hours=True,
        buffer_between_meetings_minutes=5,
        max_meetings_per_day=4,
    ),
    communication_style="technical, detailed, helpful",
    proactive_tasks=[
        "Send daily standup update",
        "Request code reviews",
        "Share technical insights",
    ],
)

DEVELOPER = Role(
    name="Developer",
    responsibilities=[
        "Write code",
        "Code reviews",
        "Bug fixes",
        "Technical discussions",
    ],
    email_check_frequency_minutes=60,
    response_time_sla_hours=4,
    meeting_preferences=MeetingPreferences(
        auto_accept_from=["Tech Lead", "Senior Developer", "Product Manager"],
        decline_outside_hours=True,
        buffer_between_meetings_minutes=5,
        max_meetings_per_day=4,
    ),
    communication_style="technical, detailed",
    proactive_tasks=[
        "Send daily standup update",
        "Ask for help when blocked",
        "Update task status",
    ],
)

FRONTEND_DEVELOPER = Role(
    name="Frontend Developer",
    responsibilities=[
        "Build user interfaces",
        "Implement designs",
        "Optimize performance",
        "Collaborate with designers",
    ],
    email_check_frequency_minutes=60,
    response_time_sla_hours=4,
    meeting_preferences=MeetingPreferences(
        auto_accept_from=["Tech Lead", "UX Designer", "Product Manager"],
        decline_outside_hours=True,
        buffer_between_meetings_minutes=5,
        max_meetings_per_day=4,
    ),
    communication_style="visual, user-focused, collaborative",
    proactive_tasks=[
        "Send standup update",
        "Share UI mockups",
        "Request design feedback",
    ],
)

BACKEND_DEVELOPER = Role(
    name="Backend Developer",
    responsibilities=[
        "Build APIs",
        "Database design",
        "System architecture",
        "Performance optimization",
    ],
    email_check_frequency_minutes=60,
    response_time_sla_hours=4,
    meeting_preferences=MeetingPreferences(
        auto_accept_from=["Tech Lead", "DevOps Engineer", "Product Manager"],
        decline_outside_hours=True,
        buffer_between_meetings_minutes=5,
        max_meetings_per_day=4,
    ),
    communication_style="technical, systematic, detail-oriented",
    proactive_tasks=[
        "Send standup update",
        "Document API changes",
        "Monitor system health",
    ],
)

DEVOPS_ENGINEER = Role(
    name="DevOps Engineer",
    responsibilities=[
        "Infrastructure management",
        "CI/CD pipelines",
        "Monitoring",
        "Incident response",
    ],
    email_check_frequency_minutes=45,
    response_time_sla_hours=2,  # Faster response for ops
    meeting_preferences=MeetingPreferences(
        auto_accept_from=["CTO", "Backend Developer"],
        decline_outside_hours=False,  # On-call
        buffer_between_meetings_minutes=5,
        max_meetings_per_day=4,
    ),
    communication_style="clear, action-oriented, status-focused",
    proactive_tasks=[
        "Send daily status report",
        "Alert on incidents",
        "Share deployment updates",
    ],
)

QA_ENGINEER = Role(
    name="QA Engineer",
    responsibilities=[
        "Test applications",
        "Report bugs",
        "Automate tests",
        "Quality assurance",
    ],
    email_check_frequency_minutes=60,
    response_time_sla_hours=3,
    meeting_preferences=MeetingPreferences(
        auto_accept_from=["Product Manager", "Developer"],
        decline_outside_hours=True,
        buffer_between_meetings_minutes=5,
        max_meetings_per_day=4,
    ),
    communication_style="thorough, detail-oriented, constructive",
    proactive_tasks=[
        "Report test results",
        "File bug reports",
        "Request test environments",
    ],
)

# Product Roles

PRODUCT_MANAGER = Role(
    name="Product Manager",
    responsibilities=[
        "Product strategy",
        "Feature prioritization",
        "Stakeholder communication",
        "Roadmap planning",
    ],
    email_check_frequency_minutes=45,
    response_time_sla_hours=2,
    meeting_preferences=MeetingPreferences(
        auto_accept_from=["CEO", "CTO", "Designer", "Developer"],
        decline_outside_hours=True,
        buffer_between_meetings_minutes=10,
        max_meetings_per_day=6,
    ),
    communication_style="clear, user-focused, prioritizes ruthlessly",
    proactive_tasks=[
        "Schedule planning meetings",
        "Share product updates",
        "Request feature estimates",
        "Follow up on blockers",
    ],
)

UX_DESIGNER = Role(
    name="UX Designer",
    responsibilities=[
        "User experience design",
        "User research",
        "Prototyping",
        "Design systems",
    ],
    email_check_frequency_minutes=60,
    response_time_sla_hours=4,
    meeting_preferences=MeetingPreferences(
        auto_accept_from=["Product Manager", "Frontend Developer"],
        decline_outside_hours=True,
        buffer_between_meetings_minutes=10,
        max_meetings_per_day=4,
    ),
    communication_style="visual, empathetic, user-centered",
    proactive_tasks=[
        "Share design mockups",
        "Request feedback on designs",
        "Schedule user research sessions",
    ],
)

# Business Roles

MARKETING_MANAGER = Role(
    name="Marketing Manager",
    responsibilities=[
        "Marketing strategy",
        "Campaign management",
        "Brand development",
        "Market research",
    ],
    email_check_frequency_minutes=45,
    response_time_sla_hours=3,
    meeting_preferences=MeetingPreferences(
        auto_accept_from=["CEO", "Product Manager", "Sales Director"],
        decline_outside_hours=True,
        buffer_between_meetings_minutes=10,
        max_meetings_per_day=5,
    ),
    communication_style="persuasive, creative, data-driven",
    proactive_tasks=[
        "Share campaign results",
        "Request product updates",
        "Coordinate launches",
    ],
)

SALES_DIRECTOR = Role(
    name="Sales Director",
    responsibilities=[
        "Sales strategy",
        "Client relationships",
        "Revenue targets",
        "Team management",
    ],
    email_check_frequency_minutes=30,
    response_time_sla_hours=2,
    meeting_preferences=MeetingPreferences(
        auto_accept_from=["CEO", "Marketing Manager"],
        decline_outside_hours=False,  # Responds to clients
        buffer_between_meetings_minutes=10,
        max_meetings_per_day=8,
    ),
    communication_style="persuasive, relationship-focused, results-driven",
    proactive_tasks=[
        "Share sales updates",
        "Request product demos",
        "Follow up with clients",
    ],
)

# Editorial Roles (TextCraft Europe)

EDITORIAL_DIRECTOR = Role(
    name="Editorial Director",
    responsibilities=[
        "Lead editorial team",
        "Ensure consistent quality",
        "Style guide governance",
        "Strategic editorial direction",
    ],
    email_check_frequency_minutes=30,
    response_time_sla_hours=2,
    meeting_preferences=MeetingPreferences(
        auto_accept_from=["CEO", "Senior Editor", "Managing Editor"],
        decline_outside_hours=True,
        buffer_between_meetings_minutes=15,
        max_meetings_per_day=6,
    ),
    communication_style="authoritative, precise, style-conscious",
    proactive_tasks=[
        "Review editorial quality reports",
        "Schedule style guide reviews",
        "Coordinate cross-team editorial standards",
    ],
)

SENIOR_EDITOR_LITERARY = Role(
    name="Senior Editor - Literary",
    responsibilities=[
        "Edit fiction and poetry",
        "Narrative craft assessment",
        "Author development",
        "Literary quality assurance",
    ],
    email_check_frequency_minutes=45,
    response_time_sla_hours=4,
    meeting_preferences=MeetingPreferences(
        auto_accept_from=["Editorial Director", "Managing Editor", "Author"],
        decline_outside_hours=True,
        buffer_between_meetings_minutes=10,
        max_meetings_per_day=4,
    ),
    communication_style="literary, thoughtful, appreciative of craft",
    proactive_tasks=[
        "Submit manuscript assessments",
        "Share literary insights",
        "Recommend promising submissions",
    ],
)

# Support Roles

HR_MANAGER = Role(
    name="HR Manager",
    responsibilities=[
        "Recruitment",
        "Employee relations",
        "Policies",
        "Team culture",
    ],
    email_check_frequency_minutes=60,
    response_time_sla_hours=4,
    meeting_preferences=MeetingPreferences(
        auto_accept_from=["CEO", "Department Heads"],
        decline_outside_hours=True,
        buffer_between_meetings_minutes=15,
        max_meetings_per_day=5,
    ),
    communication_style="empathetic, professional, supportive",
    proactive_tasks=[
        "Schedule interviews",
        "Send policy updates",
        "Plan team events",
    ],
)


# Role registry
ROLE_REGISTRY = {
    "CEO": CEO,
    "CTO": CTO,
    "Senior Developer": SENIOR_DEVELOPER,
    "Developer": DEVELOPER,
    "Frontend Developer": FRONTEND_DEVELOPER,
    "Backend Developer": BACKEND_DEVELOPER,
    "DevOps Engineer": DEVOPS_ENGINEER,
    "QA Engineer": QA_ENGINEER,
    "Product Manager": PRODUCT_MANAGER,
    "UX Designer": UX_DESIGNER,
    "Marketing Manager": MARKETING_MANAGER,
    "Sales Director": SALES_DIRECTOR,
    "HR Manager": HR_MANAGER,
    "Editorial Director": EDITORIAL_DIRECTOR,
    "Senior Editor - Literary": SENIOR_EDITOR_LITERARY,
}


def get_role(role_name: str) -> Role:
    """Get role definition by name."""
    role = ROLE_REGISTRY.get(role_name)
    if not role:
        # Default to generic developer if role not found
        print(f"Warning: Role '{role_name}' not found, using Developer defaults")
        return DEVELOPER
    return role
