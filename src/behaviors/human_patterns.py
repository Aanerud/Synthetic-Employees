"""Human behavior simulation for synthetic employees.

Simulates natural human work patterns including:
- Working hours
- Lunch breaks
- Coffee breaks
- Meeting times
- Thinking delays
"""

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class AvailabilityStatus(Enum):
    """Agent availability status."""
    AVAILABLE = "available"
    LUNCH_BREAK = "lunch_break"
    COFFEE_BREAK = "coffee_break"
    SCHEDULED_BREAK = "scheduled_break"
    MEETING = "meeting"
    OUTSIDE_HOURS = "outside_hours"
    SPONTANEOUS_BREAK = "spontaneous_break"


@dataclass
class AvailabilityResult:
    """Result of availability check."""
    available: bool
    status: AvailabilityStatus
    reason: str
    resume_at: Optional[datetime] = None


@dataclass
class TimeWindow:
    """A time window during the day."""
    start: time
    end: time

    def contains(self, t: time) -> bool:
        """Check if a time falls within this window."""
        return self.start <= t <= self.end


@dataclass
class HumanActivityPattern:
    """Defines human-like activity patterns for an agent.

    These patterns simulate realistic work behavior:
    - Standard work hours (9-5)
    - Lunch breaks (12-2pm, 70% chance)
    - Coffee breaks (10-11am, 3-4pm, 30% chance)
    - Spontaneous breaks (5% chance any time)
    - Thinking delays (3-15 seconds between actions)
    """

    # Work hours
    work_start: time = field(default_factory=lambda: time(9, 0))
    work_end: time = field(default_factory=lambda: time(17, 0))

    # Lunch break (when agent is likely unavailable)
    lunch_window: TimeWindow = field(
        default_factory=lambda: TimeWindow(time(12, 0), time(14, 0))
    )
    lunch_unavailable_chance: float = 0.70  # 70% chance during lunch window

    # Short break windows (coffee, bathroom, etc.)
    break_windows: List[TimeWindow] = field(
        default_factory=lambda: [
            TimeWindow(time(10, 0), time(11, 0)),  # Morning break
            TimeWindow(time(15, 0), time(16, 0)),  # Afternoon break
        ]
    )
    break_chance: float = 0.30  # 30% chance during break windows

    # Spontaneous breaks (coffee run, quick chat, etc.)
    spontaneous_break_chance: float = 0.05  # 5% any time

    # Thinking/processing delay between actions
    min_thinking_seconds: float = 3.0
    max_thinking_seconds: float = 15.0

    # Variation in response times
    response_time_variation: float = 0.2  # ±20%


class HumanBehaviorSimulator:
    """Simulates human-like work behavior for synthetic employees.

    This class determines when agents are "available" to work, simulating
    natural human patterns like lunch breaks, coffee breaks, and the time
    it takes to "think" about a task before acting.
    """

    def __init__(self, pattern: Optional[HumanActivityPattern] = None):
        """
        Initialize the human behavior simulator.

        Args:
            pattern: Activity pattern to use (defaults to standard patterns)
        """
        self.pattern = pattern or HumanActivityPattern()
        self._last_break_check: Optional[datetime] = None
        self._is_on_break = False
        self._break_end: Optional[datetime] = None

    def check_availability(
        self, current_time: Optional[datetime] = None
    ) -> AvailabilityResult:
        """
        Check if the agent is currently available for work.

        This simulates natural work patterns:
        - Outside work hours: unavailable
        - During lunch: 70% chance unavailable
        - During break windows: 30% chance unavailable
        - Any time: 5% chance of spontaneous break

        Args:
            current_time: Time to check (defaults to now)

        Returns:
            AvailabilityResult with availability status and reason
        """
        if current_time is None:
            current_time = datetime.now()

        current_time_only = current_time.time()

        # Check if we're already on a break
        if self._is_on_break and self._break_end:
            if current_time < self._break_end:
                return AvailabilityResult(
                    available=False,
                    status=AvailabilityStatus.SPONTANEOUS_BREAK,
                    reason="Currently on a short break",
                    resume_at=self._break_end,
                )
            else:
                # Break is over
                self._is_on_break = False
                self._break_end = None

        # Check work hours
        if current_time_only < self.pattern.work_start:
            return AvailabilityResult(
                available=False,
                status=AvailabilityStatus.OUTSIDE_HOURS,
                reason=f"Before work hours (starts at {self.pattern.work_start})",
            )

        if current_time_only > self.pattern.work_end:
            return AvailabilityResult(
                available=False,
                status=AvailabilityStatus.OUTSIDE_HOURS,
                reason=f"After work hours (ended at {self.pattern.work_end})",
            )

        # Check lunch break
        if self.pattern.lunch_window.contains(current_time_only):
            if random.random() < self.pattern.lunch_unavailable_chance:
                return AvailabilityResult(
                    available=False,
                    status=AvailabilityStatus.LUNCH_BREAK,
                    reason="Currently at lunch",
                )

        # Check scheduled break windows
        for window in self.pattern.break_windows:
            if window.contains(current_time_only):
                if random.random() < self.pattern.break_chance:
                    return AvailabilityResult(
                        available=False,
                        status=AvailabilityStatus.SCHEDULED_BREAK,
                        reason="Taking a short break",
                    )

        # Check spontaneous break
        if random.random() < self.pattern.spontaneous_break_chance:
            # Start a spontaneous break of 5-15 minutes
            from datetime import timedelta

            break_duration = timedelta(minutes=random.randint(5, 15))
            self._is_on_break = True
            self._break_end = current_time + break_duration

            return AvailabilityResult(
                available=False,
                status=AvailabilityStatus.SPONTANEOUS_BREAK,
                reason="Stepped away for a moment (coffee, quick chat)",
                resume_at=self._break_end,
            )

        # Available
        return AvailabilityResult(
            available=True,
            status=AvailabilityStatus.AVAILABLE,
            reason="Available and working",
        )

    def get_thinking_delay(self) -> float:
        """
        Get a random "thinking" delay to simulate human processing time.

        Humans don't respond instantly - they read, think, and compose.
        This adds a natural delay between 3-15 seconds (configurable).

        Returns:
            Delay in seconds
        """
        base_delay = random.uniform(
            self.pattern.min_thinking_seconds,
            self.pattern.max_thinking_seconds,
        )

        # Add some variation
        variation = base_delay * self.pattern.response_time_variation
        jitter = random.uniform(-variation, variation)

        return max(1.0, base_delay + jitter)  # Minimum 1 second

    def get_response_delay(self, message_length: int = 0) -> float:
        """
        Get delay for composing a response.

        Longer messages take more time to compose. This simulates
        the time it takes a human to read and respond.

        Args:
            message_length: Length of the message to compose

        Returns:
            Delay in seconds
        """
        base = self.get_thinking_delay()

        # Add time based on message length (roughly 50 chars/second typing)
        if message_length > 0:
            typing_time = message_length / 50.0
            # Humans don't type at constant speed
            typing_time *= random.uniform(0.8, 1.5)
            return base + typing_time

        return base

    def should_take_break_before_task(self, task_complexity: str = "normal") -> bool:
        """
        Determine if the agent should take a short break before starting a task.

        Complex tasks might trigger a "let me get some coffee first" response.

        Args:
            task_complexity: 'simple', 'normal', or 'complex'

        Returns:
            True if agent should take a break first
        """
        break_chances = {
            "simple": 0.02,   # 2% chance
            "normal": 0.05,   # 5% chance
            "complex": 0.15,  # 15% chance for complex tasks
        }

        chance = break_chances.get(task_complexity, 0.05)
        return random.random() < chance

    def is_work_hours(self, current_time: Optional[datetime] = None) -> bool:
        """
        Check if current time is within work hours.

        Args:
            current_time: Time to check (defaults to now)

        Returns:
            True if within work hours
        """
        if current_time is None:
            current_time = datetime.now()

        current_time_only = current_time.time()
        return self.pattern.work_start <= current_time_only <= self.pattern.work_end

    def get_next_available_time(
        self, current_time: Optional[datetime] = None
    ) -> datetime:
        """
        Get the next time the agent will be available.

        Args:
            current_time: Starting time (defaults to now)

        Returns:
            Next available datetime
        """
        if current_time is None:
            current_time = datetime.now()

        # If we're on a break with a known end time, use that
        if self._is_on_break and self._break_end:
            return self._break_end

        # If outside work hours, return next work start
        current_time_only = current_time.time()

        if current_time_only < self.pattern.work_start:
            # Before work - return today's work start
            return current_time.replace(
                hour=self.pattern.work_start.hour,
                minute=self.pattern.work_start.minute,
                second=0,
                microsecond=0,
            )

        if current_time_only > self.pattern.work_end:
            # After work - return tomorrow's work start
            from datetime import timedelta

            tomorrow = current_time + timedelta(days=1)
            return tomorrow.replace(
                hour=self.pattern.work_start.hour,
                minute=self.pattern.work_start.minute,
                second=0,
                microsecond=0,
            )

        # During work hours, likely available now
        return current_time


def get_default_pattern_for_role(role: str) -> HumanActivityPattern:
    """
    Get human behavior patterns appropriate for a role.

    Different roles have different work patterns:
    - Executives: Earlier hours, shorter lunch
    - Developers: Later hours, longer focus periods
    - Support: Standard hours, shorter breaks

    Args:
        role: Role name or type

    Returns:
        HumanActivityPattern appropriate for the role
    """
    role_lower = role.lower()

    if any(x in role_lower for x in ["executive", "director", "vp", "ceo", "cto"]):
        return HumanActivityPattern(
            work_start=time(8, 0),
            work_end=time(18, 0),
            lunch_window=TimeWindow(time(12, 30), time(13, 30)),
            lunch_unavailable_chance=0.50,  # Often eat at desk
            spontaneous_break_chance=0.03,
        )

    if any(x in role_lower for x in ["developer", "engineer", "programmer"]):
        return HumanActivityPattern(
            work_start=time(9, 30),
            work_end=time(17, 30),
            min_thinking_seconds=5.0,  # Developers think more
            max_thinking_seconds=30.0,
            spontaneous_break_chance=0.08,  # More coffee breaks
        )

    if any(x in role_lower for x in ["support", "customer service"]):
        return HumanActivityPattern(
            lunch_unavailable_chance=0.90,  # Strict lunch coverage
            break_chance=0.15,  # Fewer breaks
            spontaneous_break_chance=0.02,
        )

    if any(x in role_lower for x in ["sales", "account manager", "kam"]):
        return HumanActivityPattern(
            work_start=time(8, 30),
            work_end=time(17, 30),
            lunch_unavailable_chance=0.60,  # Often lunch meetings
            min_thinking_seconds=2.0,  # Quick responses
            max_thinking_seconds=10.0,
        )

    # Default pattern
    return HumanActivityPattern()
