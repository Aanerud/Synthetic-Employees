"""Tests for communication channel selection."""

import unittest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.behaviors.communication_channel import (
    CommunicationChannel,
    CommunicationChannelSelector,
    MessageContext,
    MessageType,
    MessageTemplates,
    decide_communication_channel,
)


class TestChannelSelection(unittest.TestCase):
    """Test communication channel selection logic."""

    def setUp(self):
        self.selector = CommunicationChannelSelector()

    def test_external_always_email(self):
        """External recipients should always get email."""
        context = MessageContext(
            message_type=MessageType.QUICK_QUESTION,
            content_length=50,
            is_external_recipient=True,
        )
        decision = self.selector.select_channel(context)
        self.assertEqual(decision.channel, CommunicationChannel.EMAIL)
        self.assertIn("External", decision.reason)

    def test_acknowledgment_uses_teams(self):
        """Quick acknowledgments should use Teams."""
        context = MessageContext(
            message_type=MessageType.ACKNOWLEDGMENT,
            content_length=20,
            is_external_recipient=False,
            is_reply=True,
        )
        decision = self.selector.select_channel(context)
        self.assertEqual(decision.channel, CommunicationChannel.TEAMS_CHAT)
        self.assertEqual(decision.suggested_tone, "friendly")

    def test_formal_assignment_uses_email(self):
        """Formal task assignments should use email."""
        context = MessageContext(
            message_type=MessageType.FORMAL_ASSIGNMENT,
            content_length=500,
            is_external_recipient=False,
            requires_tracking=True,
        )
        decision = self.selector.select_channel(context)
        self.assertEqual(decision.channel, CommunicationChannel.EMAIL)
        self.assertEqual(decision.suggested_tone, "professional")

    def test_short_status_update_uses_teams(self):
        """Short status updates should use Teams."""
        context = MessageContext(
            message_type=MessageType.STATUS_UPDATE,
            content_length=100,
            is_external_recipient=False,
        )
        decision = self.selector.select_channel(context)
        self.assertEqual(decision.channel, CommunicationChannel.TEAMS_CHAT)

    def test_long_status_update_uses_email(self):
        """Long status updates should use email."""
        context = MessageContext(
            message_type=MessageType.STATUS_UPDATE,
            content_length=800,
            is_external_recipient=False,
        )
        decision = self.selector.select_channel(context)
        self.assertEqual(decision.channel, CommunicationChannel.EMAIL)

    def test_urgent_uses_teams(self):
        """Urgent messages should use Teams for speed."""
        context = MessageContext(
            message_type=MessageType.URGENT_REQUEST,
            content_length=200,
            is_external_recipient=False,
            is_urgent=True,
        )
        decision = self.selector.select_channel(context)
        self.assertEqual(decision.channel, CommunicationChannel.TEAMS_CHAT)
        self.assertEqual(decision.suggested_tone, "direct")

    def test_attachments_require_email(self):
        """Messages with attachments should use email."""
        context = MessageContext(
            message_type=MessageType.STATUS_UPDATE,
            content_length=100,
            is_external_recipient=False,
            has_attachments=True,
        )
        decision = self.selector.select_channel(context)
        self.assertEqual(decision.channel, CommunicationChannel.EMAIL)

    def test_detailed_content_uses_email(self):
        """Detailed content should use email for formatting."""
        context = MessageContext(
            message_type=MessageType.DETAILED_CONTENT,
            content_length=2000,
            is_external_recipient=False,
        )
        decision = self.selector.select_channel(context)
        self.assertEqual(decision.channel, CommunicationChannel.EMAIL)

    def test_quick_question_uses_teams(self):
        """Quick questions should use Teams."""
        context = MessageContext(
            message_type=MessageType.QUICK_QUESTION,
            content_length=80,
            is_external_recipient=False,
        )
        decision = self.selector.select_channel(context)
        self.assertEqual(decision.channel, CommunicationChannel.TEAMS_CHAT)

    def test_meeting_coordination_uses_email(self):
        """Meeting coordination should use email (calendar integration)."""
        context = MessageContext(
            message_type=MessageType.MEETING_COORDINATION,
            content_length=200,
            is_external_recipient=False,
        )
        decision = self.selector.select_channel(context)
        self.assertEqual(decision.channel, CommunicationChannel.EMAIL)


class TestConvenienceFunction(unittest.TestCase):
    """Test the convenience function."""

    def test_quick_ack_decision(self):
        """Test quick acknowledgment via convenience function."""
        decision = decide_communication_channel(
            message_type=MessageType.ACKNOWLEDGMENT,
            content_length=20,
            is_reply=True,
        )
        self.assertEqual(decision.channel, CommunicationChannel.TEAMS_CHAT)

    def test_external_decision(self):
        """Test external recipient decision."""
        decision = decide_communication_channel(
            content_length=50,
            is_external=True,
        )
        self.assertEqual(decision.channel, CommunicationChannel.EMAIL)

    def test_automatic_type_inference(self):
        """Test automatic message type inference from length."""
        # Very short message -> likely acknowledgment
        decision_short = decide_communication_channel(content_length=30, is_reply=True)
        self.assertEqual(decision_short.channel, CommunicationChannel.TEAMS_CHAT)

        # Long message -> detailed content
        decision_long = decide_communication_channel(content_length=1000)
        self.assertEqual(decision_long.channel, CommunicationChannel.EMAIL)


class TestMessageTemplates(unittest.TestCase):
    """Test message templates for different channels."""

    def test_teams_acknowledgment_variety(self):
        """Test that acknowledgments have variety."""
        responses = set()
        for _ in range(50):
            response = MessageTemplates.teams_acknowledgment("John", "Task 1")
            responses.add(response)

        # Should have multiple different responses
        self.assertGreater(len(responses), 1)

    def test_teams_status_started(self):
        """Test status started template."""
        message = MessageTemplates.teams_status_started("Marketing flyer")
        self.assertIn("Marketing flyer", message)

    def test_teams_status_completed(self):
        """Test status completed template."""
        message = MessageTemplates.teams_status_completed("Website redesign")
        self.assertIn("Website redesign", message)

    def test_teams_quick_question(self):
        """Test quick question format."""
        message = MessageTemplates.teams_quick_question("what's the deadline?")
        self.assertIn("quick question", message.lower())
        self.assertIn("deadline", message)


class TestChannelDecision(unittest.TestCase):
    """Test ChannelDecision dataclass."""

    def test_decision_has_all_fields(self):
        """Test that decision includes all guidance."""
        decision = decide_communication_channel(
            message_type=MessageType.FORMAL_ASSIGNMENT,
            content_length=500,
        )

        self.assertIsNotNone(decision.channel)
        self.assertIsNotNone(decision.reason)
        self.assertIsNotNone(decision.message_type)
        self.assertIsNotNone(decision.suggested_tone)
        self.assertIsNotNone(decision.suggested_length)


if __name__ == "__main__":
    unittest.main()
