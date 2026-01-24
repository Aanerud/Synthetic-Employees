"""Scheduler for managing agent tick cycles and work hours."""

import os
import random
import time
from datetime import datetime, timedelta
from typing import List, Optional

import pytz

from src.agents.agent_registry import AgentConfig, AgentRegistry
from src.agents.roles import get_role


class WorkScheduler:
    """Manages when agents are active and schedules their tick cycles."""

    def __init__(
        self,
        agent_registry: AgentRegistry,
        tick_interval_minutes: Optional[int] = None,
        work_start_hour: Optional[int] = None,
        work_end_hour: Optional[int] = None,
        timezone: Optional[str] = None,
        randomize_ticks: bool = True,
        time_acceleration: float = 1.0,
    ):
        self.agent_registry = agent_registry
        self.tick_interval_minutes = tick_interval_minutes or int(
            os.getenv("TICK_INTERVAL_MINUTES", "5")
        )
        self.work_start_hour = work_start_hour or int(os.getenv("WORK_START_HOUR", "9"))
        self.work_end_hour = work_end_hour or int(os.getenv("WORK_END_HOUR", "17"))
        self.timezone = pytz.timezone(timezone or os.getenv("TIMEZONE", "America/Los_Angeles"))
        self.randomize_ticks = randomize_ticks and os.getenv("RANDOMIZE_TICKS", "true").lower() == "true"
        self.time_acceleration = time_acceleration or float(os.getenv("TIME_ACCELERATION", "1.0"))
        self.enable_weekends = os.getenv("ENABLE_WEEKENDS", "false").lower() == "true"

        # Track last tick time for each agent
        self.last_tick: dict[str, datetime] = {}

    def is_work_hours(self, dt: Optional[datetime] = None) -> bool:
        """Check if current time is within work hours."""
        if dt is None:
            dt = datetime.now(self.timezone)
        else:
            dt = dt.astimezone(self.timezone)

        # Check weekends
        if not self.enable_weekends and dt.weekday() >= 5:  # Saturday=5, Sunday=6
            return False

        # Check hours
        hour = dt.hour
        return self.work_start_hour <= hour < self.work_end_hour

    def get_tick_interval(self, agent: AgentConfig) -> int:
        """Get tick interval for an agent based on their role."""
        role = get_role(agent.role)

        # Base interval from role
        base_interval = role.email_check_frequency_minutes

        # Add randomization (±20%)
        if self.randomize_ticks:
            variance = base_interval * 0.2
            interval = base_interval + random.uniform(-variance, variance)
            return max(1, int(interval))

        return base_interval

    def should_tick(self, agent: AgentConfig, current_time: datetime) -> bool:
        """Determine if an agent should tick now."""
        # Check work hours
        if not self.is_work_hours(current_time):
            return False

        # Get last tick time
        last_tick = self.last_tick.get(agent.email)

        # First tick?
        if last_tick is None:
            return True

        # Check if enough time has passed
        interval_minutes = self.get_tick_interval(agent)
        next_tick_time = last_tick + timedelta(minutes=interval_minutes)

        return current_time >= next_tick_time

    def get_agents_to_tick(self) -> List[AgentConfig]:
        """Get list of agents that should tick now."""
        current_time = datetime.now(self.timezone)
        agents_to_tick = []

        for agent in self.agent_registry.agents:
            if self.should_tick(agent, current_time):
                agents_to_tick.append(agent)

        return agents_to_tick

    def mark_ticked(self, agent: AgentConfig) -> None:
        """Mark an agent as ticked."""
        self.last_tick[agent.email] = datetime.now(self.timezone)

    def sleep_until_next_check(self) -> None:
        """Sleep until next scheduler check."""
        # Check every minute in real-time
        real_sleep_seconds = 60.0 / self.time_acceleration
        time.sleep(real_sleep_seconds)

    def get_status(self) -> dict:
        """Get scheduler status."""
        current_time = datetime.now(self.timezone)
        is_work_time = self.is_work_hours(current_time)

        return {
            "current_time": current_time.isoformat(),
            "is_work_hours": is_work_time,
            "work_hours": f"{self.work_start_hour}:00 - {self.work_end_hour}:00",
            "timezone": str(self.timezone),
            "agents_total": len(self.agent_registry.agents),
            "agents_ticked": len(self.last_tick),
            "time_acceleration": self.time_acceleration,
        }

    def get_next_work_start(self) -> datetime:
        """Get the next time work hours start."""
        current_time = datetime.now(self.timezone)

        # If currently in work hours, return next day's start
        if self.is_work_hours(current_time):
            next_day = current_time + timedelta(days=1)
            next_start = next_day.replace(
                hour=self.work_start_hour, minute=0, second=0, microsecond=0
            )
        else:
            # Try today first
            next_start = current_time.replace(
                hour=self.work_start_hour, minute=0, second=0, microsecond=0
            )
            if next_start <= current_time:
                # Work hours already passed today, try tomorrow
                next_day = current_time + timedelta(days=1)
                next_start = next_day.replace(
                    hour=self.work_start_hour, minute=0, second=0, microsecond=0
                )

        # Skip weekends if needed
        while not self.enable_weekends and next_start.weekday() >= 5:
            next_start += timedelta(days=1)

        return next_start

    def wait_for_work_hours(self) -> None:
        """Block until work hours begin."""
        if self.is_work_hours():
            return

        next_start = self.get_next_work_start()
        current_time = datetime.now(self.timezone)
        wait_seconds = (next_start - current_time).total_seconds()

        print(f"\n⏰ Outside work hours. Next work starts at {next_start.strftime('%Y-%m-%d %H:%M %Z')}")
        print(f"   Waiting {wait_seconds / 3600:.1f} hours...\n")

        # Sleep with time acceleration
        real_wait_seconds = wait_seconds / self.time_acceleration
        time.sleep(real_wait_seconds)
