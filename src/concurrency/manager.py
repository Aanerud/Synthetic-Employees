"""Concurrency manager for Agency CLI process execution.

Controls how many Agency processes run simultaneously, with priority
queuing, circuit breaker, and debounce logic. Inspired by AgentCore's
ExecutionPool pattern.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class CircuitState:
    """Per-employee circuit breaker state."""

    consecutive_failures: int = 0
    cooldown_until: Optional[float] = None  # monotonic timestamp


@dataclass
class ExecutionStats:
    """Tracks execution statistics."""

    total_submitted: int = 0
    total_completed: int = 0
    total_failed: int = 0
    total_skipped_circuit: int = 0
    total_skipped_debounce: int = 0
    active_count: int = 0


class ConcurrencyManager:
    """Manages concurrent Agency CLI process execution.

    Features:
    - Semaphore-based concurrency limiting
    - Priority queue (lower number = higher priority)
    - Per-employee circuit breaker
    - Debounce to prevent rapid re-execution
    """

    def __init__(
        self,
        max_concurrent: int = 15,
        circuit_breaker_threshold: int = 3,
        circuit_breaker_cooldown: int = 3600,
        debounce_seconds: int = 300,
    ):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_concurrent = max_concurrent
        self._circuit_threshold = circuit_breaker_threshold
        self._circuit_cooldown = circuit_breaker_cooldown
        self._debounce_seconds = debounce_seconds

        self._circuits: Dict[str, CircuitState] = {}
        self._last_execution: Dict[str, float] = {}
        self._active: Dict[str, asyncio.Task] = {}
        self._shutting_down = False
        self._stats = ExecutionStats()
        self._workers: list[asyncio.Task] = []
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()

    @property
    def stats(self) -> ExecutionStats:
        return self._stats

    def is_circuit_open(self, employee_email: str) -> bool:
        """Check if circuit breaker is tripped for an employee."""
        state = self._circuits.get(employee_email)
        if not state:
            return False
        if state.cooldown_until and time.monotonic() < state.cooldown_until:
            return True
        # Cooldown expired, reset
        if state.cooldown_until and time.monotonic() >= state.cooldown_until:
            state.consecutive_failures = 0
            state.cooldown_until = None
        return False

    def is_debounced(self, employee_email: str) -> bool:
        """Check if employee was executed too recently."""
        last = self._last_execution.get(employee_email)
        if not last:
            return False
        return (time.monotonic() - last) < self._debounce_seconds

    def record_success(self, employee_email: str) -> None:
        """Record a successful execution."""
        self._last_execution[employee_email] = time.monotonic()
        state = self._circuits.setdefault(employee_email, CircuitState())
        state.consecutive_failures = 0
        state.cooldown_until = None
        self._stats.total_completed += 1

    def record_failure(self, employee_email: str) -> None:
        """Record a failed execution and check circuit breaker."""
        self._last_execution[employee_email] = time.monotonic()
        state = self._circuits.setdefault(employee_email, CircuitState())
        state.consecutive_failures += 1
        self._stats.total_failed += 1

        if state.consecutive_failures >= self._circuit_threshold:
            state.cooldown_until = (
                time.monotonic() + self._circuit_cooldown
            )
            logger.warning(
                "Circuit breaker tripped for %s after %d failures. "
                "Cooldown for %ds.",
                employee_email,
                state.consecutive_failures,
                self._circuit_cooldown,
            )

    async def submit(
        self,
        employee_email: str,
        coroutine_factory: Callable[[], Coroutine[Any, Any, Any]],
        priority: int = 5,
    ) -> bool:
        """Submit an employee task for execution.

        Args:
            employee_email: Employee identifier.
            coroutine_factory: Callable that creates the coroutine to execute.
            priority: Execution priority (1=highest, 9=lowest).

        Returns:
            True if submitted, False if skipped (circuit/debounce).
        """
        if self._shutting_down:
            return False

        if self.is_circuit_open(employee_email):
            self._stats.total_skipped_circuit += 1
            logger.debug(
                "Skipping %s - circuit breaker open", employee_email
            )
            return False

        if self.is_debounced(employee_email):
            self._stats.total_skipped_debounce += 1
            logger.debug("Skipping %s - debounced", employee_email)
            return False

        # Already running
        if employee_email in self._active:
            logger.debug(
                "Skipping %s - already executing", employee_email
            )
            return False

        self._stats.total_submitted += 1
        await self._queue.put(
            (priority, time.monotonic(), employee_email, coroutine_factory)
        )
        return True

    async def start_workers(self, num_workers: Optional[int] = None) -> None:
        """Start worker tasks that pull from the queue."""
        count = num_workers or self._max_concurrent
        for i in range(count):
            task = asyncio.create_task(
                self._worker(f"worker-{i}"), name=f"concurrency-worker-{i}"
            )
            self._workers.append(task)
        logger.info("Started %d concurrency workers", count)

    async def _worker(self, name: str) -> None:
        """Worker loop that pulls from priority queue and executes."""
        while not self._shutting_down:
            try:
                priority, _, email, coro_factory = await asyncio.wait_for(
                    self._queue.get(), timeout=5.0
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            # Re-check guards before execution
            if self.is_circuit_open(email):
                self._queue.task_done()
                continue

            async with self._semaphore:
                self._stats.active_count += 1
                task = asyncio.current_task()
                self._active[email] = task

                try:
                    coro = coro_factory()
                    await coro
                    self.record_success(email)
                except asyncio.CancelledError:
                    logger.info("Task cancelled for %s", email)
                    break
                except Exception as exc:
                    logger.error(
                        "Task failed for %s: %s", email, exc
                    )
                    self.record_failure(email)
                finally:
                    self._active.pop(email, None)
                    self._stats.active_count -= 1
                    self._queue.task_done()

    async def shutdown(self, timeout: int = 30) -> None:
        """Gracefully shut down workers and wait for active tasks."""
        logger.info("Shutting down concurrency manager...")
        self._shutting_down = True

        # Cancel workers
        for worker in self._workers:
            worker.cancel()

        if self._workers:
            await asyncio.wait(self._workers, timeout=timeout)

        self._workers.clear()

        logger.info(
            "Concurrency manager shutdown complete. "
            "Stats: submitted=%d, completed=%d, failed=%d",
            self._stats.total_submitted,
            self._stats.total_completed,
            self._stats.total_failed,
        )
