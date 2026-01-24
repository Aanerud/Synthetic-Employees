"""Rate limiter for synthetic employee actions.

Implements daily quotas, minimum intervals, and human-like delays
to ensure agents behave naturally and don't overwhelm APIs.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, Optional, TypeVar, Union

from .human_patterns import HumanBehaviorSimulator, get_default_pattern_for_role

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RateLimitReason(Enum):
    """Reason for rate limiting."""
    ALLOWED = "allowed"
    DAILY_QUOTA_EXCEEDED = "daily_quota_exceeded"
    HOURLY_QUOTA_EXCEEDED = "hourly_quota_exceeded"
    MIN_INTERVAL_NOT_MET = "min_interval_not_met"
    HUMAN_BREAK = "human_break"
    OUTSIDE_HOURS = "outside_hours"


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""
    allowed: bool
    reason: RateLimitReason
    delay_seconds: float = 0.0
    message: str = ""
    quota_remaining: Optional[int] = None


@dataclass
class DailyQuota:
    """Daily quota limits for an agent.

    Defines maximum actions per day/hour and minimum intervals
    between actions to simulate realistic work patterns.
    """

    # Email limits
    max_emails_per_day: int = 50
    min_seconds_between_emails: float = 30.0

    # API call limits (general MCP calls)
    max_api_calls_per_day: int = 500
    max_api_calls_per_hour: int = 60
    min_seconds_between_api_calls: float = 2.0

    # Teams message limits
    max_teams_messages_per_day: int = 100
    min_seconds_between_teams_messages: float = 10.0

    # Calendar limits
    max_calendar_changes_per_day: int = 20
    min_seconds_between_calendar_changes: float = 60.0


# Role-specific quota presets
ROLE_QUOTAS: Dict[str, DailyQuota] = {
    "key_account_manager": DailyQuota(
        max_emails_per_day=80,
        min_seconds_between_emails=20.0,
        max_api_calls_per_day=800,
        max_teams_messages_per_day=150,
    ),
    "developer": DailyQuota(
        max_emails_per_day=30,
        min_seconds_between_emails=60.0,
        max_api_calls_per_day=400,
        max_teams_messages_per_day=80,
    ),
    "project_manager": DailyQuota(
        max_emails_per_day=60,
        min_seconds_between_emails=30.0,
        max_api_calls_per_day=600,
        max_teams_messages_per_day=120,
    ),
    "executive": DailyQuota(
        max_emails_per_day=40,
        min_seconds_between_emails=45.0,
        max_api_calls_per_day=300,
        max_teams_messages_per_day=50,
    ),
    "default": DailyQuota(),
}


def get_quota_for_role(role: str) -> DailyQuota:
    """Get appropriate quota for a role."""
    role_lower = role.lower()

    if any(x in role_lower for x in ["account manager", "kam", "sales"]):
        return ROLE_QUOTAS["key_account_manager"]
    if any(x in role_lower for x in ["developer", "engineer"]):
        return ROLE_QUOTAS["developer"]
    if any(x in role_lower for x in ["project manager", "pm", "scrum"]):
        return ROLE_QUOTAS["project_manager"]
    if any(x in role_lower for x in ["executive", "director", "vp", "ceo"]):
        return ROLE_QUOTAS["executive"]

    return ROLE_QUOTAS["default"]


@dataclass
class AgentActivityState:
    """Tracks agent activity for rate limiting."""

    agent_email: str
    quota_reset_date: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d")
    )

    # Daily counters
    emails_sent_today: int = 0
    api_calls_today: int = 0
    teams_messages_today: int = 0
    calendar_changes_today: int = 0

    # Hourly counters (reset each hour)
    api_calls_this_hour: int = 0
    hour_reset_time: Optional[datetime] = None

    # Timestamps for minimum intervals
    last_email_at: Optional[datetime] = None
    last_api_call_at: Optional[datetime] = None
    last_teams_message_at: Optional[datetime] = None
    last_calendar_change_at: Optional[datetime] = None

    def reset_if_needed(self) -> bool:
        """Reset daily counters if it's a new day. Returns True if reset."""
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self.quota_reset_date:
            self.quota_reset_date = today
            self.emails_sent_today = 0
            self.api_calls_today = 0
            self.teams_messages_today = 0
            self.calendar_changes_today = 0
            logger.info(f"Daily quotas reset for {self.agent_email}")
            return True
        return False

    def reset_hourly_if_needed(self) -> bool:
        """Reset hourly counters if needed. Returns True if reset."""
        now = datetime.now()

        if self.hour_reset_time is None:
            self.hour_reset_time = now.replace(minute=0, second=0, microsecond=0)
            return True

        # Reset if we've moved to a new hour
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        if current_hour > self.hour_reset_time:
            self.hour_reset_time = current_hour
            self.api_calls_this_hour = 0
            return True

        return False


class AgentRateLimiter:
    """Rate limiter for agent actions.

    Enforces daily quotas, hourly limits, and minimum intervals
    between actions. Also integrates human behavior simulation
    for natural work patterns.
    """

    def __init__(
        self,
        agent_email: str,
        role: str = "default",
        quota: Optional[DailyQuota] = None,
        behavior_simulator: Optional[HumanBehaviorSimulator] = None,
        enable_human_patterns: bool = True,
    ):
        """
        Initialize the rate limiter.

        Args:
            agent_email: Email of the agent
            role: Role name for quota selection
            quota: Custom quota (overrides role-based selection)
            behavior_simulator: Custom behavior simulator
            enable_human_patterns: Whether to simulate human breaks/delays
        """
        self.agent_email = agent_email
        self.role = role
        self.quota = quota or get_quota_for_role(role)
        self.state = AgentActivityState(agent_email=agent_email)
        self.enable_human_patterns = enable_human_patterns

        if enable_human_patterns:
            self.behavior = behavior_simulator or HumanBehaviorSimulator(
                get_default_pattern_for_role(role)
            )
        else:
            self.behavior = None

    def check_api_call(self) -> RateLimitResult:
        """
        Check if an API call is allowed.

        Returns:
            RateLimitResult with allowed status and any required delay
        """
        self.state.reset_if_needed()
        self.state.reset_hourly_if_needed()

        # Check human availability first
        if self.enable_human_patterns and self.behavior:
            availability = self.behavior.check_availability()
            if not availability.available:
                return RateLimitResult(
                    allowed=False,
                    reason=RateLimitReason.HUMAN_BREAK,
                    message=availability.reason,
                )

        # Check daily quota
        if self.state.api_calls_today >= self.quota.max_api_calls_per_day:
            return RateLimitResult(
                allowed=False,
                reason=RateLimitReason.DAILY_QUOTA_EXCEEDED,
                message=f"Daily API quota ({self.quota.max_api_calls_per_day}) exceeded",
                quota_remaining=0,
            )

        # Check hourly quota
        if self.state.api_calls_this_hour >= self.quota.max_api_calls_per_hour:
            # Calculate time until next hour
            now = datetime.now()
            next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            delay = (next_hour - now).total_seconds()

            return RateLimitResult(
                allowed=False,
                reason=RateLimitReason.HOURLY_QUOTA_EXCEEDED,
                delay_seconds=delay,
                message=f"Hourly API quota ({self.quota.max_api_calls_per_hour}) exceeded",
                quota_remaining=0,
            )

        # Check minimum interval
        if self.state.last_api_call_at:
            elapsed = (datetime.now() - self.state.last_api_call_at).total_seconds()
            if elapsed < self.quota.min_seconds_between_api_calls:
                delay = self.quota.min_seconds_between_api_calls - elapsed
                return RateLimitResult(
                    allowed=True,  # Allowed but with delay
                    reason=RateLimitReason.MIN_INTERVAL_NOT_MET,
                    delay_seconds=delay,
                    message=f"Waiting {delay:.1f}s for minimum interval",
                    quota_remaining=self.quota.max_api_calls_per_day - self.state.api_calls_today,
                )

        # Add thinking delay if human patterns enabled
        delay = 0.0
        if self.enable_human_patterns and self.behavior:
            delay = self.behavior.get_thinking_delay()

        return RateLimitResult(
            allowed=True,
            reason=RateLimitReason.ALLOWED,
            delay_seconds=delay,
            message="API call allowed",
            quota_remaining=self.quota.max_api_calls_per_day - self.state.api_calls_today,
        )

    def check_email_send(self) -> RateLimitResult:
        """
        Check if sending an email is allowed.

        Returns:
            RateLimitResult with allowed status and any required delay
        """
        self.state.reset_if_needed()

        # Check human availability
        if self.enable_human_patterns and self.behavior:
            availability = self.behavior.check_availability()
            if not availability.available:
                return RateLimitResult(
                    allowed=False,
                    reason=RateLimitReason.HUMAN_BREAK,
                    message=availability.reason,
                )

        # Check daily quota
        if self.state.emails_sent_today >= self.quota.max_emails_per_day:
            return RateLimitResult(
                allowed=False,
                reason=RateLimitReason.DAILY_QUOTA_EXCEEDED,
                message=f"Daily email quota ({self.quota.max_emails_per_day}) exceeded",
                quota_remaining=0,
            )

        # Check minimum interval
        if self.state.last_email_at:
            elapsed = (datetime.now() - self.state.last_email_at).total_seconds()
            if elapsed < self.quota.min_seconds_between_emails:
                delay = self.quota.min_seconds_between_emails - elapsed
                return RateLimitResult(
                    allowed=True,
                    reason=RateLimitReason.MIN_INTERVAL_NOT_MET,
                    delay_seconds=delay,
                    message=f"Waiting {delay:.1f}s for minimum email interval",
                    quota_remaining=self.quota.max_emails_per_day - self.state.emails_sent_today,
                )

        # Add response delay for email composition
        delay = 0.0
        if self.enable_human_patterns and self.behavior:
            delay = self.behavior.get_response_delay(message_length=500)  # Assume ~500 char email

        return RateLimitResult(
            allowed=True,
            reason=RateLimitReason.ALLOWED,
            delay_seconds=delay,
            message="Email send allowed",
            quota_remaining=self.quota.max_emails_per_day - self.state.emails_sent_today,
        )

    def check_teams_message(self) -> RateLimitResult:
        """Check if sending a Teams message is allowed."""
        self.state.reset_if_needed()

        if self.enable_human_patterns and self.behavior:
            availability = self.behavior.check_availability()
            if not availability.available:
                return RateLimitResult(
                    allowed=False,
                    reason=RateLimitReason.HUMAN_BREAK,
                    message=availability.reason,
                )

        if self.state.teams_messages_today >= self.quota.max_teams_messages_per_day:
            return RateLimitResult(
                allowed=False,
                reason=RateLimitReason.DAILY_QUOTA_EXCEEDED,
                message=f"Daily Teams message quota ({self.quota.max_teams_messages_per_day}) exceeded",
                quota_remaining=0,
            )

        if self.state.last_teams_message_at:
            elapsed = (datetime.now() - self.state.last_teams_message_at).total_seconds()
            if elapsed < self.quota.min_seconds_between_teams_messages:
                delay = self.quota.min_seconds_between_teams_messages - elapsed
                return RateLimitResult(
                    allowed=True,
                    reason=RateLimitReason.MIN_INTERVAL_NOT_MET,
                    delay_seconds=delay,
                    message=f"Waiting {delay:.1f}s for minimum Teams interval",
                    quota_remaining=self.quota.max_teams_messages_per_day - self.state.teams_messages_today,
                )

        delay = 0.0
        if self.enable_human_patterns and self.behavior:
            delay = self.behavior.get_response_delay(message_length=100)

        return RateLimitResult(
            allowed=True,
            reason=RateLimitReason.ALLOWED,
            delay_seconds=delay,
            message="Teams message allowed",
            quota_remaining=self.quota.max_teams_messages_per_day - self.state.teams_messages_today,
        )

    def record_api_call(self) -> None:
        """Record that an API call was made."""
        self.state.api_calls_today += 1
        self.state.api_calls_this_hour += 1
        self.state.last_api_call_at = datetime.now()

    def record_email_sent(self) -> None:
        """Record that an email was sent."""
        self.state.emails_sent_today += 1
        self.state.last_email_at = datetime.now()

    def record_teams_message(self) -> None:
        """Record that a Teams message was sent."""
        self.state.teams_messages_today += 1
        self.state.last_teams_message_at = datetime.now()

    def record_calendar_change(self) -> None:
        """Record that a calendar change was made."""
        self.state.calendar_changes_today += 1
        self.state.last_calendar_change_at = datetime.now()

    def wait_if_needed(self, result: RateLimitResult) -> None:
        """
        Wait for the specified delay if needed.

        Args:
            result: RateLimitResult from a check method
        """
        if result.delay_seconds > 0:
            logger.debug(
                f"Rate limiter delay for {self.agent_email}: {result.delay_seconds:.1f}s "
                f"({result.message})"
            )
            time.sleep(result.delay_seconds)

    def get_status(self) -> Dict[str, Any]:
        """Get current rate limiter status."""
        self.state.reset_if_needed()
        self.state.reset_hourly_if_needed()

        return {
            "agent_email": self.agent_email,
            "role": self.role,
            "quota_reset_date": self.state.quota_reset_date,
            "emails": {
                "sent_today": self.state.emails_sent_today,
                "quota": self.quota.max_emails_per_day,
                "remaining": self.quota.max_emails_per_day - self.state.emails_sent_today,
            },
            "api_calls": {
                "today": self.state.api_calls_today,
                "this_hour": self.state.api_calls_this_hour,
                "daily_quota": self.quota.max_api_calls_per_day,
                "hourly_quota": self.quota.max_api_calls_per_hour,
                "daily_remaining": self.quota.max_api_calls_per_day - self.state.api_calls_today,
                "hourly_remaining": self.quota.max_api_calls_per_hour - self.state.api_calls_this_hour,
            },
            "teams_messages": {
                "sent_today": self.state.teams_messages_today,
                "quota": self.quota.max_teams_messages_per_day,
                "remaining": self.quota.max_teams_messages_per_day - self.state.teams_messages_today,
            },
            "human_patterns_enabled": self.enable_human_patterns,
        }


class RateLimitedMCPClient:
    """Wrapper that adds rate limiting to an MCP client.

    This wrapper automatically checks rate limits before API calls
    and records activity after successful calls.
    """

    def __init__(
        self,
        mcp_client: Any,
        rate_limiter: AgentRateLimiter,
    ):
        """
        Initialize rate-limited client wrapper.

        Args:
            mcp_client: The underlying MCP client (stdio or HTTP)
            rate_limiter: Rate limiter to use
        """
        self._client = mcp_client
        self._rate_limiter = rate_limiter

    def __getattr__(self, name: str) -> Any:
        """Proxy attribute access to underlying client."""
        attr = getattr(self._client, name)

        if callable(attr):
            return self._wrap_method(name, attr)

        return attr

    def _wrap_method(self, name: str, method: Callable) -> Callable:
        """Wrap a client method with rate limiting."""

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Determine action type and check rate limit
            if name in ("send_mail", "reply_to_mail"):
                result = self._rate_limiter.check_email_send()
                if not result.allowed and result.reason != RateLimitReason.MIN_INTERVAL_NOT_MET:
                    raise RateLimitExceededError(result.message, result)
                self._rate_limiter.wait_if_needed(result)

                response = method(*args, **kwargs)
                self._rate_limiter.record_email_sent()
                return response

            elif name in ("send_channel_message", "send_chat_message", "reply_to_channel_message"):
                result = self._rate_limiter.check_teams_message()
                if not result.allowed and result.reason != RateLimitReason.MIN_INTERVAL_NOT_MET:
                    raise RateLimitExceededError(result.message, result)
                self._rate_limiter.wait_if_needed(result)

                response = method(*args, **kwargs)
                self._rate_limiter.record_teams_message()
                return response

            elif name in ("create_event", "update_event", "delete_event", "respond_to_event"):
                result = self._rate_limiter.check_api_call()
                if not result.allowed and result.reason != RateLimitReason.MIN_INTERVAL_NOT_MET:
                    raise RateLimitExceededError(result.message, result)
                self._rate_limiter.wait_if_needed(result)

                response = method(*args, **kwargs)
                self._rate_limiter.record_calendar_change()
                self._rate_limiter.record_api_call()
                return response

            else:
                # General API call
                result = self._rate_limiter.check_api_call()
                if not result.allowed and result.reason != RateLimitReason.MIN_INTERVAL_NOT_MET:
                    raise RateLimitExceededError(result.message, result)
                self._rate_limiter.wait_if_needed(result)

                response = method(*args, **kwargs)
                self._rate_limiter.record_api_call()
                return response

        return wrapper

    @property
    def rate_limiter(self) -> AgentRateLimiter:
        """Access the rate limiter directly."""
        return self._rate_limiter


class RateLimitExceededError(Exception):
    """Raised when rate limit is exceeded and action cannot proceed."""

    def __init__(self, message: str, result: RateLimitResult):
        super().__init__(message)
        self.result = result
