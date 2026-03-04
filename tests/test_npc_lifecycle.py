#!/usr/bin/env python3
"""
Test suite for the NPC Lifecycle System.

Tests:
1. Teams integration in MCP client
2. Pulse system (schedules, definitions, execution)
3. Project coordination (creation, tasks, assignment)
4. KAM workflow (external email detection, requirement extraction)

Usage:
    python test_npc_lifecycle.py                    # Run all tests
    python test_npc_lifecycle.py --integration      # Run with real MCP (requires tokens)
"""

import argparse
import os
import sys
import tempfile
from datetime import datetime, timedelta

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()


def test_pulse_system():
    """Test pulse system data models and logic."""
    print("\n" + "=" * 60)
    print("Testing Pulse System")
    print("=" * 60)

    from src.behaviors.pulse import PulseEvent, DailyRoutine
    from src.behaviors.pulse_definitions import (
        get_routine_for_role,
        KEY_ACCOUNT_MANAGER_ROUTINE,
        ROLE_ROUTINES,
    )

    # Test PulseEvent
    print("\n[1] PulseEvent time window:")
    pulse = PulseEvent(
        name="test_pulse",
        time_window=(9, 12),
        probability=0.8,
        action="check_inbox",
        cooldown_minutes=60,
    )

    assert pulse.is_in_time_window(9) == True
    assert pulse.is_in_time_window(11) == True
    assert pulse.is_in_time_window(12) == False
    print("  ✓ Time window checks work correctly")

    # Test cooldown
    print("\n[2] PulseEvent cooldown:")
    last_exec = datetime.now() - timedelta(minutes=30)
    assert pulse.should_fire(10, last_exec) == False
    last_exec = datetime.now() - timedelta(minutes=90)
    assert pulse.should_fire(10, last_exec) == True
    print("  ✓ Cooldown logic works correctly")

    # Test role routines
    print("\n[3] Role-specific routines:")
    for role in ["Key Account Manager", "Editorial Director", "Developer", "Proofreader"]:
        routine = get_routine_for_role(role)
        print(f"  ✓ {role}: {len(routine.pulses)} pulses")

    # Test fallback
    unknown = get_routine_for_role("Unknown Role")
    assert unknown.role == "Default"
    print("  ✓ Unknown role falls back to Default routine")

    print("\n✓ Pulse system tests passed!")
    return True


def test_project_models():
    """Test project and task models."""
    print("\n" + "=" * 60)
    print("Testing Project Models")
    print("=" * 60)

    from src.projects.models import (
        Project,
        ProjectTask,
        ProjectStatus,
        TaskStatus,
        Priority,
        ExtractedRequirements,
    )

    # Test ProjectTask
    print("\n[1] ProjectTask:")
    task = ProjectTask(
        id="task-1",
        project_id="proj-1",
        title="Review document",
        status=TaskStatus.PENDING,
    )
    assert task.to_dict()["status"] == "pending"
    print("  ✓ Task creation and serialization works")

    task_from_dict = ProjectTask.from_dict({
        "id": "task-2",
        "project_id": "proj-1",
        "title": "Another task",
        "status": "in_progress",
        "priority": "high",
    })
    assert task_from_dict.status == TaskStatus.IN_PROGRESS
    print("  ✓ Task deserialization works")

    # Test Project
    print("\n[2] Project:")
    project = Project(
        id="proj-1",
        title="Test Project",
        owner_email="kam@example.com",
        status=ProjectStatus.OPEN,
    )
    project.tasks = [
        ProjectTask("t1", "proj-1", "Task 1", status=TaskStatus.COMPLETED),
        ProjectTask("t2", "proj-1", "Task 2", status=TaskStatus.IN_PROGRESS),
        ProjectTask("t3", "proj-1", "Task 3", status=TaskStatus.PENDING),
    ]

    assert len(project.completed_tasks) == 1
    assert len(project.pending_tasks) == 2
    assert project.is_complete == False
    print("  ✓ Project task tracking works")

    # Test ExtractedRequirements
    print("\n[3] ExtractedRequirements:")
    reqs = ExtractedRequirements(
        project_title="Test Project",
        project_description="A test project",
        tasks=[{"title": "Task 1", "skill": "editing"}],
        priority=Priority.HIGH,
    )
    assert reqs.priority == Priority.HIGH
    print("  ✓ Requirement extraction model works")

    print("\n✓ Project model tests passed!")
    return True


def test_database_schema():
    """Test database schema with new project tables."""
    print("\n" + "=" * 60)
    print("Testing Database Schema")
    print("=" * 60)

    from src.database.db_service import DatabaseService

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        test_db_path = f.name

    try:
        db = DatabaseService(test_db_path)
        print("\n[1] Schema initialization:")
        print("  ✓ Database created with new schema")

        # Test project operations
        print("\n[2] Project CRUD:")
        db.create_project(
            project_id="test-proj-1",
            title="Test Project",
            owner_email="test@example.com",
            client_email="client@external.com",
            priority="high",
        )
        print("  ✓ Project created")

        project = db.get_project("test-proj-1")
        assert project["title"] == "Test Project"
        print("  ✓ Project retrieved")

        # Test task operations
        print("\n[3] Task CRUD:")
        db.create_project_task(
            task_id="test-task-1",
            project_id="test-proj-1",
            title="Review document",
            skill_required="editing",
        )
        print("  ✓ Task created")

        db.assign_task(
            task_id="test-task-1",
            assignee_email="editor@example.com",
            assigned_via="email",
        )
        print("  ✓ Task assigned")

        tasks = db.get_tasks_for_project("test-proj-1")
        assert len(tasks) == 1
        print("  ✓ Tasks retrieved")

        # Test pulse logging
        print("\n[4] Pulse execution logging:")
        db.log_pulse_execution(
            agent_email="test@example.com",
            pulse_name="inbox_review",
            result="success",
        )
        last = db.get_last_pulse_execution("test@example.com", "inbox_review")
        assert last is not None
        print("  ✓ Pulse execution logged and retrieved")

        print("\n✓ Database schema tests passed!")
        return True

    finally:
        os.unlink(test_db_path)


def test_kam_workflow():
    """Test KAM workflow logic."""
    print("\n" + "=" * 60)
    print("Testing KAM Workflow")
    print("=" * 60)

    from src.database.db_service import DatabaseService
    from src.behaviors.kam_workflow import KeyAccountManagerWorkflow

    # Mock classes
    class MockPersona:
        email = "kam@company.onmicrosoft.com"
        name = "Test KAM"
        role = "Key Account Manager"
        job_title = "Key Account Manager"

    class MockMCPClient:
        def mark_as_read(self, msg_id): pass
        def send_mail(self, **kwargs): return {"id": "sent-1"}
        def reply_to_mail(self, message_id, body): return {"id": "reply-1"}
        def list_teams(self): return [{"id": "team-1"}]
        def list_channels(self, team_id): return [{"id": "ch-1", "displayName": "General"}]
        def send_channel_message(self, **kwargs): return {"id": "msg-1"}

    class MockRegistry:
        def get_all(self):
            return []

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        test_db_path = f.name

    try:
        db = DatabaseService(test_db_path)
        workflow = KeyAccountManagerWorkflow(
            persona=MockPersona(),
            mcp_client=MockMCPClient(),
            db=db,
            persona_registry=MockRegistry(),
        )

        # Test external email detection
        print("\n[1] External email detection:")
        external = {
            "from": {"emailAddress": {"address": "client@external.com"}},
        }
        internal = {
            "from": {"emailAddress": {"address": "colleague@company.onmicrosoft.com"}},
        }
        assert workflow.is_external_email(external) == True
        assert workflow.is_external_email(internal) == False
        print("  ✓ External vs internal detection works")

        # Test client request detection
        print("\n[2] Client request detection:")
        request = {
            "from": {"emailAddress": {"address": "client@external.com"}},
            "subject": "Need help with document review",
            "bodyPreview": "Could you please help us?",
        }
        assert workflow.is_client_request(request) == True
        print("  ✓ Client request detected correctly")

        # Test requirement extraction
        print("\n[3] Requirement extraction (heuristics):")
        reqs = workflow._extract_with_heuristics(
            "URGENT: Marketing copy review",
            "We urgently need help reviewing our marketing documents. Please proofread them."
        )
        assert reqs.priority.value == "urgent"
        assert len(reqs.tasks) > 0
        print(f"  ✓ Extracted {len(reqs.tasks)} tasks with priority '{reqs.priority.value}'")

        print("\n✓ KAM workflow tests passed!")
        return True

    finally:
        os.unlink(test_db_path)


def test_teams_client_methods():
    """Test Teams methods exist in MCP client."""
    print("\n" + "=" * 60)
    print("Testing Teams Client Methods")
    print("=" * 60)

    from src.mcp_client.stdio_client import MCPStdioClient
    import inspect

    teams_methods = [
        "list_teams",
        "list_channels",
        "send_channel_message",
        "reply_to_channel_message",
        "get_channel_messages",
        "list_chats",
        "send_chat_message",
        "get_chat_messages",
        "create_online_meeting",
    ]

    print("\n[1] Teams method signatures:")
    for method_name in teams_methods:
        method = getattr(MCPStdioClient, method_name, None)
        if method is None:
            print(f"  ✗ Missing: {method_name}")
            return False

        sig = inspect.signature(method)
        params = [p for p in sig.parameters.keys() if p != "self"]
        print(f"  ✓ {method_name}({', '.join(params)})")

    print("\n✓ Teams client method tests passed!")
    return True


def run_integration_tests():
    """Run integration tests with real MCP server (requires tokens)."""
    print("\n" + "=" * 60)
    print("Integration Tests (Real MCP)")
    print("=" * 60)

    from src.auth.mcp_token_manager import MCPTokenManager

    # Find a test user
    test_users = [
        "victoria.palmer@a830edad9050849coep9vqp9bog.onmicrosoft.com",
        "francois.moreau@a830edad9050849coep9vqp9bog.onmicrosoft.com",
    ]

    token_manager = MCPTokenManager()
    client = None

    for email in test_users:
        try:
            client = token_manager.get_stdio_client(email)
            print(f"\n[1] Connected as: {email}")
            break
        except Exception as e:
            print(f"  ⚠ Could not connect as {email}: {e}")

    if not client:
        print("\n✗ No valid test user found. Skipping integration tests.")
        return False

    try:
        # Test Teams listing
        print("\n[2] Testing Teams integration:")
        teams = client.list_teams()
        print(f"  ✓ Found {len(teams) if teams else 0} teams")

        if teams:
            team_id = teams[0].get("id")
            channels = client.list_channels(team_id)
            print(f"  ✓ Found {len(channels) if channels else 0} channels in first team")

        # Test inbox
        print("\n[3] Testing inbox:")
        inbox = client.get_inbox(limit=5)
        print(f"  ✓ Found {len(inbox) if inbox else 0} emails in inbox")

        print("\n✓ Integration tests passed!")
        return True

    except Exception as e:
        print(f"\n✗ Integration test failed: {e}")
        return False

    finally:
        if client:
            client.close()


def main():
    parser = argparse.ArgumentParser(description="Test NPC Lifecycle System")
    parser.add_argument(
        "--integration",
        action="store_true",
        help="Run integration tests with real MCP (requires tokens)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("NPC Lifecycle System Test Suite")
    print("=" * 60)

    results = []

    # Run unit tests
    tests = [
        ("Pulse System", test_pulse_system),
        ("Project Models", test_project_models),
        ("Database Schema", test_database_schema),
        ("KAM Workflow", test_kam_workflow),
        ("Teams Client Methods", test_teams_client_methods),
    ]

    for name, test_fn in tests:
        try:
            success = test_fn()
            results.append((name, success))
        except Exception as e:
            print(f"\n✗ {name} failed with exception: {e}")
            results.append((name, False))

    # Run integration tests if requested
    if args.integration:
        try:
            success = run_integration_tests()
            results.append(("Integration Tests", success))
        except Exception as e:
            print(f"\n✗ Integration tests failed: {e}")
            results.append(("Integration Tests", False))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    all_passed = True
    for name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"  {status}: {name}")
        if not success:
            all_passed = False

    print()
    if all_passed:
        print("All tests passed!")
        return 0
    else:
        print("Some tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
