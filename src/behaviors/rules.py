"""Rule-based behavior engine for agent decisions."""

import random
from typing import Dict, List, Optional, Tuple

from src.agents.agent_registry import AgentConfig
from src.agents.roles import Role


class BehaviorEngine:
    """Rule-based decision making for agents."""

    def __init__(self):
        self.urgent_keywords = ["urgent", "asap", "critical", "emergency", "important"]
        self.action_keywords = ["please", "can you", "could you", "would you"]

    def should_respond_to_email(
        self, agent: AgentConfig, role: Role, email: Dict
    ) -> Tuple[bool, str]:
        """
        Determine if agent should respond to an email.

        Returns: (should_respond: bool, reason: str)
        """
        sender = email.get("from", {}).get("emailAddress", {}).get("address", "").lower()
        subject = email.get("subject", "").lower()
        body = email.get("body", {}).get("content", "").lower()
        is_read = email.get("isRead", False)

        # Already read and responded? Skip
        if is_read:
            return False, "Already read"

        # Check if agent is in To: field (vs CC/BCC)
        to_recipients = email.get("toRecipients", [])
        agent_in_to = any(
            r.get("emailAddress", {}).get("address", "").lower() == agent.email.lower()
            for r in to_recipients
        )

        # Priority 1: Urgent emails
        if any(keyword in subject or keyword in body for keyword in self.urgent_keywords):
            return True, "Urgent keyword detected"

        # Priority 2: Direct request from CEO
        if "ceo" in sender and agent_in_to:
            return True, "CEO direct request"

        # Priority 3: Direct request from manager/supervisor
        if agent_in_to and any(keyword in body for keyword in self.action_keywords):
            return True, "Direct action requested"

        # Priority 4: Mentioned in To: field
        if agent_in_to:
            # Respond to most emails where agent is directly addressed
            return random.random() < 0.8, "Directly addressed (probabilistic)"

        # Lower priority: CC'd
        cc_recipients = email.get("ccRecipients", [])
        agent_in_cc = any(
            r.get("emailAddress", {}).get("address", "").lower() == agent.email.lower()
            for r in cc_recipients
        )

        if agent_in_cc:
            # Only respond to CC'd emails occasionally
            return random.random() < 0.2, "CC'd (low priority)"

        return False, "Not relevant"

    def should_accept_meeting(
        self, agent: AgentConfig, role: Role, meeting: Dict
    ) -> Tuple[str, str]:
        """
        Determine meeting response (accept/decline/tentative).

        Returns: (response: str, reason: str)
        """
        organizer = meeting.get("organizer", {}).get("emailAddress", {}).get("address", "").lower()
        subject = meeting.get("subject", "").lower()
        is_optional = meeting.get("responseRequested", True) is False

        # Check for conflicts (simplified - would need to check calendar in real implementation)
        # For now, assume no conflicts

        # Priority 1: Auto-accept from specific roles
        for acceptable_role in role.meeting_preferences.auto_accept_from:
            if acceptable_role.lower() in organizer:
                return "accept", f"Auto-accept from {acceptable_role}"

        # Priority 2: Decline if outside work hours
        if role.meeting_preferences.decline_outside_hours:
            meeting_start = meeting.get("start", {}).get("dateTime", "")
            # Simplified check - would need proper time parsing
            if "18:" in meeting_start or "19:" in meeting_start or "20:" in meeting_start:
                return "decline", "Outside work hours"

        # Priority 3: Optional meetings - probabilistic acceptance
        if is_optional:
            if random.random() < 0.7:
                return "accept", "Optional meeting (70% acceptance)"
            else:
                return "tentative", "Optional meeting (tentative)"

        # Priority 4: Required meetings with relevant keywords
        role_keywords = {
            "CEO": ["executive", "board", "strategy"],
            "CTO": ["technical", "architecture", "engineering"],
            "Developer": ["code", "review", "standup", "sprint"],
            "Product Manager": ["product", "planning", "roadmap"],
        }

        relevant_keywords = role_keywords.get(agent.role, [])
        if any(keyword in subject for keyword in relevant_keywords):
            return "accept", "Relevant to role"

        # Default: Accept most meetings
        if random.random() < 0.85:
            return "accept", "Default acceptance"
        else:
            return "tentative", "Uncertain availability"

    def generate_email_response(
        self, agent: AgentConfig, role: Role, email: Dict, response_type: str = "reply"
    ) -> str:
        """Generate an email response based on role and context."""
        sender_name = email.get("from", {}).get("emailAddress", {}).get("name", "colleague")
        subject = email.get("subject", "")

        # Template-based responses
        templates = {
            "CEO": [
                f"Thanks for bringing this to my attention. Let's discuss further.",
                f"Acknowledged. Please proceed with your recommendation.",
                f"I'll review this and get back to you shortly.",
            ],
            "Developer": [
                f"Hi {sender_name}, I'll take a look at this and get back to you.",
                f"Thanks for the heads up. Working on this now.",
                f"Got it. I'll prioritize this in my current sprint.",
            ],
            "Product Manager": [
                f"Thanks {sender_name}. Let me coordinate with the team and follow up.",
                f"I'll add this to our backlog and prioritize accordingly.",
                f"Let's schedule some time to discuss this in more detail.",
            ],
        }

        role_templates = templates.get(agent.role, templates["Developer"])
        response_body = random.choice(role_templates)

        # Add signature
        signature = f"\n\nBest regards,\n{agent.name}\n{agent.role}"

        return response_body + signature

    def get_proactive_task(self, agent: AgentConfig, role: Role, current_time) -> Optional[str]:
        """Determine if agent should perform a proactive task."""
        # Check if it's time for proactive tasks
        hour = current_time.hour

        # Morning standup for developers (9:30 AM)
        if agent.role in ["Developer", "Senior Developer", "Frontend Developer", "Backend Developer"]:
            if hour == 9 and random.random() < 0.3:  # 30% chance around 9 AM
                return "send_standup_update"

        # CEO weekly meeting (Monday 2 PM)
        if agent.role == "CEO":
            if current_time.weekday() == 0 and hour == 14:  # Monday 2 PM
                return "schedule_weekly_meeting"

        # Product manager planning (Wednesday)
        if agent.role == "Product Manager":
            if current_time.weekday() == 2 and hour == 10:  # Wednesday 10 AM
                return "send_planning_update"

        return None

    def get_response_priority(self, agent: AgentConfig, role: Role, email: Dict) -> str:
        """Determine response priority (immediate, high, normal, low)."""
        subject = email.get("subject", "").lower()
        body = email.get("body", {}).get("content", "").lower()

        # Immediate: Urgent keywords
        if any(keyword in subject or keyword in body for keyword in self.urgent_keywords):
            return "immediate"

        # High: From CEO or direct manager
        sender = email.get("from", {}).get("emailAddress", {}).get("address", "").lower()
        if "ceo" in sender:
            return "high"

        # Normal: Direct To: emails
        to_recipients = email.get("toRecipients", [])
        agent_in_to = any(
            r.get("emailAddress", {}).get("address", "").lower() == agent.email.lower()
            for r in to_recipients
        )
        if agent_in_to:
            return "normal"

        # Low: CC'd or FYI
        return "low"


# Singleton instance
behavior_engine = BehaviorEngine()
