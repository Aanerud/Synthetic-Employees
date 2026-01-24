#!/usr/bin/env python3
"""Main entry point for Synthetic Employees system."""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

from src.agents.agent_registry import AgentRegistry
from src.agents.roles import get_role
from src.behaviors.rules import behavior_engine
from src.mcp_client.client import MCPClient
from src.scenarios.email_exchange import run_email_exchange
from src.scheduler.scheduler import WorkScheduler

# Load environment variables
load_dotenv()


class SyntheticEmployees:
    """Main orchestrator for synthetic employees simulation."""

    def __init__(self):
        self.agent_registry = AgentRegistry()
        self.scheduler = None
        self.running = False

    def initialize(self):
        """Initialize the system."""
        print("🚀 Initializing Synthetic Employees System\n")

        # Load agents
        try:
            self.agent_registry.load_agents()
        except FileNotFoundError as e:
            print(f"❌ Error: {e}")
            print("\nPlease ensure config/agents.json exists.")
            print("Run this from the M365-Agent-Provisioning project:")
            print("  npm run export-to-synthetic-employees\n")
            sys.exit(1)

        # Create scheduler
        self.scheduler = WorkScheduler(self.agent_registry)

        print(f"✓ Loaded {len(self.agent_registry.agents)} agents")
        print(f"✓ Work hours: {self.scheduler.work_start_hour}:00 - {self.scheduler.work_end_hour}:00")
        print(f"✓ Timezone: {self.scheduler.timezone}")
        print()

    def tick_agent(self, agent_config, dry_run=False):
        """Process one tick for an agent."""
        role = get_role(agent_config.role)

        print(f"[{datetime.now().strftime('%H:%M:%S')}] {agent_config.name} ({agent_config.role})")

        if dry_run:
            print(f"  → Would check inbox (every {role.email_check_frequency_minutes} min)")
            return

        # Create MCP client
        mcp_client = MCPClient(agent_config.mcp_bearer_token)

        try:
            # Check inbox
            inbox = mcp_client.get_inbox(limit=10)
            unread_count = sum(1 for email in inbox if not email.get("isRead", False))

            print(f"  → Checked inbox: {unread_count} unread")

            # Process unread emails
            for email in inbox:
                if email.get("isRead", False):
                    continue

                should_respond, reason = behavior_engine.should_respond_to_email(
                    agent_config, role, email
                )

                if should_respond:
                    subject = email.get("subject", "(no subject)")[:50]
                    print(f"     ✉ Would respond to: {subject}... (Reason: {reason})")
                    # In full implementation, would generate and send response here

            # Check calendar
            events = mcp_client.get_events(timeframe="today")
            print(f"  → Calendar: {len(events)} events today")

        except Exception as e:
            print(f"  ✗ Error: {str(e)}")

    def start(self, duration_minutes=None, dry_run=False, agents=None):
        """Start the simulation."""
        print("\n" + "=" * 60)
        print("Starting Synthetic Employees")
        print("=" * 60)
        print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
        print(f"Duration: {duration_minutes if duration_minutes else 'Continuous'}")
        print("=" * 60 + "\n")

        start_time = datetime.now()
        self.running = True

        try:
            while self.running:
                # Wait if outside work hours
                if not self.scheduler.is_work_hours():
                    print("\n⏰ Outside work hours. Waiting...")
                    self.scheduler.wait_for_work_hours()

                # Get agents to tick
                agents_to_tick = self.scheduler.get_agents_to_tick()

                if agents:
                    # Filter to specific agents
                    agents_to_tick = [a for a in agents_to_tick if a.email in agents]

                # Tick agents
                for agent_config in agents_to_tick:
                    self.tick_agent(agent_config, dry_run=dry_run)
                    self.scheduler.mark_ticked(agent_config)

                # Check duration
                if duration_minutes:
                    elapsed = (datetime.now() - start_time).total_seconds() / 60
                    if elapsed >= duration_minutes:
                        print(f"\n✓ Completed {duration_minutes} minute simulation")
                        break

                # Sleep until next check
                self.scheduler.sleep_until_next_check()

        except KeyboardInterrupt:
            print("\n\n⚠ Interrupted by user")
        finally:
            self.running = False
            print("\n✨ Simulation stopped\n")

    def status(self):
        """Show current status."""
        status = self.scheduler.get_status()

        print("\nSynthetic Employees Status")
        print("=" * 60)
        print(f"Status: {'Running' if self.running else 'Stopped'}")
        print(f"Current Time: {status['current_time']}")
        print(f"Work Hours: {status['work_hours']} {status['timezone']}")
        print(f"In Work Hours: {'Yes' if status['is_work_hours'] else 'No'}")
        print(f"\nAgents: {status['agents_total']} loaded, {status['agents_ticked']} active")
        print(f"Time Acceleration: {status['time_acceleration']}x")
        print()

    def list_agents(self):
        """List all agents."""
        self.agent_registry.list_agents()

    def test_mcp(self):
        """Test MCP connectivity for all agents."""
        print("\nTesting MCP connectivity for all agents...\n")

        success_count = 0
        fail_count = 0

        for agent in self.agent_registry.agents:
            mcp_client = MCPClient(agent.mcp_bearer_token)
            result = mcp_client.test_connection()

            if result["status"] == "success":
                print(f"✓ {agent.email} - Token valid, inbox accessible")
                success_count += 1
            else:
                print(f"✗ {agent.email} - {result['error']}: {result['message']}")
                fail_count += 1

        print(f"\n{success_count}/{len(self.agent_registry.agents)} agents connected successfully")

        if fail_count > 0:
            print(f"\n⚠ {fail_count} agents failed connection")
            print("Regenerate tokens in M365-Agent-Provisioning project:")
            print("  npm run generate-tokens\n")

    def email_exchange(self):
        """Run the email exchange scenario between Victoria and François."""
        print("\nRunning Email Exchange Scenario")
        print("Victoria Palmer <-> François Moreau\n")

        result = run_email_exchange(self.agent_registry)

        if result.success:
            print(f"\n✓ Scenario completed successfully")
        else:
            print(f"\n✗ Scenario failed: {result.error}")
            print(f"  Steps completed: {result.steps_completed}/{result.total_steps}")

        return result


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Synthetic Employees - Multi-agent simulation system")

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Start command
    start_parser = subparsers.add_parser("start", help="Start the simulation")
    start_parser.add_argument("--duration", type=str, help="Duration (e.g., 8h, 30m)")
    start_parser.add_argument("--dry-run", action="store_true", help="Simulate without real API calls")
    start_parser.add_argument("--agents", type=str, help="Comma-separated list of agent emails")
    start_parser.add_argument("--acceleration", type=float, help="Time acceleration factor")

    # Status command
    subparsers.add_parser("status", help="Show current status")

    # List agents command
    subparsers.add_parser("list-agents", help="List all agents")

    # Test MCP command
    subparsers.add_parser("test-mcp", help="Test MCP connectivity")

    # Email exchange scenario command
    subparsers.add_parser("email-exchange", help="Run email exchange scenario (Victoria <-> François)")

    # Import CSV command
    import_csv_parser = subparsers.add_parser("import-csv", help="Import agents from CSV file")
    import_csv_parser.add_argument("--file", type=str, required=True, help="Path to CSV file")
    import_csv_parser.add_argument("--output", type=str, default="agents", help="Output directory for persona folders")
    import_csv_parser.add_argument("--domain", type=str, help="Email domain (only needed if CSV lacks email column)")

    # Serve command (web dashboard)
    serve_parser = subparsers.add_parser("serve", help="Start the web dashboard")
    serve_parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind to")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    serve_parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")

    # Test token exchange command
    test_token_parser = subparsers.add_parser("test-token-exchange", help="Test token exchange for a user")
    test_token_parser.add_argument("--user", type=str, required=True, help="User email to test")
    test_token_parser.add_argument("--password", type=str, help="User password (uses DEFAULT_PASSWORD if not set)")

    # Version command
    subparsers.add_parser("--version", help="Show version")

    args = parser.parse_args()

    # Handle no command
    if not args.command:
        parser.print_help()
        return

    # Handle version
    if args.command == "--version":
        print("Synthetic Employees v1.0.0")
        return

    # Initialize system
    system = SyntheticEmployees()
    system.initialize()

    # Execute command
    if args.command == "start":
        # Parse duration
        duration_minutes = None
        if args.duration:
            duration_str = args.duration.lower()
            if "h" in duration_str:
                duration_minutes = int(duration_str.replace("h", "")) * 60
            elif "m" in duration_str:
                duration_minutes = int(duration_str.replace("m", ""))
            elif "d" in duration_str:
                duration_minutes = int(duration_str.replace("d", "")) * 60 * 24

        # Parse agents filter
        agents = args.agents.split(",") if args.agents else None

        system.start(duration_minutes=duration_minutes, dry_run=args.dry_run, agents=agents)

    elif args.command == "status":
        system.status()

    elif args.command == "list-agents":
        system.list_agents()

    elif args.command == "test-mcp":
        system.test_mcp()

    elif args.command == "email-exchange":
        system.email_exchange()

    elif args.command == "import-csv":
        # Import CSV without initializing full system
        from src.agents.csv_importer import import_csv

        csv_file = args.file
        output_dir = args.output
        domain = args.domain or os.getenv("EMAIL_DOMAIN", "textcraft.onmicrosoft.com")

        print(f"Importing agents from {csv_file}...")
        try:
            personas = import_csv(csv_file, output_dir, domain)
            print(f"\nSuccessfully created {len(personas)} persona folders in {output_dir}/")
            for p in personas[:10]:  # Show first 10
                print(f"  - {p['name']} ({p['role']}) -> {p['folder']}")
            if len(personas) > 10:
                print(f"  ... and {len(personas) - 10} more")
        except FileNotFoundError:
            print(f"Error: CSV file not found: {csv_file}")
            sys.exit(1)
        except Exception as e:
            print(f"Error importing CSV: {e}")
            sys.exit(1)

    elif args.command == "serve":
        # Start web dashboard
        try:
            import uvicorn
            from src.web.app import app
        except ImportError:
            print("Error: FastAPI/uvicorn not installed. Run: pip install fastapi uvicorn")
            sys.exit(1)

        host = args.host
        port = args.port

        print(f"Starting Synthetic Employees Dashboard at http://{host}:{port}")
        uvicorn.run(
            "src.web.app:app",
            host=host,
            port=port,
            reload=args.reload,
        )

    elif args.command == "test-token-exchange":
        # Test token exchange
        from src.auth.mcp_token_manager import MCPTokenManager

        user_email = args.user
        password = args.password or os.getenv("DEFAULT_PASSWORD")

        if not password:
            print("Error: Password required. Set DEFAULT_PASSWORD env var or use --password")
            sys.exit(1)

        print(f"Testing token exchange for {user_email}...")

        try:
            manager = MCPTokenManager()
            mcp_token = manager.get_mcp_token(user_email, password)

            print(f"\nToken exchange successful!")
            print(f"  User ID: {mcp_token.user_id}")
            print(f"  User Email: {mcp_token.user_email}")
            print(f"  User Name: {mcp_token.user_name}")
            print(f"  Token Type: {mcp_token.token_type}")
            print(f"  Expires At: {mcp_token.expires_at}")
            print(f"  Token Preview: {mcp_token.access_token[:50]}...")

        except ValueError as e:
            print(f"\nToken exchange failed: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"\nError: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
