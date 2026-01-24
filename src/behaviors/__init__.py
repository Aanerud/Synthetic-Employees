"""Behaviors module for agent actions and responses."""

from .agent_loop import (
    tick_agent,
    check_inbox,
    check_calendar,
    process_email,
    should_respond_to_email,
)
from .rules import behavior_engine

# Pulse system
from .pulse import PulseEvent, DailyRoutine, PulseExecution
from .pulse_definitions import get_routine_for_role, ROLE_ROUTINES
from .pulse_executor import PulseExecutor

# KAM workflow
from .kam_workflow import KeyAccountManagerWorkflow

# Rate limiting and human behavior patterns
from .rate_limiter import (
    AgentRateLimiter,
    RateLimitedMCPClient,
    RateLimitExceededError,
    RateLimitResult,
    RateLimitReason,
    DailyQuota,
    get_quota_for_role,
)
from .human_patterns import (
    HumanBehaviorSimulator,
    HumanActivityPattern,
    AvailabilityResult,
    AvailabilityStatus,
    get_default_pattern_for_role,
)

# Communication channel selection
from .communication_channel import (
    CommunicationChannel,
    CommunicationChannelSelector,
    MessageContext,
    MessageType,
    MessageTemplates,
    ChannelDecision,
    decide_communication_channel,
)

__all__ = [
    # Agent loop
    "tick_agent",
    "check_inbox",
    "check_calendar",
    "process_email",
    "should_respond_to_email",
    "behavior_engine",
    # Pulse system
    "PulseEvent",
    "DailyRoutine",
    "PulseExecution",
    "PulseExecutor",
    "get_routine_for_role",
    "ROLE_ROUTINES",
    # KAM workflow
    "KeyAccountManagerWorkflow",
    # Rate limiting
    "AgentRateLimiter",
    "RateLimitedMCPClient",
    "RateLimitExceededError",
    "RateLimitResult",
    "RateLimitReason",
    "DailyQuota",
    "get_quota_for_role",
    # Human behavior patterns
    "HumanBehaviorSimulator",
    "HumanActivityPattern",
    "AvailabilityResult",
    "AvailabilityStatus",
    "get_default_pattern_for_role",
    # Communication channel selection
    "CommunicationChannel",
    "CommunicationChannelSelector",
    "MessageContext",
    "MessageType",
    "MessageTemplates",
    "ChannelDecision",
    "decide_communication_channel",
]
