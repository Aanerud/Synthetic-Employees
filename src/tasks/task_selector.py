"""Task selection logic for employee wake-up cycles.

Decides what task to give each employee based on:
- Time of day and first-check-in status
- Pending items from previous cycles
- Role-specific pulse definitions
- Default inbox check
"""

import logging
from typing import Optional

from src.behaviors.pulse import PulseEvent
from src.behaviors.pulse_definitions import get_routine_for_role
from src.scheduler.employee_scheduler import EmployeeScheduler
from src.tasks.task_types import Task, TaskType, get_task_instructions

logger = logging.getLogger(__name__)


class TaskSelector:
    """Selects the most appropriate task for an employee wake-up."""

    def __init__(self, scheduler: EmployeeScheduler):
        self.scheduler = scheduler

    def select_task(
        self,
        email: str,
        role: str,
        has_pending_items: bool = False,
        pending_description: Optional[str] = None,
    ) -> Task:
        """Select the best task for an employee's current wake-up.

        Priority order:
        1. First check-in of the day → morning_routine
        2. End of day → end_of_day
        3. Pending items from previous cycles → respond_to_pending
        4. Pulse-based proactive task → proactive_work
        5. Default → check_inbox
        """
        # 1. Morning routine (first check-in)
        if self.scheduler.is_first_check_in_today(email):
            logger.info(
                "First check-in today for %s -> morning_routine", email
            )
            return Task(
                task_type=TaskType.MORNING_ROUTINE,
                instructions=get_task_instructions(TaskType.MORNING_ROUTINE),
                priority=3,
            )

        # 2. End of day
        if self.scheduler.is_end_of_day(email, within_minutes=30):
            logger.info(
                "End of day for %s -> end_of_day", email
            )
            return Task(
                task_type=TaskType.END_OF_DAY,
                instructions=get_task_instructions(TaskType.END_OF_DAY),
                priority=9,
            )

        # 3. Pending items
        if has_pending_items:
            logger.info(
                "Pending items for %s -> respond_to_pending", email
            )
            return Task(
                task_type=TaskType.RESPOND_TO_PENDING,
                instructions=get_task_instructions(
                    TaskType.RESPOND_TO_PENDING, pending_description
                ),
                priority=1,
            )

        # 4. Pulse-based proactive task
        pulse_task = self._check_pulse(email, role)
        if pulse_task:
            return pulse_task

        # 5. Default: check inbox
        return Task(
            task_type=TaskType.CHECK_INBOX,
            instructions=get_task_instructions(TaskType.CHECK_INBOX),
            priority=5,
        )

    def _check_pulse(
        self, email: str, role: str
    ) -> Optional[Task]:
        """Check if a pulse-based proactive task should fire."""
        routine = get_routine_for_role(role)
        local_hour = self.scheduler.get_local_hour(email)

        if local_hour is None:
            return None

        for pulse in routine.pulses:
            start_hour, end_hour = pulse.time_window
            if start_hour <= local_hour < end_hour:
                # Probability check - use pulse probability
                import random

                if random.random() <= pulse.probability:
                    instructions = (
                        f"Proactive task: {pulse.name}\n"
                        f"Action: {pulse.action}\n"
                        f"Parameters: {pulse.params}\n\n"
                        f"Perform this role-specific task. "
                        f"Check your inbox/Teams for relevant items "
                        f"and take appropriate action."
                    )
                    logger.info(
                        "Pulse fired for %s: %s (p=%.2f)",
                        email,
                        pulse.name,
                        pulse.probability,
                    )
                    return Task(
                        task_type=TaskType.PROACTIVE_WORK,
                        instructions=get_task_instructions(
                            TaskType.PROACTIVE_WORK, instructions
                        ),
                        priority=7,
                        pulse_name=pulse.name,
                    )

        return None
