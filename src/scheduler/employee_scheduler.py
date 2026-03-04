"""Per-employee timezone-aware scheduler.

Each employee gets their own schedule based on country/timezone,
role-specific check frequencies, and persona preferences.
Replaces the old single-timezone WorkScheduler.
"""

import hashlib
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from .cultural_schedules import CulturalSchedule, get_cultural_schedule

logger = logging.getLogger(__name__)


@dataclass
class EmployeeSchedule:
    """Schedule configuration for a single employee."""

    email: str
    timezone: str
    country: str
    role: str
    check_frequency_minutes: int
    work_start: time
    work_end: time
    lunch_start: time
    lunch_end: time
    breaks: List[str] = field(default_factory=list)

    # Runtime state
    last_tick_at: Optional[datetime] = None
    next_tick_at: Optional[datetime] = None


class EmployeeScheduler:
    """Manages per-employee timezone-aware scheduling.

    Features:
    - Per-employee timezone from persona/CSV data
    - Cultural work hour schedules per country
    - Role-based check frequencies
    - ±N% randomization on intervals for natural variance
    - Lunch break and fika awareness
    """

    def __init__(
        self,
        variance_percent: int = 20,
        enable_weekends: bool = False,
    ):
        self._schedules: Dict[str, EmployeeSchedule] = {}
        self._variance_percent = variance_percent
        self._enable_weekends = enable_weekends

    def register_employee(
        self,
        email: str,
        country: str,
        role: str,
        check_frequency_minutes: int,
        timezone_override: Optional[str] = None,
        usage_location: Optional[str] = None,
    ) -> EmployeeSchedule:
        """Register an employee with their schedule.

        Uses cultural schedule from country data, with optional
        timezone override from persona.json.
        """
        cultural = get_cultural_schedule(
            country=country, usage_location=usage_location
        )

        tz = timezone_override or cultural.timezone

        def parse_time(s: str) -> time:
            parts = s.split(":")
            return time(int(parts[0]), int(parts[1]))

        schedule = EmployeeSchedule(
            email=email,
            timezone=tz,
            country=country,
            role=role,
            check_frequency_minutes=check_frequency_minutes,
            work_start=parse_time(cultural.work_start),
            work_end=parse_time(cultural.work_end),
            lunch_start=parse_time(cultural.lunch_start),
            lunch_end=parse_time(cultural.lunch_end),
            breaks=cultural.breaks,
        )

        self._schedules[email] = schedule
        return schedule

    def _apply_variance(self, minutes: int, email: str) -> int:
        """Apply randomized variance to an interval.

        Uses seeded random per employee for reproducibility during
        debugging (same employee always gets same variance pattern
        within a session).
        """
        seed = int(
            hashlib.md5(
                f"{email}:{datetime.now().strftime('%Y-%m-%d-%H')}".encode()
            ).hexdigest()[:8],
            16,
        )
        rng = random.Random(seed)
        factor = 1.0 + rng.uniform(
            -self._variance_percent / 100, self._variance_percent / 100
        )
        return max(1, int(minutes * factor))

    def _is_during_break(
        self, schedule: EmployeeSchedule, local_time: datetime
    ) -> bool:
        """Check if current local time falls within lunch or break."""
        t = local_time.time()

        # Lunch break
        if schedule.lunch_start <= t < schedule.lunch_end:
            return True

        # Additional breaks (e.g., fika)
        for brk in schedule.breaks:
            parts = brk.split("-")
            if len(parts) == 2:
                start_parts = parts[0].strip().split(":")
                end_parts = parts[1].strip().split(":")
                brk_start = time(int(start_parts[0]), int(start_parts[1]))
                brk_end = time(int(end_parts[0]), int(end_parts[1]))
                if brk_start <= t < brk_end:
                    return True

        return False

    def is_work_hours(self, email: str) -> bool:
        """Check if it's currently work hours for an employee."""
        schedule = self._schedules.get(email)
        if not schedule:
            return False

        tz = ZoneInfo(schedule.timezone)
        now_local = datetime.now(tz)

        # Weekend check
        if not self._enable_weekends and now_local.weekday() >= 5:
            return False

        t = now_local.time()
        if not (schedule.work_start <= t < schedule.work_end):
            return False

        # During break is still "work hours" but not active time
        return True

    def is_active_time(self, email: str) -> bool:
        """Check if employee should be active (work hours minus breaks)."""
        schedule = self._schedules.get(email)
        if not schedule:
            return False

        if not self.is_work_hours(email):
            return False

        tz = ZoneInfo(schedule.timezone)
        now_local = datetime.now(tz)

        return not self._is_during_break(schedule, now_local)

    def get_employees_due_for_tick(self) -> List[EmployeeSchedule]:
        """Get all employees whose next tick time has passed.

        Only returns employees who are in active work hours.
        """
        due = []
        now = datetime.now()

        for email, schedule in self._schedules.items():
            if not self.is_active_time(email):
                continue

            if schedule.next_tick_at is None:
                # First tick - schedule immediately
                schedule.next_tick_at = now
                due.append(schedule)
            elif now >= schedule.next_tick_at:
                due.append(schedule)

        return due

    def mark_ticked(self, email: str) -> None:
        """Mark an employee as ticked and schedule next tick."""
        schedule = self._schedules.get(email)
        if not schedule:
            return

        now = datetime.now()
        schedule.last_tick_at = now

        # Apply variance to next tick interval
        interval = self._apply_variance(
            schedule.check_frequency_minutes, email
        )
        schedule.next_tick_at = now + timedelta(minutes=interval)

    def get_time_of_day(self, email: str) -> Optional[str]:
        """Get the time-of-day period for an employee's local time.

        Returns: 'early_morning', 'morning', 'midday', 'afternoon',
                 'evening', or None if outside work hours.
        """
        schedule = self._schedules.get(email)
        if not schedule:
            return None

        tz = ZoneInfo(schedule.timezone)
        hour = datetime.now(tz).hour

        if 6 <= hour < 9:
            return "early_morning"
        if 9 <= hour < 12:
            return "morning"
        if 12 <= hour < 14:
            return "midday"
        if 14 <= hour < 17:
            return "afternoon"
        if 17 <= hour < 19:
            return "evening"
        return None

    def get_local_hour(self, email: str) -> Optional[int]:
        """Get the current local hour for an employee."""
        schedule = self._schedules.get(email)
        if not schedule:
            return None
        tz = ZoneInfo(schedule.timezone)
        return datetime.now(tz).hour

    def is_first_check_in_today(self, email: str) -> bool:
        """Check if this would be the employee's first tick today."""
        schedule = self._schedules.get(email)
        if not schedule or not schedule.last_tick_at:
            return True

        tz = ZoneInfo(schedule.timezone)
        now_local = datetime.now(tz)
        last_local = schedule.last_tick_at.astimezone(tz)

        return now_local.date() != last_local.date()

    def is_end_of_day(self, email: str, within_minutes: int = 30) -> bool:
        """Check if employee is within N minutes of their work end."""
        schedule = self._schedules.get(email)
        if not schedule:
            return False

        tz = ZoneInfo(schedule.timezone)
        now_local = datetime.now(tz)
        end_dt = now_local.replace(
            hour=schedule.work_end.hour,
            minute=schedule.work_end.minute,
            second=0,
        )

        diff = (end_dt - now_local).total_seconds() / 60
        return 0 < diff <= within_minutes

    @property
    def employee_count(self) -> int:
        return len(self._schedules)

    def get_active_employees(self) -> List[str]:
        """Get emails of all employees currently in work hours."""
        return [
            email
            for email in self._schedules
            if self.is_active_time(email)
        ]

    def get_schedule(self, email: str) -> Optional[EmployeeSchedule]:
        return self._schedules.get(email)
