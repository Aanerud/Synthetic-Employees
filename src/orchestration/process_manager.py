"""Process Manager - manages agent worker processes."""

import asyncio
import multiprocessing
import os
import signal
import time
from dataclasses import dataclass
from datetime import datetime
from multiprocessing import Process, Queue
from typing import Callable, Dict, List, Optional, Set

from ..database import get_db, AgentState


@dataclass
class WorkerStatus:
    """Status of a worker process."""

    worker_id: int
    pid: int
    agents: List[str]
    is_alive: bool
    started_at: datetime
    agent_count: int


@dataclass
class AgentCommand:
    """Command to send to a worker."""

    action: str  # 'start', 'stop', 'pause', 'resume', 'tick'
    agent_email: str
    data: Optional[Dict] = None


class ProcessManager:
    """
    Manages worker processes for agent orchestration.

    Each worker handles up to AGENTS_PER_WORKER agents in a continuous loop.
    Workers communicate via multiprocessing queues.
    """

    AGENTS_PER_WORKER = 10

    def __init__(self, max_workers: int = 10):
        self.max_workers = max_workers
        self.workers: Dict[int, Process] = {}
        self.worker_queues: Dict[int, Queue] = {}
        self.agent_to_worker: Dict[str, int] = {}
        self.next_worker_id = 0
        self._shutdown_event = multiprocessing.Event()
        self.db = get_db()

    def _create_worker(self) -> int:
        """Create a new worker process."""
        from .worker import worker_main

        worker_id = self.next_worker_id
        self.next_worker_id += 1

        command_queue = Queue()
        self.worker_queues[worker_id] = command_queue

        process = Process(
            target=worker_main,
            args=(worker_id, command_queue, self._shutdown_event),
            daemon=True,
        )
        process.start()
        self.workers[worker_id] = process

        return worker_id

    def _find_available_worker(self) -> int:
        """Find a worker with capacity or create a new one."""
        # Count agents per worker
        worker_counts: Dict[int, int] = {wid: 0 for wid in self.workers.keys()}
        for worker_id in self.agent_to_worker.values():
            if worker_id in worker_counts:
                worker_counts[worker_id] += 1

        # Find worker with space
        for worker_id, count in worker_counts.items():
            if count < self.AGENTS_PER_WORKER and self.workers[worker_id].is_alive():
                return worker_id

        # Create new worker if under limit
        if len(self.workers) < self.max_workers:
            return self._create_worker()

        # All workers full - find one with most space
        min_count = min(worker_counts.values())
        for worker_id, count in worker_counts.items():
            if count == min_count and self.workers[worker_id].is_alive():
                return worker_id

        raise RuntimeError("No available workers")

    def _send_command(self, worker_id: int, command: AgentCommand) -> bool:
        """Send a command to a worker."""
        if worker_id not in self.worker_queues:
            return False
        try:
            self.worker_queues[worker_id].put(command, timeout=5)
            return True
        except Exception:
            return False

    def start_agent(self, email: str) -> bool:
        """Start an agent."""
        # Check if already assigned to a worker
        if email in self.agent_to_worker:
            worker_id = self.agent_to_worker[email]
            # Send resume command
            return self._send_command(
                worker_id, AgentCommand(action="start", agent_email=email)
            )

        # Find available worker
        try:
            worker_id = self._find_available_worker()
        except RuntimeError:
            return False

        # Assign agent to worker
        self.agent_to_worker[email] = worker_id

        # Send start command
        success = self._send_command(
            worker_id, AgentCommand(action="start", agent_email=email)
        )

        if success:
            self.db.upsert_agent_state(email, status="running")
        else:
            del self.agent_to_worker[email]

        return success

    def stop_agent(self, email: str) -> bool:
        """Stop an agent."""
        if email not in self.agent_to_worker:
            # Just update DB state
            self.db.update_agent_status(email, "stopped")
            return True

        worker_id = self.agent_to_worker[email]
        success = self._send_command(
            worker_id, AgentCommand(action="stop", agent_email=email)
        )

        if success:
            del self.agent_to_worker[email]
            self.db.update_agent_status(email, "stopped")

        return success

    def pause_agent(self, email: str) -> bool:
        """Pause an agent."""
        if email not in self.agent_to_worker:
            return False

        worker_id = self.agent_to_worker[email]
        success = self._send_command(
            worker_id, AgentCommand(action="pause", agent_email=email)
        )

        if success:
            self.db.update_agent_status(email, "paused")

        return success

    def resume_agent(self, email: str) -> bool:
        """Resume a paused agent."""
        if email not in self.agent_to_worker:
            return self.start_agent(email)

        worker_id = self.agent_to_worker[email]
        success = self._send_command(
            worker_id, AgentCommand(action="resume", agent_email=email)
        )

        if success:
            self.db.update_agent_status(email, "running")

        return success

    def get_agent_status(self, email: str) -> Optional[str]:
        """Get current status of an agent."""
        state = self.db.get_agent_state(email)
        return state.status if state else None

    def get_all_status(self) -> List[AgentState]:
        """Get status of all agents."""
        return self.db.get_all_agent_states()

    def get_worker_status(self) -> List[WorkerStatus]:
        """Get status of all workers."""
        statuses = []
        for worker_id, process in self.workers.items():
            agents = [
                email
                for email, wid in self.agent_to_worker.items()
                if wid == worker_id
            ]
            statuses.append(
                WorkerStatus(
                    worker_id=worker_id,
                    pid=process.pid,
                    agents=agents,
                    is_alive=process.is_alive(),
                    started_at=datetime.now(),  # Would need to track this
                    agent_count=len(agents),
                )
            )
        return statuses

    def start_all(self, emails: List[str]) -> Dict[str, bool]:
        """Start multiple agents."""
        results = {}
        for email in emails:
            results[email] = self.start_agent(email)
        return results

    def stop_all(self) -> Dict[str, bool]:
        """Stop all agents."""
        results = {}
        for email in list(self.agent_to_worker.keys()):
            results[email] = self.stop_agent(email)
        return results

    def shutdown(self) -> None:
        """Shutdown all workers gracefully."""
        # Signal shutdown
        self._shutdown_event.set()

        # Stop all agents
        self.stop_all()

        # Give workers time to finish
        time.sleep(2)

        # Terminate any remaining workers
        for process in self.workers.values():
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)

        # Clean up queues
        for queue in self.worker_queues.values():
            queue.close()

        self.workers.clear()
        self.worker_queues.clear()
        self.agent_to_worker.clear()

    def health_check(self) -> Dict[str, bool]:
        """Check health of all workers."""
        health = {}
        for worker_id, process in self.workers.items():
            health[f"worker_{worker_id}"] = process.is_alive()
        return health

    def restart_dead_workers(self) -> List[int]:
        """Restart any dead workers and reassign their agents."""
        restarted = []
        for worker_id, process in list(self.workers.items()):
            if not process.is_alive():
                # Get agents that were on this worker
                agents = [
                    email
                    for email, wid in self.agent_to_worker.items()
                    if wid == worker_id
                ]

                # Remove old worker
                del self.workers[worker_id]
                self.worker_queues[worker_id].close()
                del self.worker_queues[worker_id]

                # Reassign agents
                for email in agents:
                    del self.agent_to_worker[email]
                    # They'll be reassigned when started again
                    self.db.update_agent_status(email, "stopped")

                restarted.append(worker_id)

        return restarted


# Global process manager instance
_manager: Optional[ProcessManager] = None


def get_process_manager() -> ProcessManager:
    """Get or create the global process manager instance."""
    global _manager
    if _manager is None:
        _manager = ProcessManager()
    return _manager


def cleanup_process_manager() -> None:
    """Shutdown and clean up the process manager."""
    global _manager
    if _manager is not None:
        _manager.shutdown()
        _manager = None
