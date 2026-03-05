"""Office Events Engine - random life events that make the company feel alive.

Loads YAML event files from the events/ directory and fires them based on
probability, time windows, and cooldowns. Events generate M365 signals
(Teams messages, emails) directly via MCPClient - no Agency CLI needed.
"""

import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)


@dataclass
class EventAction:
    """Single action within an event."""
    type: str
    templates: List[str] = field(default_factory=list)
    subject_templates: List[str] = field(default_factory=list)
    channel: str = "general"
    to: str = ""
    pick_agents: int = 1
    probability: float = 1.0


@dataclass
class OfficeEvent:
    """Describes a random office event."""
    name: str
    description: str
    category: str
    time_window: Tuple[int, int]
    probability: float
    cooldown_minutes: int
    requires_workday: bool
    scope: str
    actions: List[EventAction]
    exclude_roles: List[str] = field(default_factory=list)
    day_of_week: Optional[int] = None  # 0=Monday, 4=Friday

    # Runtime state
    last_fired: Optional[float] = None


def load_events(events_dir: str = "events") -> List[OfficeEvent]:
    """Load all YAML event files from directory."""
    events_path = Path(events_dir)
    if not events_path.exists():
        return []

    events = []
    for f in sorted(events_path.glob("*.yaml")):
        try:
            with open(f, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)

            actions = []
            for a in data.get("actions", []):
                actions.append(EventAction(
                    type=a.get("type", "teams_channel_message"),
                    templates=a.get("templates", []),
                    subject_templates=a.get("subject_templates", []),
                    channel=a.get("channel", "general"),
                    to=a.get("to", ""),
                    pick_agents=a.get("pick_agents", 1),
                    probability=a.get("probability", 1.0),
                ))

            event = OfficeEvent(
                name=data["name"],
                description=data.get("description", ""),
                category=data.get("category", "office_life"),
                time_window=tuple(data.get("time_window", [9, 17])),
                probability=data.get("probability", 0.05),
                cooldown_minutes=data.get("cooldown_minutes", 1440),
                requires_workday=data.get("requires_workday", True),
                scope=data.get("scope", "all_active"),
                actions=actions,
                exclude_roles=data.get("exclude_roles", []),
                day_of_week=data.get("day_of_week"),
            )
            events.append(event)
            logger.info("Loaded event: %s (%s)", event.name, f.name)

        except Exception as exc:
            logger.warning("Failed to load event %s: %s", f, exc)

    return events


class OfficeEventEngine:
    """Checks and fires random office events each tick cycle."""

    def __init__(self, events_dir: str = "events"):
        self.events = load_events(events_dir)
        self._cooldowns: Dict[str, float] = {}
        logger.info("Loaded %d office events", len(self.events))

    def check_and_fire(
        self,
        active_agents: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Check all events and fire any that trigger.

        Args:
            active_agents: List of dicts with 'email', 'name', 'role', 'department', 'country'.

        Returns:
            List of fired event results with actions to execute.
        """
        now = datetime.now()
        hour = now.hour
        weekday = now.weekday()
        results = []

        for event in self.events:
            # Time window check
            start, end = event.time_window
            if not (start <= hour < end):
                continue

            # Workday check
            if event.requires_workday and weekday >= 5:
                continue

            # Day of week check (e.g., Friday only)
            if event.day_of_week is not None and weekday != event.day_of_week:
                continue

            # Cooldown check
            last = self._cooldowns.get(event.name)
            if last and (time.monotonic() - last) < event.cooldown_minutes * 60:
                continue

            # Probability roll
            if random.random() > event.probability:
                continue

            # Event fires!
            logger.info("Event fired: %s", event.name)
            self._cooldowns[event.name] = time.monotonic()

            # Select affected agents
            affected = self._select_agents(event, active_agents)

            # Build action list
            for action in event.actions:
                # Pick random agents for this action
                actors = random.sample(
                    affected,
                    min(action.pick_agents, len(affected))
                ) if affected else []

                for agent in actors:
                    if random.random() > action.probability:
                        continue

                    template = random.choice(action.templates) if action.templates else ""
                    # Replace placeholders
                    message = template.replace("{Name}", agent.get("name", ""))
                    message = message.replace("{OfficeLocation}", agent.get("country", ""))
                    if "{RandomColleague}" in message and affected:
                        colleague = random.choice([a for a in affected if a["email"] != agent["email"]] or affected)
                        message = message.replace("{RandomColleague}", colleague.get("name", "someone"))

                    subject = ""
                    if action.subject_templates:
                        subject = random.choice(action.subject_templates)
                        subject = subject.replace("{Name}", agent.get("name", ""))

                    results.append({
                        "event": event.name,
                        "category": event.category,
                        "agent_email": agent["email"],
                        "agent_name": agent.get("name", ""),
                        "action_type": action.type,
                        "channel": action.channel,
                        "to": action.to,
                        "message": message,
                        "subject": subject,
                    })

        return results

    def _select_agents(
        self, event: OfficeEvent, active_agents: List[Dict]
    ) -> List[Dict]:
        """Select agents affected by event based on scope."""
        candidates = active_agents

        # Filter excluded roles
        if event.exclude_roles:
            candidates = [
                a for a in candidates
                if a.get("role", "") not in event.exclude_roles
            ]

        scope = event.scope

        if scope == "all_active":
            return candidates

        if scope.startswith("random:"):
            count = int(scope.split(":")[1])
            return random.sample(candidates, min(count, len(candidates)))

        if scope.startswith("department:"):
            dept = scope.split(":")[1]
            return [a for a in candidates if a.get("department", "") == dept]

        if scope.startswith("role:"):
            role = scope.split(":")[1]
            return [a for a in candidates if role.lower() in a.get("role", "").lower()]

        if scope.startswith("country:"):
            country = scope.split(":")[1]
            return [a for a in candidates if a.get("country", "") == country]

        return candidates
