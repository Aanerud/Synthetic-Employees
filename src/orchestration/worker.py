"""Worker - runs multiple agents in a continuous loop."""

import os
import signal
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta
from multiprocessing import Event, Queue
from typing import Any, Callable, Dict, Optional, Set

# Add parent directory to path for imports when running as subprocess
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


@dataclass
class AgentState:
    """Local state for an agent in this worker."""

    email: str
    status: str  # 'running', 'paused', 'stopping'
    next_tick_at: datetime
    tick_interval_minutes: int
    error_count: int
    last_error: Optional[str]


class Worker:
    """
    Worker that manages multiple agents in a continuous loop.

    Each agent has its own tick interval based on role.
    The worker continuously checks which agents are due for ticks
    and executes them.
    """

    def __init__(
        self, worker_id: int, command_queue: Queue, shutdown_event: Event
    ):
        self.worker_id = worker_id
        self.command_queue = command_queue
        self.shutdown_event = shutdown_event
        self.agents: Dict[str, AgentState] = {}
        self.tick_function: Optional[Callable] = None

        # Lazy imports to avoid circular dependencies
        self._db = None
        self._persona_registry = None
        self._mcp_token_manager = None

    @property
    def db(self):
        """Lazy load database service."""
        if self._db is None:
            from ..database import get_db

            self._db = get_db()
        return self._db

    @property
    def persona_registry(self):
        """Lazy load persona registry."""
        if self._persona_registry is None:
            from ..agents.persona_loader import PersonaRegistry

            self._persona_registry = PersonaRegistry()
            self._persona_registry.load_all()
        return self._persona_registry

    @property
    def mcp_token_manager(self):
        """Lazy load MCP token manager."""
        if self._mcp_token_manager is None:
            from ..auth.mcp_token_manager import MCPTokenManager

            self._mcp_token_manager = MCPTokenManager()
        return self._mcp_token_manager

    def _get_tick_interval(self, email: str) -> int:
        """Get tick interval for an agent based on their persona."""
        persona = self.persona_registry.get_by_email(email)
        if persona:
            return persona.email_check_frequency_minutes
        return 60  # Default: 1 hour

    def _process_command(self) -> bool:
        """Process a command from the queue. Returns True if command processed."""
        try:
            # Non-blocking check for commands
            command = self.command_queue.get_nowait()
        except Exception:
            return False

        email = command.agent_email
        action = command.action

        if action == "start":
            self._start_agent(email)
        elif action == "stop":
            self._stop_agent(email)
        elif action == "pause":
            self._pause_agent(email)
        elif action == "resume":
            self._resume_agent(email)
        elif action == "tick":
            # Manual tick trigger
            if email in self.agents:
                self.agents[email].next_tick_at = datetime.now()

        return True

    def _start_agent(self, email: str) -> None:
        """Start an agent in this worker."""
        if email in self.agents:
            # Already exists, just ensure running
            self.agents[email].status = "running"
            return

        tick_interval = self._get_tick_interval(email)
        self.agents[email] = AgentState(
            email=email,
            status="running",
            next_tick_at=datetime.now(),  # Tick immediately
            tick_interval_minutes=tick_interval,
            error_count=0,
            last_error=None,
        )
        print(f"[Worker {self.worker_id}] Started agent: {email}")

    def _stop_agent(self, email: str) -> None:
        """Stop an agent in this worker."""
        if email in self.agents:
            del self.agents[email]
            print(f"[Worker {self.worker_id}] Stopped agent: {email}")

    def _pause_agent(self, email: str) -> None:
        """Pause an agent in this worker."""
        if email in self.agents:
            self.agents[email].status = "paused"
            print(f"[Worker {self.worker_id}] Paused agent: {email}")

    def _resume_agent(self, email: str) -> None:
        """Resume a paused agent."""
        if email in self.agents:
            self.agents[email].status = "running"
            print(f"[Worker {self.worker_id}] Resumed agent: {email}")

    def _tick_agent(self, state: AgentState) -> None:
        """Execute a tick for an agent."""
        email = state.email

        try:
            # Import behavior module here to avoid circular imports
            from ..behaviors.agent_loop import tick_agent

            # Execute the tick
            tick_agent(
                email,
                self.mcp_token_manager,
                self.persona_registry,
                self.db,
            )

            # Update state
            state.next_tick_at = datetime.now() + timedelta(
                minutes=state.tick_interval_minutes
            )
            state.error_count = 0
            state.last_error = None

            # Update database
            self.db.update_agent_tick(email, state.next_tick_at)
            self.db.increment_metric(email, "tick_count")

        except Exception as e:
            error_msg = str(e)
            state.error_count += 1
            state.last_error = error_msg

            # Exponential backoff on errors
            backoff_minutes = min(state.error_count * 5, 60)
            state.next_tick_at = datetime.now() + timedelta(minutes=backoff_minutes)

            # Update database
            self.db.update_agent_tick(email, state.next_tick_at, error=error_msg)
            self.db.increment_metric(email, "error_count")

            print(
                f"[Worker {self.worker_id}] Error ticking {email}: {error_msg}"
            )
            traceback.print_exc()

    def run(self) -> None:
        """Main worker loop."""
        print(f"[Worker {self.worker_id}] Started (PID: {os.getpid()})")

        while not self.shutdown_event.is_set():
            # Process any pending commands
            while self._process_command():
                pass

            # Find agents due for tick
            now = datetime.now()
            agents_to_tick = [
                state
                for state in self.agents.values()
                if state.status == "running" and state.next_tick_at <= now
            ]

            # Execute ticks
            for state in agents_to_tick:
                if self.shutdown_event.is_set():
                    break
                self._tick_agent(state)

            # Sleep before next check (short sleep to stay responsive)
            time.sleep(1)

        print(f"[Worker {self.worker_id}] Shutting down")


def worker_main(worker_id: int, command_queue: Queue, shutdown_event: Event) -> None:
    """
    Entry point for worker subprocess.

    Args:
        worker_id: Unique ID for this worker
        command_queue: Queue for receiving commands
        shutdown_event: Event signaling shutdown
    """
    # Setup signal handlers
    def signal_handler(signum, frame):
        shutdown_event.set()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Create and run worker
    worker = Worker(worker_id, command_queue, shutdown_event)

    try:
        worker.run()
    except Exception as e:
        print(f"[Worker {worker_id}] Fatal error: {e}")
        traceback.print_exc()
    finally:
        print(f"[Worker {worker_id}] Exited")


if __name__ == "__main__":
    # Test worker in isolation
    import multiprocessing

    queue = Queue()
    event = Event()

    # Add a test agent
    from dataclasses import dataclass

    @dataclass
    class TestCommand:
        action: str
        agent_email: str
        data: Optional[Dict] = None

    queue.put(TestCommand(action="start", agent_email="test@example.com"))

    # Run for a few seconds then stop
    def stop_after_delay():
        time.sleep(5)
        event.set()

    import threading

    threading.Thread(target=stop_after_delay, daemon=True).start()

    worker_main(0, queue, event)
