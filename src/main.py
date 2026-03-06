#!/usr/bin/env python3
"""Main entry point for Synthetic Employees system.

Supports two modes:
  - Legacy: Direct MCP API calls (original implementation)
  - Agency: CLI-based agent execution via `agency copilot` (v2)
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict

import yaml
from dotenv import load_dotenv

from src.agents.agent_registry import AgentRegistry
from src.agents.persona_loader import PersonaRegistry, to_agency_input_vars
from src.agency.action_executor import ActionExecutor
from src.agency.cli_runner import AgencyCliRunner
from src.agency.data_fetcher import DataFetcher
from src.agency.result_parser import ResultParser
from src.concurrency.manager import ConcurrencyManager
from src.database.db_service import DatabaseService
from src.auth.mcp_token_manager import MCPTokenManager
from src.behaviors.office_events import OfficeEventEngine
from src.memory.context_assembler import ContextAssembler
from src.scheduler.employee_scheduler import EmployeeScheduler
from src.tasks.task_selector import TaskSelector
from src.tasks.task_types import get_task_instructions

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file with .env fallbacks."""
    if Path(config_path).exists():
        with open(config_path, "r") as f:
            return yaml.safe_load(f) or {}
    return {}


class AgencyOrchestrator:
    """Async orchestrator using Agency CLI as the agent brain.

    This is the v2 architecture that replaces direct LLM API calls
    with `agency copilot` subprocess invocations.
    """

    def __init__(self, config: dict):
        self.config = config
        self.running = False
        self.authed_employees: set = set()  # Emails with valid MCP tokens
        self.auth_queue: list = []  # Emails waiting for auth
        self.onboarding_total: int = 0
        self.tick_count: int = 0
        self.action_count: int = 0
        self.error_count_session: int = 0
        self._status_callback = None  # Optional callback for dashboard

        # Core components
        agency_cfg = config.get("agency", {})
        concurrency_cfg = config.get("concurrency", {})
        scheduling_cfg = config.get("scheduling", {})
        db_cfg = config.get("database", {})

        self.db = DatabaseService(db_cfg.get("path"))
        self.persona_registry = PersonaRegistry()
        self.agent_registry = AgentRegistry()

        self.scheduler = EmployeeScheduler(
            variance_percent=scheduling_cfg.get("variance_percent", 20),
            enable_weekends=scheduling_cfg.get("enable_weekends", False),
        )

        self.concurrency = ConcurrencyManager(
            max_concurrent=concurrency_cfg.get("max_concurrent", 15),
            circuit_breaker_threshold=concurrency_cfg.get(
                "circuit_breaker_threshold", 3
            ),
            circuit_breaker_cooldown=concurrency_cfg.get(
                "circuit_breaker_cooldown", 3600
            ),
            debounce_seconds=concurrency_cfg.get("debounce_seconds", 300),
        )

        self.runner = AgencyCliRunner(
            binary_path=agency_cfg.get("binary_path", "agency"),
            default_backend=agency_cfg.get("default_backend", "copilot"),
            premium_backend=agency_cfg.get("premium_backend", "claude"),
            premium_roles=agency_cfg.get("premium_roles", []),
            default_timeout=agency_cfg.get("default_timeout", 120),
            role_timeouts=agency_cfg.get("role_timeouts", {}),
            mcp_servers=agency_cfg.get("mcp_servers", ["workiq"]),
            agent_directory=agency_cfg.get(
                "agent_directory", ".github/agents"
            ),
        )

        self.token_manager = MCPTokenManager()
        self.context_assembler = ContextAssembler(self.db)
        self.result_parser = ResultParser(self.db)
        self.task_selector = TaskSelector(self.scheduler)
        self.event_engine = OfficeEventEngine(events_dir="events")

    def initialize(self):
        """Load personas and register employees with scheduler."""
        print("Initializing Agency Orchestrator\n")

        # Load personas
        count = self.persona_registry.load_all()
        print(f"  Loaded {count} personas")

        # Load agent registry (for MCP bearer tokens)
        try:
            self.agent_registry.load_agents()
            print(
                f"  Loaded {len(self.agent_registry.agents)} agent configs"
            )
        except FileNotFoundError:
            print(
                "  Warning: config/agents.json not found. "
                "MCP auth will not be available."
            )

        # Register each persona with the scheduler
        registered = 0
        for persona in self.persona_registry:
            # Get country from CSV data if available
            country = self._resolve_country(persona)

            # Only use persona timezone if it differs from the default
            # (all personas currently default to Europe/London regardless of country)
            tz_override = persona.timezone
            if tz_override == "Europe/London" and country != "United Kingdom":
                tz_override = None  # Let cultural schedule determine timezone

            self.scheduler.register_employee(
                email=persona.email,
                country=country,
                role=persona.role or persona.job_title,
                check_frequency_minutes=persona.email_check_frequency_minutes,
                timezone_override=tz_override,
            )
            registered += 1

        print(f"  Registered {registered} employees with scheduler")
        active = len(self.scheduler.get_active_employees())
        print(f"  Currently in work hours: {active} employees")
        print()

    def _load_csv_country_map(self) -> Dict[str, str]:
        """Load email -> country mapping from textcraft-europe.csv."""
        import csv

        csv_path = Path("textcraft-europe.csv")
        if not csv_path.exists():
            return {}

        mapping = {}
        with open(csv_path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                email = row.get("email", "")
                country = row.get("country", "")
                if email and country:
                    mapping[email.lower()] = country
        return mapping

    def _resolve_country(self, persona) -> str:
        """Resolve country from CSV data."""
        if not hasattr(self, "_csv_countries"):
            self._csv_countries = self._load_csv_country_map()

        country = self._csv_countries.get(persona.email.lower())
        if country:
            return country

        return "United Kingdom"

    async def auth_batch(self, batch_size: int = 12) -> int:
        """Authenticate a batch of employees. Returns count authed."""
        if not self.auth_queue:
            return 0

        batch = self.auth_queue[:batch_size]
        authed = 0

        for email in batch:
            try:
                self.token_manager.get_mcp_token(email)
                self.authed_employees.add(email)
                self.auth_queue.remove(email)
                self.db.upsert_agent_state(email, status="running")
                authed += 1
                logger.info("Authed %s (%d/%d)", email.split("@")[0], len(self.authed_employees), self.onboarding_total)
                await asyncio.sleep(0.5)  # Small delay between auths
            except Exception as exc:
                logger.warning("Auth failed for %s: %s", email.split("@")[0], exc)
                # Move to end of queue for retry next batch
                self.auth_queue.remove(email)
                self.auth_queue.append(email)

        return authed

    async def _progressive_auth_loop(self):
        """Background task: auth employees in batches every 15 minutes."""
        # Auth all employees at once (rate limit raised to 200)
        count = await self.auth_batch(100)
        logger.info("First batch: %d employees authed", count)

        # If any failed, retry remaining every 2 minutes
        while self.running and self.auth_queue:
            await asyncio.sleep(120)  # 2 minutes
            if not self.running:
                break
            count = await self.auth_batch(12)
            logger.info("Batch auth: %d more employees (%d/%d total)", count, len(self.authed_employees), self.onboarding_total)

    def get_status(self) -> dict:
        """Get current orchestrator status for dashboard."""
        active = self.scheduler.get_active_employees()
        return {
            "running": self.running,
            "authed": len(self.authed_employees),
            "total": self.onboarding_total,
            "active_in_work_hours": len(active),
            "ticks": self.tick_count,
            "actions": self.action_count,
            "errors": self.error_count_session,
            "auth_queue_remaining": len(self.auth_queue),
        }

    async def _execute_employee_tick(self, email: str) -> None:
        """Execute one tick for a single employee.

        Pipeline:
        1. Pre-tick: Fetch inbox/calendar via MCPClient (per-employee token)
        2. Brain: Agency CLI decides what to do (free via Copilot)
        3. Post-tick: Execute decided actions via MCPClient (per-employee token)
        """
        persona = self.persona_registry.get_by_email(email)
        if not persona:
            logger.warning("No persona found for %s", email)
            return

        role = persona.role or persona.job_title

        # ---- PRE-TICK: Fetch M365 data as this employee via stdio adapter ----
        self.db.upsert_agent_state(email, status="fetching")
        inbox_data = "No inbox data available."
        calendar_data = "No calendar data available."
        mcp_client = None

        def _sync_fetch():
            """Run stdio client in thread (it's sync/blocking)."""
            c = self.token_manager.get_stdio_client(email)
            f = DataFetcher(c)
            data = f.fetch_all(inbox_limit=10)
            return c, data

        try:
            loop = asyncio.get_event_loop()
            mcp_client, m365_data = await asyncio.wait_for(
                loop.run_in_executor(None, _sync_fetch),
                timeout=30,
            )
            inbox_data = m365_data["inbox"]
            calendar_data = m365_data["calendar"]
        except asyncio.TimeoutError:
            logger.warning("Pre-tick fetch TIMED OUT for %s (30s)", email)
            inbox_data = "[Inbox fetch timed out - will retry next cycle]"
            if mcp_client:
                try:
                    mcp_client.close()
                except Exception:
                    pass
                mcp_client = None
        except Exception as exc:
            logger.warning("Pre-tick fetch failed for %s: %s", email, exc)
            inbox_data = f"[Error fetching inbox: {exc}]"

        # Check for pending items from previous cycles
        state = self.db.get_employee_state(email)
        has_pending = False
        pending_desc = None
        if state:
            try:
                pending = json.loads(state.get("pending_items", "[]"))
                has_pending = bool(pending)
                if pending:
                    pending_desc = "; ".join(
                        item.get("description", str(item))
                        if isinstance(item, dict)
                        else str(item)
                        for item in pending[:3]
                    )
            except (json.JSONDecodeError, TypeError):
                pass

        # Select task
        task = self.task_selector.select_task(
            email=email,
            role=role,
            has_pending_items=has_pending,
            pending_description=pending_desc,
        )

        # Build input variables from persona + M365 data
        input_vars = to_agency_input_vars(persona)
        input_vars["TaskType"] = task.task_type.value

        # Always inject pending items into task instructions so agents act on them
        task_instructions = task.instructions
        if has_pending and pending_desc:
            task_instructions += (
                "\n\n## PENDING WORK FROM PREVIOUS CYCLES\n"
                "You have unfinished work that needs attention:\n"
                f"{pending_desc}\n\n"
                "If your inbox has no new unread emails, work on these pending items. "
                "Draft content, send follow-ups, deliver completed work, or email colleagues to move projects forward. "
                "Do NOT just report 'no action' when you have pending work."
            )

        input_vars["TaskInstructions"] = task_instructions
        input_vars["InboxData"] = inbox_data
        input_vars["CalendarData"] = calendar_data
        input_vars["TenantDomain"] = self.config.get("tenant_domain", "a830edad9050849coep9vqp9bog.onmicrosoft.com")

        # Build memory context
        memory_context = self.context_assembler.build_context(email)
        input_vars["MemoryContext"] = memory_context

        # Build prompt
        prompt = (
            f"Perform your {task.task_type.value} task. "
            f"Review your inbox and calendar data, then decide what "
            f"actions to take. Output your decisions as JSON."
        )

        ts = datetime.now().strftime("%H:%M:%S")
        print(
            f"  [{ts}] {persona.name} ({role}) -> {task.task_type.value}"
        )

        # ---- BRAIN: Agency CLI decides what to do (free via Copilot) ----
        self.db.upsert_agent_state(email, status="thinking")
        result = await self.runner.execute(
            agent_email=email,
            role=role,
            prompt=prompt,
            input_vars=input_vars,
        )

        # Process result and update DB state
        summary = self.result_parser.process_result(email, result)

        # ---- POST-TICK: Execute decided actions via stdio MCPClient ----
        actions_executed = 0
        if result.exit_code == 0 and result.parsed_ok and mcp_client:
            self.db.upsert_agent_state(email, status="executing")
            actions = result.actions_taken
            if actions:
                def _sync_execute():
                    executor = ActionExecutor(mcp_client)
                    return executor.execute_actions(actions, email)

                try:
                    loop = asyncio.get_event_loop()
                    action_results = await asyncio.wait_for(
                        loop.run_in_executor(None, _sync_execute),
                        timeout=30,
                    )
                    actions_executed = sum(
                        1 for r in action_results if r.get("status") == "success"
                    )
                    logger.info(
                        "Executed %d/%d actions for %s",
                        actions_executed,
                        len(actions),
                        email,
                    )
                except asyncio.TimeoutError:
                    logger.warning("Post-tick execution TIMED OUT for %s", email)
                except Exception as exc:
                    logger.error("Post-tick execution failed for %s: %s", email, exc)

        # Close stdio client
        if mcp_client:
            try:
                mcp_client.close()
            except Exception:
                pass

        # Track stats
        self.tick_count += 1
        self.action_count += actions_executed

        # Mark ticked in scheduler
        self.scheduler.mark_ticked(email)

        # Update final status
        self.db.upsert_agent_state(email, status="running")

        if result.exit_code == 0:
            print(
                f"           Done: {actions_executed} actions executed "
                f"({result.duration_seconds:.1f}s)"
            )
        else:
            self.error_count_session += 1
            self.db.upsert_agent_state(email, status="error", last_error=result.error)
            print(f"           Error: {result.error}")

    async def start(
        self,
        duration_minutes: int = None,
        agents_filter: list = None,
        dry_run: bool = False,
    ):
        """Start the async Agency orchestration loop."""
        print("\n" + "=" * 60)
        print("Starting Synthetic Employees (Agency Mode)")
        print("=" * 60)
        print(f"  Backend: {self.runner.default_backend}")
        print(f"  Max concurrent: {self.concurrency._max_concurrent}")
        print(
            f"  Employees: {self.scheduler.employee_count} registered"
        )
        print(f"  Mode: {'DRY RUN' if dry_run else 'LIVE'}")
        print(
            f"  Duration: {duration_minutes}min"
            if duration_minutes
            else "  Duration: Continuous"
        )
        print("=" * 60 + "\n")

        self.running = True
        start_time = datetime.now()
        check_interval = self.config.get("scheduling", {}).get(
            "check_interval_seconds", 60
        )

        # Build auth queue - KAMs and their teams first
        all_personas = list(self.persona_registry)
        if agents_filter:
            all_personas = [p for p in all_personas if p.email in agents_filter]

        # Prioritize: KAMs first, then editors, writers, proofreaders, then rest
        priority_order = {
            "key account": 0, "account director": 0, "account manager": 0,
            "editorial director": 1, "editor": 2,
            "writer": 3, "proofreader": 4,
            "ceo": 1, "coo": 1, "cfo": 1, "cco": 1,
        }

        def _priority(p):
            role_lower = (p.role or p.job_title or "").lower()
            for key, pri in priority_order.items():
                if key in role_lower:
                    return pri
            return 9

        all_personas.sort(key=_priority)
        self.auth_queue = [p.email for p in all_personas]
        self.onboarding_total = len(self.auth_queue)

        # Start concurrency workers
        await self.concurrency.start_workers()

        # Start progressive auth in background
        if not dry_run:
            auth_task = asyncio.create_task(self._progressive_auth_loop())

        try:
            while self.running:
                # Get employees due for a tick
                due = self.scheduler.get_employees_due_for_tick()

                # Only tick employees that are authed (or all in dry-run)
                if not dry_run:
                    due = [s for s in due if s.email in self.authed_employees]

                if agents_filter:
                    due = [
                        s for s in due if s.email in agents_filter
                    ]

                # Check office events (no Agency CLI needed - fast)
                if not dry_run and self.authed_employees:
                    active_info = []
                    for s in due:
                        p = self.persona_registry.get_by_email(s.email)
                        if p:
                            active_info.append({
                                "email": s.email,
                                "name": p.name,
                                "role": p.role or p.job_title,
                                "department": p.department,
                                "country": self._resolve_country(p),
                            })
                    fired = self.event_engine.check_and_fire(active_info)
                    if fired:
                        logger.info("Office events fired: %d actions", len(fired))
                        for ev in fired:
                            self.db.log_activity(
                                agent_email=ev["agent_email"],
                                action_type=f"event:{ev['event']}",
                                action_data=ev,
                                result="success",
                            )
                            self.action_count += 1
                            print(f"  [EVENT] {ev['agent_name']}: {ev['event']} - {ev['message'][:60]}")

                logger.info("Tick loop: %d due, %d authed, submitting...", len(due), len(self.authed_employees))

                # Submit to concurrency manager
                for schedule in due:
                    email = schedule.email

                    if dry_run:
                        ts = datetime.now().strftime("%H:%M:%S")
                        print(
                            f"  [{ts}] Would tick: {email} "
                            f"({schedule.role})"
                        )
                        self.scheduler.mark_ticked(email)
                        continue

                    # Determine priority
                    priority = 5  # normal
                    if self.scheduler.is_first_check_in_today(email):
                        priority = 3  # morning routine
                    elif self.scheduler.is_end_of_day(email):
                        priority = 9  # end of day

                    # Submit (closure captures email)
                    _email = email
                    await self.concurrency.submit(
                        employee_email=_email,
                        coroutine_factory=lambda e=_email: self._execute_employee_tick(e),
                        priority=priority,
                    )

                # Check duration
                if duration_minutes:
                    elapsed = (
                        datetime.now() - start_time
                    ).total_seconds() / 60
                    if elapsed >= duration_minutes:
                        print(
                            f"\n  Completed {duration_minutes} minute simulation"
                        )
                        break

                # Sleep until next check
                await asyncio.sleep(check_interval)

        except asyncio.CancelledError:
            print("\n  Cancelled")
        finally:
            self.running = False
            await self.concurrency.shutdown()

            stats = self.concurrency.stats
            print(f"\n  Simulation stopped")
            print(
                f"  Stats: {stats.total_completed} completed, "
                f"{stats.total_failed} failed, "
                f"{stats.total_skipped_circuit} circuit-broken"
            )
            print()


# =============================================================================
# CLI
# =============================================================================


def parse_duration(s: str) -> int:
    """Parse duration string to minutes."""
    s = s.lower()
    if "h" in s:
        return int(s.replace("h", "")) * 60
    if "m" in s:
        return int(s.replace("m", ""))
    if "d" in s:
        return int(s.replace("d", "")) * 60 * 24
    return int(s)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Synthetic Employees - Agency CLI Agent System"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # Start command (Agency mode - default)
    start_p = subparsers.add_parser(
        "start", help="Start the simulation (Agency CLI mode)"
    )
    start_p.add_argument("--duration", type=str, help="Duration (8h, 30m)")
    start_p.add_argument(
        "--dry-run", action="store_true", help="Simulate without executing"
    )
    start_p.add_argument(
        "--agents", type=str, help="Comma-separated agent emails"
    )
    start_p.add_argument(
        "--config", type=str, default="config.yaml", help="Config file"
    )

    # Status
    subparsers.add_parser("status", help="Show current status")

    # List agents
    subparsers.add_parser("list-agents", help="List all agents")

    # Test MCP
    subparsers.add_parser("test-mcp", help="Test MCP connectivity")

    # Generate agents.json from CSV (no M365 provisioning needed)
    gen_p = subparsers.add_parser(
        "generate-agents", help="Generate config/agents.json from textcraft-europe.csv"
    )
    gen_p.add_argument("--csv", default="textcraft-europe.csv", help="CSV file path")
    gen_p.add_argument("--password", help="Password for all agents (or uses DEFAULT_PASSWORD env)")

    # Import CSV
    import_p = subparsers.add_parser(
        "import-csv", help="Import agents from CSV"
    )
    import_p.add_argument("--file", type=str, required=True)
    import_p.add_argument("--output", type=str, default="agents")
    import_p.add_argument("--domain", type=str)

    # Serve
    serve_p = subparsers.add_parser("serve", help="Start web dashboard")
    serve_p.add_argument("--host", default="0.0.0.0")
    serve_p.add_argument("--port", type=int, default=8000)
    serve_p.add_argument("--reload", action="store_true")

    # Test token exchange
    token_p = subparsers.add_parser(
        "test-token-exchange", help="Test token exchange"
    )
    token_p.add_argument("--user", type=str, required=True)
    token_p.add_argument("--password", type=str)

    # Version
    subparsers.add_parser("version", help="Show version")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "version":
        print("Synthetic Employees v2.0.0 (Agency CLI)")
        return

    # Setup logging
    log_cfg = load_config(
        getattr(args, "config", "config.yaml")
    ).get("logging", {})
    logging.basicConfig(
        level=getattr(logging, log_cfg.get("level", "INFO")),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    if args.command == "start":
        duration = parse_duration(args.duration) if args.duration else None
        agents_filter = args.agents.split(",") if args.agents else None

        config = load_config(args.config)
        orchestrator = AgencyOrchestrator(config)
        orchestrator.initialize()

        loop = asyncio.new_event_loop()

        def _signal_handler():
            orchestrator.running = False

        # add_signal_handler not available on Windows
        if sys.platform != "win32":
            loop.add_signal_handler(signal.SIGINT, _signal_handler)

        try:
            loop.run_until_complete(
                orchestrator.start(
                    duration_minutes=duration,
                    agents_filter=agents_filter,
                    dry_run=args.dry_run,
                )
            )
        except KeyboardInterrupt:
            orchestrator.running = False
        finally:
            loop.close()

    elif args.command == "status":
        config = load_config()
        orchestrator = AgencyOrchestrator(config)
        orchestrator.initialize()
        active = orchestrator.scheduler.get_active_employees()
        print(f"\nSynthetic Employees Status")
        print("=" * 60)
        print(f"  Employees registered: {orchestrator.scheduler.employee_count}")
        print(f"  Currently active: {len(active)}")
        print()

    elif args.command == "list-agents":
        registry = PersonaRegistry()
        count = registry.load_all()
        print(f"\n{count} agents loaded:\n")
        for persona in sorted(registry.list_all(), key=lambda p: p.name):
            print(
                f"  {persona.name:30s} {persona.role:25s} "
                f"{persona.office_location:15s} {persona.timezone}"
            )
        print()

    elif args.command == "generate-agents":
        import csv as csv_mod
        csv_file = args.csv
        password = args.password or os.getenv("DEFAULT_PASSWORD", "")

        if not password:
            print("Error: provide --password or set DEFAULT_PASSWORD in .env")
            sys.exit(1)

        if not Path(csv_file).exists():
            print(f"Error: CSV not found: {csv_file}")
            sys.exit(1)

        agents_list = []
        with open(csv_file, encoding="utf-8") as f:
            for row in csv_mod.DictReader(f):
                agents_list.append({
                    "name": row["name"],
                    "email": row["email"],
                    "role": row.get("jobTitle", row.get("role", "")),
                    "department": row.get("department", ""),
                    "userId": "",
                    "password": password,
                    "createdAt": datetime.now().isoformat(),
                    "metadata": {"country": row.get("country", "")},
                })

        output = {
            "agents": agents_list,
            "metadata": {"totalAgents": len(agents_list), "version": "2.0.0"},
        }

        os.makedirs("config", exist_ok=True)
        with open("config/agents.json", "w", encoding="utf-8") as f:
            import json as json_mod
            json_mod.dump(output, f, indent=2, ensure_ascii=False)

        print(f"Generated config/agents.json with {len(agents_list)} agents")

    elif args.command == "test-mcp":
        print("\nTesting MCP connectivity via stdio adapter...\n")
        from src.auth.mcp_token_manager import MCPTokenManager as TM
        tm = TM()
        registry = PersonaRegistry()
        registry.load_all()
        ok = fail = 0
        for persona in list(registry)[:5]:  # Test first 5
            try:
                client = tm.get_stdio_client(persona.email)
                inbox = client.get_inbox(limit=1)
                client.close()
                print(f"  OK: {persona.name} ({persona.email})")
                ok += 1
            except Exception as e:
                print(f"  FAIL: {persona.name} - {e}")
                fail += 1
        print(f"\n{ok}/{ok+fail} connected")

    elif args.command == "import-csv":
        from src.agents.csv_importer import import_csv

        domain = args.domain or os.getenv(
            "EMAIL_DOMAIN", "textcraft.onmicrosoft.com"
        )
        print(f"Importing agents from {args.file}...")
        try:
            personas = import_csv(args.file, args.output, domain)
            print(f"\nCreated {len(personas)} persona folders")
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)

    elif args.command == "serve":
        try:
            import uvicorn
        except ImportError:
            print("Error: pip install fastapi uvicorn")
            sys.exit(1)

        print(f"Starting dashboard at http://{args.host}:{args.port}")
        uvicorn.run(
            "src.web.app:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )

    elif args.command == "test-token-exchange":
        from src.auth.mcp_token_manager import MCPTokenManager

        password = args.password or os.getenv("DEFAULT_PASSWORD")
        if not password:
            print("Error: Set DEFAULT_PASSWORD or use --password")
            sys.exit(1)

        print(f"Testing token exchange for {args.user}...")
        try:
            manager = MCPTokenManager()
            token = manager.get_mcp_token(args.user, password)
            print(f"\n  Success! Token: {token.access_token[:50]}...")
        except Exception as e:
            print(f"\n  Failed: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
