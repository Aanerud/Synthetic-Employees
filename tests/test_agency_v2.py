#!/usr/bin/env python3
"""
Test suite for the Agency CLI v2 architecture.

Modes:
  --offline   (default) Unit tests only - no MCP server needed
  --online    Full tests including live MCP server connectivity

Usage:
    python tests/test_agency_v2.py                # Offline only
    python tests/test_agency_v2.py --online       # Offline + Online (requires MCP server)
    pytest tests/test_agency_v2.py -v             # Offline via pytest
    pytest tests/test_agency_v2.py -v -k online   # Online via pytest (mark-based)
"""

import asyncio
import json
import os
import sys
import tempfile
import time
from datetime import datetime, time as dt_time, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

VICTORIA = "victoria.palmer@a830edad9050849coep9vqp9bog.onmicrosoft.com"
FRANCOIS = "francois.moreau@a830edad9050849coep9vqp9bog.onmicrosoft.com"


# ==========================================================================
# OFFLINE TESTS (no MCP server needed)
# ==========================================================================

def test_cultural_schedules():
    """Test country-specific work schedule definitions."""
    print("\n" + "=" * 60)
    print("Testing Cultural Schedules")
    print("=" * 60)

    from src.scheduler.cultural_schedules import (
        CULTURAL_SCHEDULES, COUNTRY_NAME_TO_CODE, get_cultural_schedule,
    )

    print("\n[1] Country coverage:")
    expected = ["IT", "SE", "FR", "DE", "ES", "PL", "NL", "BE", "PT", "AT", "DK", "IE", "CH", "GB"]
    for code in expected:
        assert code in CULTURAL_SCHEDULES, f"Missing: {code}"
    print(f"  All {len(expected)} country codes present")

    print("\n[2] Country name mapping:")
    assert COUNTRY_NAME_TO_CODE["Italy"] == "IT"
    assert COUNTRY_NAME_TO_CODE["Sweden"] == "SE"
    assert COUNTRY_NAME_TO_CODE["United Kingdom"] == "GB"
    print("  Country names resolve correctly")

    print("\n[3] Schedule values:")
    italy = get_cultural_schedule(country="Italy")
    assert italy.timezone == "Europe/Rome"
    assert italy.lunch_start == "12:30"
    print(f"  Italy: {italy.work_start}-{italy.work_end}, lunch {italy.lunch_start}-{italy.lunch_end}")

    sweden = get_cultural_schedule(usage_location="SE")
    assert len(sweden.breaks) == 2
    print(f"  Sweden: {sweden.work_start}-{sweden.work_end}, {len(sweden.breaks)} fika breaks")

    print("\n[4] Fallback:")
    assert get_cultural_schedule(country="Narnia").country_code == "GB"
    print("  Unknown -> GB")

    print("\n  PASSED")
    return True


def test_employee_scheduler():
    """Test per-employee timezone-aware scheduling."""
    print("\n" + "=" * 60)
    print("Testing Employee Scheduler")
    print("=" * 60)

    from src.scheduler.employee_scheduler import EmployeeScheduler

    sched = EmployeeScheduler(variance_percent=20, enable_weekends=False)

    print("\n[1] Registration:")
    s1 = sched.register_employee(email="it@test.com", country="Italy", role="Editor", check_frequency_minutes=30)
    assert s1.timezone == "Europe/Rome"
    s2 = sched.register_employee(email="se@test.com", country="Sweden", role="Developer", check_frequency_minutes=60)
    assert sched.employee_count == 2
    print(f"  2 employees registered (IT, SE)")

    print("\n[2] First check-in:")
    assert sched.is_first_check_in_today("it@test.com") == True
    print("  True (never ticked)")

    print("\n[3] Tick scheduling with variance:")
    sched.mark_ticked("it@test.com")
    s = sched.get_schedule("it@test.com")
    interval = (s.next_tick_at - s.last_tick_at).total_seconds() / 60
    assert 20 <= interval <= 40
    print(f"  Next tick in {interval:.0f}min (base=30, ±20%)")

    print("\n[4] Time-of-day:")
    tod = sched.get_time_of_day("it@test.com")
    print(f"  Italy: {tod}")

    print("\n  PASSED")
    return True


def test_concurrency_manager():
    """Test concurrency control: semaphore, circuit breaker, debounce."""
    print("\n" + "=" * 60)
    print("Testing Concurrency Manager")
    print("=" * 60)

    from src.concurrency.manager import ConcurrencyManager

    cm = ConcurrencyManager(max_concurrent=2, circuit_breaker_threshold=3, circuit_breaker_cooldown=10, debounce_seconds=5)

    print("\n[1] Circuit breaker:")
    cm.record_failure("a@test.com")
    cm.record_failure("a@test.com")
    assert not cm.is_circuit_open("a@test.com")
    cm.record_failure("a@test.com")
    assert cm.is_circuit_open("a@test.com")
    print("  3 failures -> open")

    print("\n[2] Debounce:")
    cm.record_success("b@test.com")
    assert cm.is_debounced("b@test.com")
    assert not cm.is_debounced("never@test.com")
    print("  Recently executed -> debounced")

    print("\n[3] Async workers:")
    async def _test():
        cm2 = ConcurrencyManager(max_concurrent=2, circuit_breaker_threshold=3, circuit_breaker_cooldown=3600, debounce_seconds=0)
        results = []
        async def task(n): results.append(n)
        await cm2.start_workers(2)
        await cm2.submit("x@test.com", lambda: task("x"), 5)
        await cm2.submit("y@test.com", lambda: task("y"), 3)
        await asyncio.sleep(0.5)
        await cm2.shutdown(5)
        assert len(results) == 2
        return True
    assert asyncio.run(_test())
    print("  2 tasks executed via workers")

    print("\n  PASSED")
    return True


def test_task_types():
    """Test task type definitions and instructions."""
    print("\n" + "=" * 60)
    print("Testing Task Types")
    print("=" * 60)

    from src.tasks.task_types import TaskType, Task, get_task_instructions

    print("\n[1] All 7 types defined:")
    for val in ["morning_routine", "check_inbox", "check_teams", "check_calendar", "proactive_work", "respond_to_pending", "end_of_day"]:
        assert TaskType(val)
    print("  OK")

    print("\n[2] Instructions per type:")
    for tt in TaskType:
        instr = get_task_instructions(tt)
        assert len(instr) > 50, f"Too short: {tt.value}"
        print(f"  {tt.value}: {len(instr)} chars")

    print("\n[3] Custom instructions:")
    custom = get_task_instructions(TaskType.CHECK_INBOX, "Also check VIP.")
    assert "Also check VIP" in custom
    print("  Appended correctly")

    print("\n  PASSED")
    return True


def test_task_selector():
    """Test task selection logic."""
    print("\n" + "=" * 60)
    print("Testing Task Selector")
    print("=" * 60)

    from src.scheduler.employee_scheduler import EmployeeScheduler
    from src.tasks.task_selector import TaskSelector
    from src.tasks.task_types import TaskType

    sched = EmployeeScheduler(variance_percent=0)
    sched.register_employee(email="t@test.com", country="United Kingdom", role="Developer", check_frequency_minutes=60)
    sel = TaskSelector(sched)

    print("\n[1] First check-in -> morning_routine:")
    assert sel.select_task("t@test.com", "Developer").task_type == TaskType.MORNING_ROUTINE
    print("  OK")

    sched.mark_ticked("t@test.com")

    print("\n[2] Pending -> respond_to_pending:")
    assert sel.select_task("t@test.com", "Developer", has_pending_items=True).task_type == TaskType.RESPOND_TO_PENDING
    print("  OK")

    print("\n[3] Default -> check_inbox or proactive:")
    tt = sel.select_task("t@test.com", "Developer").task_type
    assert tt in (TaskType.CHECK_INBOX, TaskType.PROACTIVE_WORK)
    print(f"  -> {tt.value}")

    print("\n  PASSED")
    return True


def test_agency_cli_runner():
    """Test Agency CLI command assembly and output parsing."""
    print("\n" + "=" * 60)
    print("Testing Agency CLI Runner")
    print("=" * 60)

    from src.agency.cli_runner import AgencyCliRunner, AgencyResult, _parse_json_summary

    runner = AgencyCliRunner(
        binary_path="agency", default_backend="copilot", premium_backend="claude",
        premium_roles=["Key Account Manager", "CEO"], default_timeout=120,
        role_timeouts={"Writer": 180, "CEO": 90},
    )

    print("\n[1] Backend selection:")
    assert runner._get_backend("Developer") == "copilot"
    assert runner._get_backend("CEO", is_external=True) == "claude"
    print("  Copilot default, Claude for premium+external")

    print("\n[2] Template mapping:")
    maps = {"CEO": "employee-executive", "Key Account Manager": "employee-kam",
            "Editorial Director": "employee-editorial-director", "Senior Editor - Literary": "employee-editor",
            "Academic Writer": "employee-writer", "Proofreader": "employee-proofreader",
            "Backend Developer": "employee-developer", "HR Manager": "employee-default"}
    for role, expected in maps.items():
        assert runner._get_agent_template(role) == expected, f"{role}: got {runner._get_agent_template(role)}"
        print(f"  {role:30s} -> {expected}")

    print("\n[3] JSON parsing (```json block):")
    parsed = _parse_json_summary('Text\n```json\n{"actions": [{"type": "send_email"}], "items_flagged_for_later": [], "memory_updates": []}\n```')
    assert parsed and len(parsed["actions"]) == 1
    print("  OK")

    print("\n[4] JSON parsing (inline):")
    parsed2 = _parse_json_summary('Done! {"actions": [{"type": "no_action"}], "items_flagged_for_later": [], "memory_updates": []}')
    assert parsed2 and parsed2["actions"][0]["type"] == "no_action"
    print("  OK")

    print("\n[5] No JSON -> None:")
    assert _parse_json_summary("Just text") is None
    print("  OK")

    print("\n  PASSED")
    return True


def test_result_parser():
    """Test parsing Agency output and updating database."""
    print("\n" + "=" * 60)
    print("Testing Result Parser")
    print("=" * 60)

    from src.agency.cli_runner import AgencyResult
    from src.agency.result_parser import ResultParser
    from src.database.db_service import DatabaseService

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = DatabaseService(db_path)
        parser = ResultParser(db)
        db.upsert_agent_state("t@test.com", status="running")

        print("\n[1] Success result:")
        result = AgencyResult(exit_code=0, stdout="", stderr="", duration_seconds=5.0, parsed_ok=True,
            actions_taken=[{"type": "send_email", "to": "a@b.com", "message_id": "msg-1"}],
            emails_sent=1, items_flagged_for_later=[{"description": "Follow up", "priority": "high"}],
            memory_updates=[{"type": "knowledge", "subject": "Bob", "content": "Prefers email"}])
        summary = parser.process_result("t@test.com", result)
        assert summary["success"]
        state = db.get_employee_state("t@test.com")
        assert state and "Follow up" in state["pending_items"]
        print(f"  OK: {summary}")

        print("\n[2] Failed result:")
        fail = AgencyResult(exit_code=1, stdout="", stderr="Timeout", duration_seconds=120.0, error="Timeout")
        assert not parser.process_result("t@test.com", fail)["success"]
        print("  OK: failure recorded")

        print("\n[3] Activity log:")
        logs = db.get_activity_log(agent_email="t@test.com", limit=5)
        assert len(logs) >= 2
        print(f"  {len(logs)} entries")

        print("\n  PASSED")
        return True
    finally:
        os.unlink(db_path)


def test_context_assembler():
    """Test memory context assembly for prompts."""
    print("\n" + "=" * 60)
    print("Testing Context Assembler")
    print("=" * 60)

    from src.database.db_service import DatabaseService
    from src.memory.context_assembler import ContextAssembler

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = DatabaseService(db_path)
        asm = ContextAssembler(db)

        print("\n[1] Empty DB:")
        ctx = asm.build_context("nobody@test.com")
        assert "No prior context" in ctx
        print("  Fallback message shown")

        print("\n[2] With data:")
        db.upsert_agent_state("t@test.com", status="running")
        db.upsert_conversation_memory("t@test.com", "conv-1", ["t@test.com", "bob@test.com"], "email_thread", summary="Q4 planning")
        db.upsert_agent_knowledge("t@test.com", "person", "Bob", "Prefers email")
        db.upsert_employee_state(email="t@test.com", pending_items=json.dumps([{"description": "Reply to Alice", "priority": "high"}]))
        ctx = asm.build_context("t@test.com")
        assert "Pending Items" in ctx and "Reply to Alice" in ctx
        sections = [l for l in ctx.split("\n") if l.startswith("##")]
        for s in sections:
            print(f"  {s}")

        print("\n  PASSED")
        return True
    finally:
        os.unlink(db_path)


def test_persona_to_agency_vars():
    """Test persona -> Agency input variable conversion."""
    print("\n" + "=" * 60)
    print("Testing Persona to Agency Variables")
    print("=" * 60)

    from src.agents.persona_loader import LoadedPersona, to_agency_input_vars

    persona = LoadedPersona(
        name="Victoria Palmer", email="v@test.com", role="Editorial Director",
        department="Editorial", job_title="Editorial Director", office_location="London",
        writing_style="Professional", communication_style="Clear and concise",
        specialization="Style Guardian", languages=["English (Native)", "French (Professional)"],
        skills=["Editorial Leadership"], email_check_frequency_minutes=30,
        response_time_sla_hours=2, timezone="Europe/London", manager_email=None,
        auto_accept_meetings_from=[], about_me="Experienced editor",
        custom_context={"background": "ENTJ, 15 years publishing", "expertise": "Style guides", "relationships": "Manages team of 12"},
        folder_path="agents/victoria.palmer",
    )
    v = to_agency_input_vars(persona)

    print("\n[1] Required keys:")
    for key in ["Name", "Email", "JobTitle", "Department", "OfficeLocation", "Timezone", "Languages", "WritingStyle", "CommunicationStyle", "Background", "Expertise", "Relationships"]:
        assert key in v, f"Missing: {key}"
    print(f"  All 12 keys present")

    print("\n[2] Values:")
    assert v["Name"] == "Victoria Palmer"
    assert "ENTJ" in v["Background"]
    assert "team of 12" in v["Relationships"]
    print("  Correct")

    print("\n  PASSED")
    return True


def test_employee_state_db():
    """Test employee_state table operations."""
    print("\n" + "=" * 60)
    print("Testing Employee State DB")
    print("=" * 60)

    from src.database.db_service import DatabaseService

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = DatabaseService(db_path)
        db.upsert_agent_state("e@test.com", status="running")

        print("\n[1] Upsert + read:")
        db.upsert_employee_state(email="e@test.com", processed_email_ids=json.dumps(["m1", "m2"]), pending_items=json.dumps([{"description": "Review"}]))
        state = db.get_employee_state("e@test.com")
        assert state and len(json.loads(state["processed_email_ids"])) == 2
        print("  OK")

        print("\n[2] Update:")
        db.upsert_employee_state(email="e@test.com", consecutive_failures=2)
        assert db.get_employee_state("e@test.com")["consecutive_failures"] == 2
        print("  OK")

        print("\n[3] Non-existent:")
        assert db.get_employee_state("x@test.com") is None
        print("  None returned")

        print("\n[4] Error count:")
        db.increment_error_count("e@test.com", "Timeout")
        assert db.get_agent_state("e@test.com").error_count == 1
        print("  OK")

        print("\n  PASSED")
        return True
    finally:
        os.unlink(db_path)


def test_integration_smoke():
    """Integration smoke test: full pipeline without external deps."""
    print("\n" + "=" * 60)
    print("Testing Integration (Smoke Test)")
    print("=" * 60)

    from src.agents.persona_loader import PersonaRegistry, to_agency_input_vars
    from src.scheduler.employee_scheduler import EmployeeScheduler
    from src.tasks.task_selector import TaskSelector
    from src.database.db_service import DatabaseService
    from src.memory.context_assembler import ContextAssembler
    from src.agency.cli_runner import AgencyCliRunner

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        reg = PersonaRegistry()
        count = reg.load_all()
        print(f"\n[1] Loaded {count} personas")
        if count == 0:
            print("  No personas - skipping")
            return True

        victoria = reg.get_by_email(VICTORIA) or reg.list_all()[0]
        print(f"  Using: {victoria.name}")

        print("\n[2] Scheduler:")
        sched = EmployeeScheduler()
        sched.register_employee(email=victoria.email, country="United Kingdom", role=victoria.role, check_frequency_minutes=victoria.email_check_frequency_minutes, timezone_override=victoria.timezone)
        print(f"  Registered, first_check_in={sched.is_first_check_in_today(victoria.email)}")

        print("\n[3] Task selection:")
        task = TaskSelector(sched).select_task(victoria.email, victoria.role)
        print(f"  {task.task_type.value} (priority={task.priority})")

        print("\n[4] Input vars:")
        iv = to_agency_input_vars(victoria)
        iv["TaskType"] = task.task_type.value
        iv["TaskInstructions"] = task.instructions
        iv["InboxData"] = "No inbox data (offline test)"
        iv["CalendarData"] = "No calendar data (offline test)"
        iv["MemoryContext"] = ContextAssembler(DatabaseService(db_path)).build_context(victoria.email)
        print(f"  {len(iv)} variables")

        print("\n[5] CLI command:")
        runner = AgencyCliRunner()
        cmd = runner._build_command("copilot", runner._get_agent_template(victoria.role), f"Perform {task.task_type.value}", iv)
        print(f"  {' '.join(cmd[:8])}... ({len(cmd)} args)")

        print(f"\n  Full pipeline validated for {victoria.name}")
        print("\n  PASSED")
        return True
    finally:
        os.unlink(db_path)


# ==========================================================================
# ONLINE TESTS (require MCP server at localhost:3000 + valid tokens)
# ==========================================================================

_shared_token_manager = None

def _get_token_manager():
    """Shared token manager to avoid rate limit on token exchange."""
    global _shared_token_manager
    if _shared_token_manager is None:
        from src.auth.mcp_token_manager import MCPTokenManager
        _shared_token_manager = MCPTokenManager()
    return _shared_token_manager

def _get_mcp_token(email=VICTORIA):
    """Helper: get MCP token, skip if unavailable."""
    return _get_token_manager().get_mcp_token(email)

def _get_stdio_client(email=VICTORIA):
    """Helper: get stdio MCP client (real Graph API)."""
    return _get_token_manager().get_stdio_client(email)


def test_online_token_exchange():
    """[ONLINE] Test MSAL ROPC -> Graph -> MCP JWT token exchange."""
    print("\n" + "=" * 60)
    print("[ONLINE] Token Exchange")
    print("=" * 60)

    token = _get_mcp_token()
    assert token.access_token
    assert token.user_email == VICTORIA
    print(f"  User: {token.user_name}")
    print(f"  Expires: {token.expires_at}")
    print("\n  PASSED")
    return True


def test_online_read_inbox():
    """[ONLINE] Test reading inbox via stdio MCPClient (real Graph API)."""
    print("\n" + "=" * 60)
    print("[ONLINE] Read Inbox")
    print("=" * 60)

    client = _get_stdio_client(VICTORIA)

    inbox = client.get_inbox(limit=5)
    assert isinstance(inbox, list)
    print(f"  {len(inbox)} messages")
    for msg in inbox[:3]:
        subj = msg.get("subject", "(no subject)")
        fr = msg.get("from", {})
        sender = fr.get("email") or fr.get("emailAddress", {}).get("address", "?")
        print(f"    - {sender}: {subj[:50]}")
    print("\n  PASSED")
    return True


def test_online_calendar():
    """[ONLINE] Test reading calendar via stdio MCPClient."""
    print("\n" + "=" * 60)
    print("[ONLINE] Calendar Events")
    print("=" * 60)

    client = _get_stdio_client(VICTORIA)

    events = client.get_events(timeframe="today")
    print(f"  {len(events) if isinstance(events, list) else '?'} events today")
    print("\n  PASSED")
    return True


def test_online_send_email():
    """[ONLINE] Test sending an email (Victoria -> Francois)."""
    print("\n" + "=" * 60)
    print("[ONLINE] Send Email")
    print("=" * 60)

    client = _get_stdio_client(VICTORIA)

    subject = f"Agency v2 Test - {datetime.now().strftime('%H:%M:%S')}"
    result = client.send_mail(to=FRANCOIS, subject=subject, body="Automated test from Agency v2 test suite.\n\n- Victoria Palmer")
    print(f"  Sent: '{subject}'")
    print(f"  Result: {json.dumps(result, default=str)[:200]}")
    print("\n  PASSED")
    return True


def test_online_data_fetcher():
    """[ONLINE] Test DataFetcher formats M365 data for Agency."""
    print("\n" + "=" * 60)
    print("[ONLINE] DataFetcher")
    print("=" * 60)

    from src.agency.data_fetcher import DataFetcher
    client = _get_stdio_client(VICTORIA)

    fetcher = DataFetcher(client)
    data = fetcher.fetch_all(inbox_limit=5)
    print(f"  Inbox:    {len(data['inbox'])} chars")
    print(f"  Calendar: {len(data['calendar'])} chars")
    assert len(data["inbox"]) > 10
    print(f"  Preview: {data['inbox'][:120]}...")
    print("\n  PASSED")
    return True


def test_online_action_executor():
    """[ONLINE] Test ActionExecutor with a no-op action."""
    print("\n" + "=" * 60)
    print("[ONLINE] ActionExecutor")
    print("=" * 60)

    from src.agency.action_executor import ActionExecutor
    client = _get_stdio_client(VICTORIA)

    executor = ActionExecutor(client)
    results = executor.execute_actions([{"type": "no_action", "reason": "Test"}], VICTORIA)
    assert results[0]["status"] == "skipped"
    print(f"  no_action -> skipped: OK")
    print("\n  PASSED")
    return True


def test_online_full_pipeline():
    """[ONLINE] Full pipeline: fetch data -> build context -> verify."""
    print("\n" + "=" * 60)
    print("[ONLINE] Full Pipeline (Pre-tick -> Context -> Verify)")
    print("=" * 60)

    from src.mcp_client.client import MCPClient
    from src.agency.data_fetcher import DataFetcher
    from src.agents.persona_loader import PersonaRegistry, to_agency_input_vars
    from src.scheduler.employee_scheduler import EmployeeScheduler
    from src.tasks.task_selector import TaskSelector
    from src.database.db_service import DatabaseService
    from src.memory.context_assembler import ContextAssembler
    from src.agency.cli_runner import AgencyCliRunner

    # Auth - use stdio client for real Graph API access
    client = _get_stdio_client(VICTORIA)

    # Persona
    reg = PersonaRegistry()
    reg.load_all()
    victoria = reg.get_by_email(VICTORIA)
    assert victoria
    print(f"  Persona: {victoria.name}")

    # Pre-tick: fetch M365 data
    fetcher = DataFetcher(client)
    m365 = fetcher.fetch_all(inbox_limit=5)
    print(f"  Inbox: {len(m365['inbox'])} chars")
    print(f"  Calendar: {len(m365['calendar'])} chars")

    # Scheduler + task
    sched = EmployeeScheduler()
    sched.register_employee(email=victoria.email, country="United Kingdom", role=victoria.role, check_frequency_minutes=30, timezone_override=victoria.timezone)
    task = TaskSelector(sched).select_task(victoria.email, victoria.role)
    print(f"  Task: {task.task_type.value}")

    # Build full input vars
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        iv = to_agency_input_vars(victoria)
        iv["TaskType"] = task.task_type.value
        iv["TaskInstructions"] = task.instructions
        iv["InboxData"] = m365["inbox"]
        iv["CalendarData"] = m365["calendar"]
        iv["MemoryContext"] = ContextAssembler(DatabaseService(db_path)).build_context(victoria.email)

        # Build command (don't execute)
        runner = AgencyCliRunner()
        cmd = runner._build_command("copilot", runner._get_agent_template(victoria.role), f"Perform {task.task_type.value}", iv)
        print(f"  Command: {' '.join(cmd[:6])}... ({len(cmd)} args)")
        print(f"  InboxData injected: {len(iv['InboxData'])} chars")

        print(f"\n  Full online pipeline validated for {victoria.name}")
        print("  (Agency CLI not invoked - use 'python -m src.main start' for live run)")
        print("\n  PASSED")
        return True
    finally:
        os.unlink(db_path)


# ==========================================================================
# Runner
# ==========================================================================

OFFLINE_TESTS = [
    ("Cultural Schedules", test_cultural_schedules),
    ("Employee Scheduler", test_employee_scheduler),
    ("Concurrency Manager", test_concurrency_manager),
    ("Task Types", test_task_types),
    ("Task Selector", test_task_selector),
    ("Agency CLI Runner", test_agency_cli_runner),
    ("Result Parser", test_result_parser),
    ("Context Assembler", test_context_assembler),
    ("Persona to Agency Vars", test_persona_to_agency_vars),
    ("Employee State DB", test_employee_state_db),
    ("Integration Smoke Test", test_integration_smoke),
]

ONLINE_TESTS = [
    ("Token Exchange", test_online_token_exchange),
    ("Read Inbox", test_online_read_inbox),
    ("Calendar Events", test_online_calendar),
    ("Send Email", test_online_send_email),
    ("DataFetcher", test_online_data_fetcher),
    ("ActionExecutor", test_online_action_executor),
    ("Full Pipeline", test_online_full_pipeline),
]


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Agency v2 Test Suite")
    parser.add_argument("--online", action="store_true", help="Include online tests (requires MCP server + tokens)")
    parser.add_argument("--online-only", action="store_true", help="Run only online tests")
    args = parser.parse_args()

    print("=" * 60)
    print("Agency v2 Test Suite")
    print("=" * 60)

    tests_to_run = []
    if not args.online_only:
        tests_to_run.extend([("OFFLINE", n, fn) for n, fn in OFFLINE_TESTS])
    if args.online or args.online_only:
        tests_to_run.extend([("ONLINE", n, fn) for n, fn in ONLINE_TESTS])

    if not (args.online or args.online_only):
        print("  Mode: OFFLINE (use --online for MCP server tests)")
    else:
        print("  Mode: ONLINE (MCP server at localhost:3000)")

    results = []
    for mode, name, fn in tests_to_run:
        try:
            success = fn()
            results.append((mode, name, success))
        except Exception as e:
            print(f"\n  FAILED: {e}")
            import traceback
            traceback.print_exc()
            results.append((mode, name, False))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = 0
    for mode, name, success in results:
        tag = f"[{mode}]" if args.online or args.online_only else ""
        status = "PASS" if success else "FAIL"
        print(f"  {status} {tag:10s} {name}")
        if success:
            passed += 1

    total = len(results)
    print(f"\n  {passed}/{total} tests passed")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
