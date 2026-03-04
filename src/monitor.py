#!/usr/bin/env python3
"""Live terminal monitor for Synthetic Employees.

Shows all employees, their timezone, status, and current activity
in a live-updating terminal display.

Usage:
    python -m src.monitor                    # Monitor only (read-only)
    python -m src.monitor --run              # Monitor + run agents
    python -m src.monitor --run --duration 30m
"""

import argparse
import asyncio
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict

import yaml
from dotenv import load_dotenv

load_dotenv()

from src.agents.agent_registry import AgentRegistry
from src.agents.persona_loader import PersonaRegistry
from src.scheduler.employee_scheduler import EmployeeScheduler
from src.scheduler.cultural_schedules import get_cultural_schedule, COUNTRY_NAME_TO_CODE


# ANSI colors
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
WHITE = "\033[37m"
BG_GREEN = "\033[42m"
BG_YELLOW = "\033[43m"
BG_RED = "\033[41m"
BG_BLUE = "\033[44m"

# Status indicators
STATUS_ICONS = {
    "idle": f"{DIM}--{RESET}",
    "active": f"{GREEN}OK{RESET}",
    "thinking": f"{YELLOW}AI{RESET}",
    "executing": f"{CYAN}MX{RESET}",
    "error": f"{RED}!!{RESET}",
    "sleeping": f"{DIM}zz{RESET}",
    "lunch": f"{DIM}LN{RESET}",
    "off": f"{DIM}  {RESET}",
}


def load_config(path: str = "config.yaml") -> dict:
    if Path(path).exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


def load_csv_countries() -> Dict[str, str]:
    """Load email -> country from CSV."""
    import csv
    mapping = {}
    csv_path = Path("textcraft-europe.csv")
    if csv_path.exists():
        with open(csv_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                email = row.get("email", "").lower()
                country = row.get("country", "")
                if email and country:
                    mapping[email] = country
    return mapping


def get_country_flag(country: str) -> str:
    """Get flag emoji for country."""
    flags = {
        "Italy": "IT", "Sweden": "SE", "France": "FR", "Germany": "DE",
        "Spain": "ES", "Poland": "PL", "Netherlands": "NL", "Belgium": "BE",
        "Portugal": "PT", "Austria": "AT", "Denmark": "DK", "Ireland": "IE",
        "Switzerland": "CH", "United Kingdom": "GB",
    }
    code = flags.get(country, "")
    if code and len(code) == 2:
        return chr(0x1F1E6 + ord(code[0]) - ord('A')) + chr(0x1F1E6 + ord(code[1]) - ord('A'))
    return "  "


class EmployeeMonitor:
    """Live terminal monitor for all employees."""

    def __init__(self):
        self.personas = PersonaRegistry()
        self.scheduler = EmployeeScheduler()
        self.csv_countries = load_csv_countries()
        self.agent_status: Dict[str, str] = {}  # email -> status string
        self.agent_action: Dict[str, str] = {}  # email -> current action
        self.stats = {"ticks": 0, "emails": 0, "errors": 0, "active": 0}
        self.running = True

    def initialize(self):
        count = self.personas.load_all()

        for persona in self.personas:
            country = self.csv_countries.get(persona.email.lower(), "United Kingdom")
            tz_override = persona.timezone
            if tz_override == "Europe/London" and country != "United Kingdom":
                tz_override = None

            self.scheduler.register_employee(
                email=persona.email,
                country=country,
                role=persona.role or persona.job_title,
                check_frequency_minutes=persona.email_check_frequency_minutes,
                timezone_override=tz_override,
            )
            self.agent_status[persona.email] = "idle"
            self.agent_action[persona.email] = ""

        return count

    def render(self):
        """Render the full monitor display."""
        # Clear screen
        sys.stdout.write("\033[2J\033[H")

        now = datetime.now()
        active = self.scheduler.get_active_employees()
        self.stats["active"] = len(active)

        # Header
        print(f"{BOLD}Synthetic Employees Monitor{RESET}")
        print(f"{DIM}{now.strftime('%Y-%m-%d %H:%M:%S')} | "
              f"{len(active)}/{self.scheduler.employee_count} active | "
              f"Ticks: {self.stats['ticks']} | "
              f"Emails: {self.stats['emails']} | "
              f"Errors: {self.stats['errors']}{RESET}")
        print(f"{DIM}{'─' * 100}{RESET}")

        # Column headers
        print(f"  {'Name':<25s} {'Role':<22s} {'Country':<5s} {'TZ Time':<8s} {'St':>2s}  {'Action':<30s}")
        print(f"{DIM}  {'─'*25} {'─'*22} {'─'*5} {'─'*8} {'─'*2}  {'─'*30}{RESET}")

        # Sort: active first, then by name
        from zoneinfo import ZoneInfo
        personas_sorted = sorted(
            self.personas.list_all(),
            key=lambda p: (
                0 if p.email in active else 1,
                p.name,
            ),
        )

        for persona in personas_sorted:
            email = persona.email
            country = self.csv_countries.get(email.lower(), "United Kingdom")
            code = COUNTRY_NAME_TO_CODE.get(country, "GB")
            flag = get_country_flag(country)

            # Get local time
            schedule = self.scheduler.get_schedule(email)
            if schedule:
                try:
                    tz = ZoneInfo(schedule.timezone)
                    local_time = datetime.now(tz).strftime("%H:%M")
                except Exception:
                    local_time = "??:??"
            else:
                local_time = "??:??"

            # Status
            is_active = email in active
            is_lunch = schedule and self.scheduler._is_during_break(schedule, datetime.now(ZoneInfo(schedule.timezone))) if schedule else False

            if not self.scheduler.is_work_hours(email):
                status = STATUS_ICONS["off"]
            elif is_lunch:
                status = STATUS_ICONS["lunch"]
            elif self.agent_status.get(email) == "error":
                status = STATUS_ICONS["error"]
            elif self.agent_status.get(email) == "thinking":
                status = STATUS_ICONS["thinking"]
            elif self.agent_status.get(email) == "executing":
                status = STATUS_ICONS["executing"]
            elif is_active:
                status = STATUS_ICONS["active"]
            else:
                status = STATUS_ICONS["sleeping"]

            action = self.agent_action.get(email, "")
            if len(action) > 30:
                action = action[:27] + "..."

            # Dim inactive employees
            style = "" if is_active else DIM
            end_style = RESET if is_active else RESET

            name = persona.name[:25]
            role = (persona.role or persona.job_title)[:22]

            print(f"  {style}{name:<25s} {role:<22s} {flag:<5s} {local_time:<8s}{end_style} {status}  {style}{action:<30s}{end_style}")

        # Footer
        print(f"\n{DIM}Press Ctrl+C to stop{RESET}")

    async def monitor_loop(self):
        """Main monitor loop - refreshes display every 2 seconds."""
        while self.running:
            self.render()
            await asyncio.sleep(2)


async def main_monitor(run_agents: bool = False, duration_minutes: int = None):
    """Run the monitor, optionally with agent execution."""
    monitor = EmployeeMonitor()
    count = monitor.initialize()

    if run_agents:
        # Import the orchestrator for running agents
        from src.main import AgencyOrchestrator, load_config
        config = load_config()
        # TODO: Wire up orchestrator status updates to monitor.agent_status
        print(f"Agent execution mode not yet wired to monitor. Use --dry-run for now.")

    # Run monitor loop
    try:
        await monitor.monitor_loop()
    except asyncio.CancelledError:
        pass


def main():
    parser = argparse.ArgumentParser(description="Live Employee Monitor")
    parser.add_argument("--run", action="store_true", help="Also run agents (not just monitor)")
    parser.add_argument("--duration", type=str, help="Duration (e.g., 30m, 2h)")
    args = parser.parse_args()

    loop = asyncio.new_event_loop()

    def _stop():
        loop.stop()

    loop.add_signal_handler(signal.SIGINT, _stop)

    try:
        loop.run_until_complete(main_monitor(run_agents=args.run))
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()
        print("\nMonitor stopped.")


if __name__ == "__main__":
    main()
