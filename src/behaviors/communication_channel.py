"""Communication Channel Selection - decides how NPCs should communicate.

NPCs should think like humans about communication:
- Teams Chat: Quick acks, status updates, casual coordination
- Email: Formal assignments, detailed info, external clients, deliverables

This module helps NPCs make natural communication decisions.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CommunicationChannel(Enum):
    """Available communication channels."""
    EMAIL = "email"
    TEAMS_CHAT = "teams_chat"
    TEAMS_CHANNEL = "teams_channel"


class MessageType(Enum):
    """Types of messages that affect channel selection."""
    ACKNOWLEDGMENT = "acknowledgment"           # "Got it!", "Thanks!"
    STATUS_UPDATE = "status_update"             # "Started working on X"
    QUICK_QUESTION = "quick_question"           # "Hey, quick Q about..."
    FORMAL_ASSIGNMENT = "formal_assignment"     # Task assignment with details
    DETAILED_CONTENT = "detailed_content"       # Long-form content, deliverables
    PROGRESS_REPORT = "progress_report"         # Detailed progress update
    CLIENT_COMMUNICATION = "client_communication"  # Any external communication
    MEETING_COORDINATION = "meeting_coordination"  # Scheduling, calendar
    FILE_SHARING = "file_sharing"               # Documents, attachments
    CASUAL_CHAT = "casual_chat"                 # Informal office chat
    URGENT_REQUEST = "urgent_request"           # Time-sensitive needs


@dataclass
class ChannelDecision:
    """Result of channel selection decision."""
    channel: CommunicationChannel
    reason: str
    message_type: MessageType
    suggested_tone: str  # "formal", "casual", "friendly", "professional"
    suggested_length: str  # "brief", "moderate", "detailed"


@dataclass
class MessageContext:
    """Context for making a channel decision."""
    message_type: Optional[MessageType] = None
    content_length: int = 0  # Approximate character count
    is_external_recipient: bool = False
    is_urgent: bool = False
    is_reply: bool = False
    has_attachments: bool = False
    recipient_role: Optional[str] = None
    sender_role: Optional[str] = None
    project_context: bool = False
    time_sensitive: bool = False
    requires_tracking: bool = False  # Needs paper trail


class CommunicationChannelSelector:
    """
    Selects appropriate communication channel for NPC messages.

    Mimics how real employees choose between Teams and Email:

    Teams (Chat/Channel) is preferred for:
    - Quick acknowledgments ("Got it!", "On it!")
    - Status updates ("Just finished X")
    - Casual questions ("Hey, quick question...")
    - Internal coordination
    - Real-time collaboration
    - Messages < 200 chars

    Email is preferred for:
    - External communications (always!)
    - Formal assignments with details
    - Deliverables and content
    - Messages > 500 chars
    - Anything needing a paper trail
    - Meeting requests/calendar items
    - File sharing (unless live collab)
    """

    # Character thresholds
    BRIEF_MESSAGE_THRESHOLD = 150
    MODERATE_MESSAGE_THRESHOLD = 500

    def __init__(
        self,
        default_internal_channel: CommunicationChannel = CommunicationChannel.TEAMS_CHAT,
        prefer_email_for_assignments: bool = True,
    ):
        """
        Initialize the channel selector.

        Args:
            default_internal_channel: Default for internal messages
            prefer_email_for_assignments: Whether to use email for task assignments
        """
        self.default_internal_channel = default_internal_channel
        self.prefer_email_for_assignments = prefer_email_for_assignments

    def select_channel(self, context: MessageContext) -> ChannelDecision:
        """
        Select the appropriate communication channel based on context.

        Args:
            context: Message context with all relevant factors

        Returns:
            ChannelDecision with selected channel and reasoning
        """
        # Rule 1: ALWAYS use email for external recipients
        if context.is_external_recipient:
            return ChannelDecision(
                channel=CommunicationChannel.EMAIL,
                reason="External recipient - email is required for professional communication",
                message_type=context.message_type or MessageType.CLIENT_COMMUNICATION,
                suggested_tone="professional",
                suggested_length="detailed" if context.content_length > 200 else "moderate",
            )

        # Rule 2: Use email for content that needs tracking
        if context.requires_tracking or context.has_attachments:
            return ChannelDecision(
                channel=CommunicationChannel.EMAIL,
                reason="Requires paper trail or has attachments",
                message_type=context.message_type or MessageType.DETAILED_CONTENT,
                suggested_tone="professional",
                suggested_length="detailed",
            )

        # Rule 3: Detect message type from content length if not specified
        msg_type = context.message_type
        if not msg_type:
            msg_type = self._infer_message_type(context)

        # Rule 4: Handle specific message types
        return self._decide_by_message_type(msg_type, context)

    def _infer_message_type(self, context: MessageContext) -> MessageType:
        """Infer message type from context."""
        if context.content_length < self.BRIEF_MESSAGE_THRESHOLD:
            if context.is_reply:
                return MessageType.ACKNOWLEDGMENT
            return MessageType.QUICK_QUESTION
        elif context.content_length > self.MODERATE_MESSAGE_THRESHOLD:
            return MessageType.DETAILED_CONTENT
        else:
            if context.project_context:
                return MessageType.PROGRESS_REPORT
            return MessageType.STATUS_UPDATE

    def _decide_by_message_type(
        self, msg_type: MessageType, context: MessageContext
    ) -> ChannelDecision:
        """Make channel decision based on message type."""

        # Quick messages -> Teams
        if msg_type in (
            MessageType.ACKNOWLEDGMENT,
            MessageType.QUICK_QUESTION,
            MessageType.CASUAL_CHAT,
        ):
            return ChannelDecision(
                channel=CommunicationChannel.TEAMS_CHAT,
                reason=f"Quick {msg_type.value} - Teams is faster and less formal",
                message_type=msg_type,
                suggested_tone="casual" if msg_type == MessageType.CASUAL_CHAT else "friendly",
                suggested_length="brief",
            )

        # Status updates -> Teams (usually)
        if msg_type == MessageType.STATUS_UPDATE:
            # But if it's long or needs tracking, use email
            if context.content_length > self.MODERATE_MESSAGE_THRESHOLD:
                return ChannelDecision(
                    channel=CommunicationChannel.EMAIL,
                    reason="Detailed status update - email provides better formatting",
                    message_type=msg_type,
                    suggested_tone="professional",
                    suggested_length="detailed",
                )
            return ChannelDecision(
                channel=CommunicationChannel.TEAMS_CHAT,
                reason="Quick status update - Teams is immediate and visible",
                message_type=msg_type,
                suggested_tone="friendly",
                suggested_length="brief",
            )

        # Formal assignments -> Email (usually)
        if msg_type == MessageType.FORMAL_ASSIGNMENT:
            if self.prefer_email_for_assignments:
                return ChannelDecision(
                    channel=CommunicationChannel.EMAIL,
                    reason="Task assignment needs clear documentation and tracking",
                    message_type=msg_type,
                    suggested_tone="professional",
                    suggested_length="detailed",
                )
            else:
                return ChannelDecision(
                    channel=CommunicationChannel.TEAMS_CHANNEL,
                    reason="Task assignment posted to project channel for visibility",
                    message_type=msg_type,
                    suggested_tone="professional",
                    suggested_length="moderate",
                )

        # Detailed content -> Email
        if msg_type in (MessageType.DETAILED_CONTENT, MessageType.FILE_SHARING):
            return ChannelDecision(
                channel=CommunicationChannel.EMAIL,
                reason="Detailed content requires proper formatting and archiving",
                message_type=msg_type,
                suggested_tone="professional",
                suggested_length="detailed",
            )

        # Progress reports -> depends on length
        if msg_type == MessageType.PROGRESS_REPORT:
            if context.content_length > self.MODERATE_MESSAGE_THRESHOLD:
                return ChannelDecision(
                    channel=CommunicationChannel.EMAIL,
                    reason="Detailed progress report - email provides better format",
                    message_type=msg_type,
                    suggested_tone="professional",
                    suggested_length="detailed",
                )
            return ChannelDecision(
                channel=CommunicationChannel.TEAMS_CHANNEL,
                reason="Brief progress update - post to project channel",
                message_type=msg_type,
                suggested_tone="professional",
                suggested_length="moderate",
            )

        # Urgent requests -> Teams (faster)
        if msg_type == MessageType.URGENT_REQUEST:
            return ChannelDecision(
                channel=CommunicationChannel.TEAMS_CHAT,
                reason="Urgent - Teams provides immediate visibility",
                message_type=msg_type,
                suggested_tone="direct",
                suggested_length="brief",
            )

        # Meeting coordination -> Email (integrates with calendar)
        if msg_type == MessageType.MEETING_COORDINATION:
            return ChannelDecision(
                channel=CommunicationChannel.EMAIL,
                reason="Calendar/meeting items work better via email",
                message_type=msg_type,
                suggested_tone="professional",
                suggested_length="moderate",
            )

        # Default fallback
        return ChannelDecision(
            channel=self.default_internal_channel,
            reason="Default internal communication channel",
            message_type=msg_type,
            suggested_tone="friendly",
            suggested_length="moderate",
        )

    def get_quick_response_channel(
        self,
        original_channel: CommunicationChannel,
        is_external: bool = False,
    ) -> CommunicationChannel:
        """
        Get the appropriate channel for a quick response.

        If someone emails you, you usually email back.
        If someone Teams you, you usually Teams back.
        External = always email.
        """
        if is_external:
            return CommunicationChannel.EMAIL
        return original_channel


# Pre-built message templates for different channels
class MessageTemplates:
    """Templates for different message types and channels."""

    @staticmethod
    def teams_acknowledgment(sender_name: str, task_ref: str = "") -> str:
        """Quick acknowledgment for Teams."""
        options = [
            f"Got it, thanks {sender_name}!",
            f"On it!",
            f"Thanks! I'll take a look.",
            f"Received, will review shortly.",
            f"Perfect, I'll start on this now.",
        ]
        import random
        return random.choice(options)

    @staticmethod
    def teams_status_started(task_title: str) -> str:
        """Status update when starting work."""
        options = [
            f"Starting work on: {task_title}",
            f"Just started on {task_title} - will update when done",
            f"Working on {task_title} now",
        ]
        import random
        return random.choice(options)

    @staticmethod
    def teams_status_completed(task_title: str) -> str:
        """Status update when completing work."""
        options = [
            f"Finished {task_title} - sending over now",
            f"Done with {task_title}!",
            f"Completed {task_title}, please review when you get a chance",
        ]
        import random
        return random.choice(options)

    @staticmethod
    def teams_quick_question(question: str) -> str:
        """Quick question format for Teams."""
        return f"Hey, quick question - {question}"

    @staticmethod
    def email_formal_assignment_subject(task_title: str, project_title: str) -> str:
        """Subject line for formal task assignment email."""
        return f"Task Assignment: {task_title} [Project: {project_title}]"


def decide_communication_channel(
    message_type: Optional[MessageType] = None,
    content_length: int = 0,
    is_external: bool = False,
    is_urgent: bool = False,
    is_reply: bool = False,
    has_attachments: bool = False,
) -> ChannelDecision:
    """
    Convenience function to quickly decide on a communication channel.

    Args:
        message_type: Type of message being sent
        content_length: Approximate character count
        is_external: Is recipient outside the organization?
        is_urgent: Is this time-sensitive?
        is_reply: Is this a reply to a previous message?
        has_attachments: Does it include files?

    Returns:
        ChannelDecision with recommended channel and guidance

    Example:
        decision = decide_communication_channel(
            message_type=MessageType.ACKNOWLEDGMENT,
            content_length=20,
            is_reply=True,
        )
        # Returns: Teams chat with casual tone
    """
    selector = CommunicationChannelSelector()
    context = MessageContext(
        message_type=message_type,
        content_length=content_length,
        is_external_recipient=is_external,
        is_urgent=is_urgent,
        is_reply=is_reply,
        has_attachments=has_attachments,
    )
    return selector.select_channel(context)
