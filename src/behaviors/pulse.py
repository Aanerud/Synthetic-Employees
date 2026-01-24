"""Pulse system data models for NPC-like agent behaviors.

A pulse represents a scheduled behavior that fires based on time windows
and probability, making agents behave like NPCs in a game.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class TimeOfDay(Enum):
    """Time of day periods for pulse scheduling."""
    EARLY_MORNING = "early_morning"  # 6am-9am
    MORNING = "morning"              # 9am-12pm
    MIDDAY = "midday"                # 12pm-2pm
    AFTERNOON = "afternoon"          # 2pm-5pm
    EVENING = "evening"              # 5pm-7pm


# Time window definitions (start_hour, end_hour)
TIME_WINDOWS: Dict[TimeOfDay, Tuple[int, int]] = {
    TimeOfDay.EARLY_MORNING: (6, 9),
    TimeOfDay.MORNING: (9, 12),
    TimeOfDay.MIDDAY: (12, 14),
    TimeOfDay.AFTERNOON: (14, 17),
    TimeOfDay.EVENING: (17, 19),
}


@dataclass
class PulseEvent:
    """
    A single pulse event that can fire during an agent's day.

    Attributes:
        name: Unique identifier for this pulse
        time_window: (start_hour, end_hour) in 24h format
        probability: 0.0-1.0 chance of firing when conditions are met
        action: The action to execute (e.g., "check_external_emails", "post_standup")
        params: Additional parameters for the action
        cooldown_minutes: Minimum time between executions
        requires_workday: Whether this pulse only fires on workdays
    """
    name: str
    time_window: Tuple[int, int]
    probability: float
    action: str
    params: Dict[str, Any] = field(default_factory=dict)
    cooldown_minutes: int = 60
    requires_workday: bool = True

    def is_in_time_window(self, hour: int) -> bool:
        """Check if the given hour falls within this pulse's time window."""
        start, end = self.time_window
        return start <= hour < end

    def should_fire(self, hour: int, last_executed: Optional[datetime] = None) -> bool:
        """
        Determine if this pulse should fire.

        Returns True if:
        - Current hour is within time window
        - Cooldown period has passed since last execution
        - Random roll succeeds based on probability
        """
        if not self.is_in_time_window(hour):
            return False

        # Check cooldown
        if last_executed:
            minutes_since = (datetime.now() - last_executed).total_seconds() / 60
            if minutes_since < self.cooldown_minutes:
                return False

        # Probability check is done by executor (requires random)
        return True


@dataclass
class DailyRoutine:
    """
    A complete daily routine for a role, organized by time of day.

    Attributes:
        role: The role this routine applies to
        pulses: List of all pulse events for this routine
        description: Human-readable description of this routine
    """
    role: str
    pulses: List[PulseEvent] = field(default_factory=list)
    description: str = ""

    def get_pulses_for_hour(self, hour: int) -> List[PulseEvent]:
        """Get all pulses that could fire at the given hour."""
        return [p for p in self.pulses if p.is_in_time_window(hour)]

    def get_pulses_for_time_of_day(self, time_of_day: TimeOfDay) -> List[PulseEvent]:
        """Get all pulses for a specific time of day period."""
        start, end = TIME_WINDOWS[time_of_day]
        return [
            p for p in self.pulses
            if p.time_window[0] >= start and p.time_window[1] <= end
        ]

    @property
    def morning_pulses(self) -> List[PulseEvent]:
        """Get morning pulses (9am-12pm)."""
        return self.get_pulses_for_time_of_day(TimeOfDay.MORNING)

    @property
    def midday_pulses(self) -> List[PulseEvent]:
        """Get midday pulses (12pm-2pm)."""
        return self.get_pulses_for_time_of_day(TimeOfDay.MIDDAY)

    @property
    def afternoon_pulses(self) -> List[PulseEvent]:
        """Get afternoon pulses (2pm-5pm)."""
        return self.get_pulses_for_time_of_day(TimeOfDay.AFTERNOON)


@dataclass
class PulseExecution:
    """Record of a pulse execution."""
    pulse_name: str
    agent_email: str
    executed_at: datetime
    result: str  # 'success', 'error', 'skipped'
    action_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
