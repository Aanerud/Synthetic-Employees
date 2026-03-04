#!/usr/bin/env python3
"""
End-to-end scenario test: Agent interaction via Agency CLI + MCP server.

This tests the FULL v2 pipeline with real agents:
  Pre-tick (MCPClient) -> Brain (agency copilot) -> Post-tick (MCPClient)

Scenario: "Client Request to KAM"
  1. [Setup] Send an email TO Anna Kowalski (KAM) pretending to be an external client
  2. [Tick 1] Anna's agent wakes up, reads inbox, sees the client request
     -> Agency CLI thinks as Anna, decides to reply to client + delegate to team
     -> MCPClient executes: reply + assignment emails
  3. [Tick 2] François Moreau (Editor) wakes up, reads inbox, sees assignment
     -> Agency CLI thinks as François, decides to acknowledge
     -> MCPClient executes: reply to Anna

This proves:
- Token exchange works per employee
- Inbox fetching returns real data
- Agency CLI produces valid JSON actions
- Actions get executed via MCPClient
- Agents can interact with each other through M365

Usage:
    python tests/test_scenario_e2e.py                    # Full scenario
    python tests/test_scenario_e2e.py --skip-agency      # Skip Agency CLI (test MCP only)
    python tests/test_scenario_e2e.py --dry-run           # Show what would happen
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

# Participants
ANNA_KAM = "anna.kowalski@a830edad9050849coep9vqp9bog.onmicrosoft.com"
FRANCOIS = "francois.moreau@a830edad9050849coep9vqp9bog.onmicrosoft.com"
VICTORIA = "victoria.palmer@a830edad9050849coep9vqp9bog.onmicrosoft.com"

# Use Victoria to simulate the "external client" sending an email to Anna
# (In production, a real external person would email Anna)
SCENARIO_SUBJECT = f"Scenario Test - {datetime.now().strftime('%Y%m%d-%H%M%S')}"


def header(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def step(num, total, desc):
    print(f"\n[Step {num}/{total}] {desc}")
    print("-" * 50)


def get_mcp_client(email):
    """Get an authenticated stdio MCPClient for an employee (real Graph API)."""
    from src.auth.mcp_token_manager import MCPTokenManager

    tm = MCPTokenManager()
    client = tm.get_stdio_client(email)
    token = tm.get_mcp_token(email)  # for metadata only
    return client, token


def run_agent_tick(email, role, persona_registry, db, skip_agency=False, dry_run=False):
    """Run one full v2 tick for an employee. Returns (actions_decided, actions_executed)."""
    import asyncio
    from src.mcp_client.client import MCPClient
    from src.agency.data_fetcher import DataFetcher
    from src.agency.action_executor import ActionExecutor
    from src.agency.cli_runner import AgencyCliRunner, AgencyResult
    from src.agency.result_parser import ResultParser
    from src.agents.persona_loader import to_agency_input_vars
    from src.scheduler.employee_scheduler import EmployeeScheduler
    from src.tasks.task_selector import TaskSelector
    from src.memory.context_assembler import ContextAssembler

    # Get persona
    persona = persona_registry.get_by_email(email)
    if not persona:
        print(f"  No persona for {email}")
        return [], []

    # Auth
    print(f"  Authenticating as {persona.name}...")
    client, token = get_mcp_client(email)
    print(f"  Token OK (expires {token.expires_at})")

    # PRE-TICK: Fetch M365 data
    print(f"  Fetching inbox + calendar...")
    fetcher = DataFetcher(client)
    m365_data = fetcher.fetch_all(inbox_limit=10)
    print(f"  Inbox: {len(m365_data['inbox'])} chars")
    print(f"  Calendar: {len(m365_data['calendar'])} chars")

    # Show inbox summary
    inbox_preview = m365_data['inbox'][:300]
    for line in inbox_preview.split('\n')[:6]:
        if line.strip():
            print(f"    {line.strip()}")

    # Task selection
    sched = EmployeeScheduler()
    sched.register_employee(email=email, country="Poland" if "kowalski" in email else "France", role=role, check_frequency_minutes=30)
    task = TaskSelector(sched).select_task(email, role)
    print(f"  Task: {task.task_type.value}")

    # Build input vars
    input_vars = to_agency_input_vars(persona)
    input_vars["TaskType"] = task.task_type.value
    input_vars["TaskInstructions"] = task.instructions
    input_vars["InboxData"] = m365_data["inbox"]
    input_vars["CalendarData"] = m365_data["calendar"]
    input_vars["MemoryContext"] = ContextAssembler(db).build_context(email)

    if dry_run:
        print(f"\n  [DRY RUN] Would invoke: agency copilot --agent {AgencyCliRunner()._get_agent_template(role)}")
        print(f"  Input vars: {len(input_vars)} variables, {sum(len(v) for v in input_vars.values())} total chars")
        return [], []

    if skip_agency:
        print(f"\n  [SKIP AGENCY] Skipping Agency CLI, using mock response")
        # Return a mock "no_action" response
        return [{"type": "no_action", "reason": "Agency CLI skipped for testing"}], []

    # BRAIN: Agency CLI thinks
    print(f"\n  Invoking Agency CLI (this may take 30-60 seconds)...")
    runner = AgencyCliRunner()
    result = asyncio.run(runner.execute(
        agent_email=email,
        role=role,
        prompt=f"Perform your {task.task_type.value} task. Review your inbox and calendar data, then decide what actions to take. Output your decisions as JSON.",
        input_vars=input_vars,
    ))

    print(f"  Agency CLI: exit={result.exit_code}, duration={result.duration_seconds:.1f}s")

    if result.exit_code != 0:
        print(f"  ERROR: {result.error}")
        print(f"  stderr: {result.stderr[:300]}")
        return [], []

    if not result.parsed_ok:
        print(f"  WARNING: Could not parse JSON from Agency output")
        print(f"  stdout preview: {result.stdout[:500]}")
        return [], []

    actions = result.actions_taken
    print(f"  Decided {len(actions)} actions:")
    for a in actions:
        print(f"    - {a.get('type')}: {a.get('to', a.get('message_id', a.get('reason', '')))[:60]}")

    # POST-TICK: Execute actions
    print(f"\n  Executing actions via MCPClient...")
    executor = ActionExecutor(client)
    exec_results = executor.execute_actions(actions, email)

    success_count = sum(1 for r in exec_results if r.get("status") == "success")
    skip_count = sum(1 for r in exec_results if r.get("status") == "skipped")
    fail_count = sum(1 for r in exec_results if r.get("status") == "error")
    print(f"  Results: {success_count} succeeded, {skip_count} skipped, {fail_count} failed")

    for r in exec_results:
        status_icon = {"success": "OK", "skipped": "--", "error": "!!"}.get(r["status"], "??")
        print(f"    [{status_icon}] {r['action']}: {r.get('to', r.get('subject', r.get('detail', '')))[:50]}")

    # Update DB
    ResultParser(db).process_result(email, result)

    return actions, exec_results


def main():
    parser = argparse.ArgumentParser(description="E2E Scenario Test")
    parser.add_argument("--skip-agency", action="store_true", help="Skip Agency CLI invocation (test MCP only)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without executing")
    args = parser.parse_args()

    import tempfile
    from src.agents.persona_loader import PersonaRegistry
    from src.database.db_service import DatabaseService

    header(f"E2E Scenario: Client Request to KAM")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Mode: {'DRY RUN' if args.dry_run else 'SKIP AGENCY' if args.skip_agency else 'FULL (Agency CLI + MCP)'}")

    # Load personas
    persona_reg = PersonaRegistry()
    count = persona_reg.load_all()
    print(f"  Personas: {count} loaded")

    # Temp DB for this test
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    db = DatabaseService(db_path)

    try:
        # ============================================================
        # Step 1: Send a "client request" email to Anna (KAM)
        # ============================================================
        step(1, 4, "Send client request email to Anna Kowalski (KAM)")

        if args.dry_run:
            print(f"  [DRY RUN] Would send email from Victoria to Anna")
            print(f"  Subject: {SCENARIO_SUBJECT}")
        else:
            print(f"  Authenticating as Victoria (to simulate external client)...")
            victoria_client, _ = get_mcp_client(VICTORIA)

            print(f"  Sending client request to Anna...")
            result = victoria_client.send_mail(
                to=ANNA_KAM,
                subject=SCENARIO_SUBJECT,
                body=f"""Dear Anna,

I hope this message finds you well. We need your team's help with a content project.

We're preparing marketing materials for our annual European Technology Conference and need:

1. A compelling keynote summary (2 pages) - needs strong editorial voice
2. Speaker biography edits (5 bios) - need proofreading and polish
3. Conference program descriptions - technical writing with engaging tone

Timeline: We need drafts by end of next week.

Could you coordinate with your editorial team on this? Happy to discuss details.

Best regards,
Victoria Palmer
(simulating external client for E2E test)
""",
            )
            print(f"  Sent: '{SCENARIO_SUBJECT}'")
            print(f"  Result: {json.dumps(result, default=str)[:100]}")

            print(f"\n  Waiting 3s for email delivery...")
            time.sleep(3)

        # ============================================================
        # Step 2: Anna's agent tick (reads inbox, decides actions)
        # ============================================================
        step(2, 4, "Anna Kowalski (KAM) agent tick")

        anna_persona = persona_reg.get_by_email(ANNA_KAM)
        anna_role = anna_persona.role if anna_persona else "Key Account Manager"
        print(f"  Persona: {anna_persona.name if anna_persona else ANNA_KAM} ({anna_role})")

        anna_actions, anna_results = run_agent_tick(
            ANNA_KAM, anna_role, persona_reg, db,
            skip_agency=args.skip_agency, dry_run=args.dry_run,
        )

        # ============================================================
        # Step 3: François's agent tick (reads inbox, responds)
        # ============================================================
        step(3, 4, "François Moreau (Editor) agent tick")

        if anna_actions and any(a.get("type") == "send_email" for a in anna_actions):
            print(f"  Anna sent assignment emails - François should see one")
            print(f"  Waiting 3s for delivery...")
            time.sleep(3)
        else:
            print(f"  No assignment emails sent by Anna (may see nothing new)")

        francois_persona = persona_reg.get_by_email(FRANCOIS)
        francois_role = francois_persona.role if francois_persona else "Senior Editor - Literary"
        print(f"  Persona: {francois_persona.name if francois_persona else FRANCOIS} ({francois_role})")

        francois_actions, francois_results = run_agent_tick(
            FRANCOIS, francois_role, persona_reg, db,
            skip_agency=args.skip_agency, dry_run=args.dry_run,
        )

        # ============================================================
        # Step 4: Verify - check inboxes for evidence of interaction
        # ============================================================
        step(4, 4, "Verify agent interaction")

        if args.dry_run:
            print(f"  [DRY RUN] Would verify emails arrived")
        else:
            print(f"  Checking Anna's sent items / François's inbox...")
            try:
                francois_client, _ = get_mcp_client(FRANCOIS)
                inbox = francois_client.get_inbox(limit=5)
                print(f"  François's inbox: {len(inbox)} messages")
                for msg in inbox[:3]:
                    subj = msg.get("subject", "?")
                    fr = msg.get("from", {})
                    sender = fr.get("email") or fr.get("emailAddress", {}).get("address", "?")
                    print(f"    - {sender}: {subj[:50]}")
            except Exception as e:
                print(f"  Could not verify: {e}")

        # ============================================================
        # Summary
        # ============================================================
        header("Scenario Results")

        total_actions = len(anna_actions) + len(francois_actions)
        total_executed = len(anna_results) + len(francois_results)
        total_success = sum(1 for r in anna_results + francois_results if r.get("status") == "success")

        print(f"""
  Scenario:  Client Request to KAM
  Subject:   {SCENARIO_SUBJECT}
  Mode:      {'DRY RUN' if args.dry_run else 'SKIP AGENCY' if args.skip_agency else 'FULL'}

  Anna Kowalski (KAM):
    Actions decided: {len(anna_actions)}
    Actions executed: {len(anna_results)}

  François Moreau (Editor):
    Actions decided: {len(francois_actions)}
    Actions executed: {len(francois_results)}

  Total:
    Actions decided:  {total_actions}
    Actions executed: {total_executed}
    Successful:       {total_success}
""")

        if args.dry_run:
            print("  DRY RUN complete - no real actions taken")
        elif args.skip_agency:
            print("  MCP connectivity verified - Agency CLI was skipped")
            print("  Run without --skip-agency for full agent interaction")
        else:
            if total_success > 0:
                print("  Agents successfully interacted through M365!")
            else:
                print("  No actions executed - check agent output above")

        return total_success > 0 or args.dry_run or args.skip_agency

    except Exception as e:
        print(f"\n  SCENARIO FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
