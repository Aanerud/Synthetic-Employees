"""Database service for Synthetic Employees persistence."""

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class AgentState:
    """Agent state record."""

    email: str
    status: str
    last_tick_at: Optional[datetime]
    next_tick_at: Optional[datetime]
    error_count: int
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime


@dataclass
class ActivityLogEntry:
    """Activity log entry."""

    id: int
    agent_email: str
    action_type: str
    action_data: Optional[Dict[str, Any]]
    result: str
    error_message: Optional[str]
    timestamp: datetime


class DatabaseService:
    """SQLite database service for agent persistence."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.getenv(
            "DATABASE_PATH", "data/synthetic_employees.db"
        )
        self._ensure_db_exists()

    def _ensure_db_exists(self):
        """Ensure database directory and schema exist."""
        db_file = Path(self.db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        # Load and execute schema
        schema_path = Path(__file__).parent / "schema.sql"
        if schema_path.exists():
            with open(schema_path, "r") as f:
                schema_sql = f.read()
            with self._get_connection() as conn:
                conn.executescript(schema_sql)

    @contextmanager
    def _get_connection(self):
        """Get a database connection with proper cleanup."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        """Parse ISO datetime string to datetime object."""
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

    # ==========================================================================
    # Agent State Operations
    # ==========================================================================

    def get_agent_state(self, email: str) -> Optional[AgentState]:
        """Get current state for an agent."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM agent_state WHERE email = ?", (email,)
            ).fetchone()

            if not row:
                return None

            return AgentState(
                email=row["email"],
                status=row["status"],
                last_tick_at=self._parse_datetime(row["last_tick_at"]),
                next_tick_at=self._parse_datetime(row["next_tick_at"]),
                error_count=row["error_count"],
                last_error=row["last_error"],
                created_at=self._parse_datetime(row["created_at"]) or datetime.now(),
                updated_at=self._parse_datetime(row["updated_at"]) or datetime.now(),
            )

    def get_all_agent_states(self) -> List[AgentState]:
        """Get all agent states."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM agent_state ORDER BY email").fetchall()
            return [
                AgentState(
                    email=row["email"],
                    status=row["status"],
                    last_tick_at=self._parse_datetime(row["last_tick_at"]),
                    next_tick_at=self._parse_datetime(row["next_tick_at"]),
                    error_count=row["error_count"],
                    last_error=row["last_error"],
                    created_at=self._parse_datetime(row["created_at"]) or datetime.now(),
                    updated_at=self._parse_datetime(row["updated_at"]) or datetime.now(),
                )
                for row in rows
            ]

    def upsert_agent_state(
        self,
        email: str,
        status: str = "stopped",
        last_tick_at: Optional[datetime] = None,
        next_tick_at: Optional[datetime] = None,
        error_count: int = 0,
        last_error: Optional[str] = None,
    ) -> None:
        """Create or update agent state."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO agent_state (email, status, last_tick_at, next_tick_at, error_count, last_error)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    status = excluded.status,
                    last_tick_at = excluded.last_tick_at,
                    next_tick_at = excluded.next_tick_at,
                    error_count = excluded.error_count,
                    last_error = excluded.last_error
                """,
                (
                    email,
                    status,
                    last_tick_at.isoformat() if last_tick_at else None,
                    next_tick_at.isoformat() if next_tick_at else None,
                    error_count,
                    last_error,
                ),
            )

    def update_agent_status(self, email: str, status: str) -> None:
        """Update just the status of an agent."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE agent_state SET status = ? WHERE email = ?",
                (status, email),
            )

    def update_agent_tick(
        self, email: str, next_tick_at: datetime, error: Optional[str] = None
    ) -> None:
        """Update agent after a tick."""
        with self._get_connection() as conn:
            if error:
                conn.execute(
                    """
                    UPDATE agent_state
                    SET last_tick_at = ?, next_tick_at = ?, error_count = error_count + 1, last_error = ?
                    WHERE email = ?
                    """,
                    (datetime.now().isoformat(), next_tick_at.isoformat(), error, email),
                )
            else:
                conn.execute(
                    """
                    UPDATE agent_state
                    SET last_tick_at = ?, next_tick_at = ?, last_error = NULL
                    WHERE email = ?
                    """,
                    (datetime.now().isoformat(), next_tick_at.isoformat(), email),
                )

    def get_agents_by_status(self, status: str) -> List[str]:
        """Get email addresses of agents with a specific status."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT email FROM agent_state WHERE status = ?", (status,)
            ).fetchall()
            return [row["email"] for row in rows]

    def get_agents_due_for_tick(self) -> List[str]:
        """Get agents that are due for their next tick."""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT email FROM agent_state
                WHERE status = 'running' AND (next_tick_at IS NULL OR next_tick_at <= ?)
                ORDER BY next_tick_at
                """,
                (now,),
            ).fetchall()
            return [row["email"] for row in rows]

    # ==========================================================================
    # Activity Log Operations
    # ==========================================================================

    def log_activity(
        self,
        agent_email: str,
        action_type: str,
        action_data: Optional[Dict[str, Any]] = None,
        result: str = "success",
        error_message: Optional[str] = None,
    ) -> int:
        """Log an activity for an agent. Returns the log entry ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO activity_log (agent_email, action_type, action_data, result, error_message)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    agent_email,
                    action_type,
                    json.dumps(action_data) if action_data else None,
                    result,
                    error_message,
                ),
            )
            return cursor.lastrowid

    def get_activity_log(
        self,
        agent_email: Optional[str] = None,
        action_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ActivityLogEntry]:
        """Get activity log entries with optional filters."""
        query = "SELECT * FROM activity_log WHERE 1=1"
        params: List[Any] = []

        if agent_email:
            query += " AND agent_email = ?"
            params.append(agent_email)

        if action_type:
            query += " AND action_type = ?"
            params.append(action_type)

        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [
                ActivityLogEntry(
                    id=row["id"],
                    agent_email=row["agent_email"],
                    action_type=row["action_type"],
                    action_data=json.loads(row["action_data"])
                    if row["action_data"]
                    else None,
                    result=row["result"],
                    error_message=row["error_message"],
                    timestamp=self._parse_datetime(row["timestamp"]) or datetime.now(),
                )
                for row in rows
            ]

    def get_recent_activity(
        self, agent_email: str, minutes: int = 60
    ) -> List[ActivityLogEntry]:
        """Get recent activity for an agent."""
        cutoff = (
            datetime.now()
            .replace(microsecond=0)
            .__sub__(
                __import__("datetime").timedelta(minutes=minutes)
            )
            .isoformat()
        )
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM activity_log
                WHERE agent_email = ? AND timestamp >= ?
                ORDER BY timestamp DESC
                """,
                (agent_email, cutoff),
            ).fetchall()
            return [
                ActivityLogEntry(
                    id=row["id"],
                    agent_email=row["agent_email"],
                    action_type=row["action_type"],
                    action_data=json.loads(row["action_data"])
                    if row["action_data"]
                    else None,
                    result=row["result"],
                    error_message=row["error_message"],
                    timestamp=self._parse_datetime(row["timestamp"]) or datetime.now(),
                )
                for row in rows
            ]

    # ==========================================================================
    # Token Storage Operations
    # ==========================================================================

    def store_token(
        self,
        agent_email: str,
        mcp_token: str,
        expires_at: datetime,
        refresh_token: Optional[str] = None,
    ) -> None:
        """Store an MCP token for an agent (should be pre-encrypted)."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO token_storage (agent_email, mcp_token_encrypted, expires_at, refresh_token_encrypted)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(agent_email) DO UPDATE SET
                    mcp_token_encrypted = excluded.mcp_token_encrypted,
                    expires_at = excluded.expires_at,
                    refresh_token_encrypted = excluded.refresh_token_encrypted,
                    last_refreshed_at = CURRENT_TIMESTAMP
                """,
                (
                    agent_email,
                    mcp_token,
                    expires_at.isoformat(),
                    refresh_token,
                ),
            )

    def get_token(self, agent_email: str) -> Optional[Tuple[str, datetime]]:
        """Get stored token for an agent. Returns (token, expires_at) or None."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT mcp_token_encrypted, expires_at FROM token_storage WHERE agent_email = ?",
                (agent_email,),
            ).fetchone()

            if not row or not row["mcp_token_encrypted"]:
                return None

            expires_at = self._parse_datetime(row["expires_at"])
            if not expires_at:
                return None

            return row["mcp_token_encrypted"], expires_at

    def delete_token(self, agent_email: str) -> None:
        """Delete stored token for an agent."""
        with self._get_connection() as conn:
            conn.execute(
                "DELETE FROM token_storage WHERE agent_email = ?", (agent_email,)
            )

    # ==========================================================================
    # Email Thread Operations
    # ==========================================================================

    def upsert_email_thread(
        self,
        thread_id: str,
        agent_email: str,
        subject: str,
        participants: List[str],
        message_count: int = 1,
        status: str = "active",
    ) -> None:
        """Create or update an email thread."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO email_threads (thread_id, agent_email, subject, participants, message_count, last_message_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(thread_id) DO UPDATE SET
                    subject = excluded.subject,
                    participants = excluded.participants,
                    message_count = excluded.message_count,
                    last_message_at = excluded.last_message_at,
                    status = excluded.status
                """,
                (
                    thread_id,
                    agent_email,
                    subject,
                    json.dumps(participants),
                    message_count,
                    datetime.now().isoformat(),
                    status,
                ),
            )

    def get_active_threads(self, agent_email: str) -> List[Dict[str, Any]]:
        """Get active email threads for an agent."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM email_threads
                WHERE agent_email = ? AND status = 'active'
                ORDER BY last_message_at DESC
                """,
                (agent_email,),
            ).fetchall()
            return [
                {
                    "thread_id": row["thread_id"],
                    "subject": row["subject"],
                    "participants": json.loads(row["participants"]) if row["participants"] else [],
                    "message_count": row["message_count"],
                    "last_message_at": row["last_message_at"],
                }
                for row in rows
            ]

    # ==========================================================================
    # Meeting Operations
    # ==========================================================================

    def upsert_meeting(
        self,
        event_id: str,
        agent_email: str,
        subject: str,
        organizer_email: str,
        start_time: datetime,
        end_time: datetime,
        response: str = "pending",
        is_online: bool = False,
    ) -> None:
        """Create or update a meeting record."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO meetings (event_id, agent_email, subject, organizer_email, start_time, end_time, response, is_online)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    subject = excluded.subject,
                    organizer_email = excluded.organizer_email,
                    start_time = excluded.start_time,
                    end_time = excluded.end_time,
                    response = excluded.response,
                    is_online = excluded.is_online
                """,
                (
                    event_id,
                    agent_email,
                    subject,
                    organizer_email,
                    start_time.isoformat(),
                    end_time.isoformat(),
                    response,
                    1 if is_online else 0,
                ),
            )

    def update_meeting_response(
        self, event_id: str, response: str
    ) -> None:
        """Update meeting response."""
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE meetings
                SET response = ?, response_at = ?
                WHERE event_id = ?
                """,
                (response, datetime.now().isoformat(), event_id),
            )

    def get_pending_meetings(self, agent_email: str) -> List[Dict[str, Any]]:
        """Get meetings pending response for an agent."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM meetings
                WHERE agent_email = ? AND response = 'pending'
                ORDER BY start_time
                """,
                (agent_email,),
            ).fetchall()
            return [
                {
                    "event_id": row["event_id"],
                    "subject": row["subject"],
                    "organizer_email": row["organizer_email"],
                    "start_time": row["start_time"],
                    "end_time": row["end_time"],
                    "is_online": bool(row["is_online"]),
                }
                for row in rows
            ]

    # ==========================================================================
    # Metrics Operations
    # ==========================================================================

    def increment_metric(
        self, agent_email: str, metric_name: str, value: int = 1
    ) -> None:
        """Increment a daily metric for an agent."""
        today = datetime.now().strftime("%Y-%m-%d")
        with self._get_connection() as conn:
            # First ensure row exists
            conn.execute(
                """
                INSERT INTO agent_metrics (agent_email, metric_date)
                VALUES (?, ?)
                ON CONFLICT(agent_email, metric_date) DO NOTHING
                """,
                (agent_email, today),
            )
            # Then increment the specific metric
            valid_metrics = [
                "emails_received",
                "emails_sent",
                "emails_responded",
                "meetings_attended",
                "meetings_declined",
                "tick_count",
                "error_count",
            ]
            if metric_name in valid_metrics:
                conn.execute(
                    f"""
                    UPDATE agent_metrics
                    SET {metric_name} = {metric_name} + ?
                    WHERE agent_email = ? AND metric_date = ?
                    """,
                    (value, agent_email, today),
                )

    def get_daily_metrics(
        self, agent_email: str, date: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get daily metrics for an agent."""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM agent_metrics WHERE agent_email = ? AND metric_date = ?",
                (agent_email, date),
            ).fetchone()
            if not row:
                return None
            return dict(row)

    # ==========================================================================
    # Cleanup Operations
    # ==========================================================================

    def cleanup_old_logs(self, days: int = 30) -> int:
        """Delete activity logs older than specified days. Returns count deleted."""
        cutoff = (
            datetime.now()
            .__sub__(__import__("datetime").timedelta(days=days))
            .isoformat()
        )
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM activity_log WHERE timestamp < ?", (cutoff,)
            )
            return cursor.rowcount

    # ==========================================================================
    # Project Operations
    # ==========================================================================

    def create_project(
        self,
        project_id: str,
        title: str,
        owner_email: str,
        description: Optional[str] = None,
        client_email: Optional[str] = None,
        client_name: Optional[str] = None,
        source_email_id: Optional[str] = None,
        priority: str = "normal",
        due_date: Optional[datetime] = None,
    ) -> None:
        """Create a new project."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, title, description, owner_email, client_email,
                    client_name, source_email_id, priority, due_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    title,
                    description,
                    owner_email,
                    client_email,
                    client_name,
                    source_email_id,
                    priority,
                    due_date.isoformat() if due_date else None,
                ),
            )

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get a project by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_projects_by_owner(
        self, owner_email: str, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all projects owned by an agent."""
        query = "SELECT * FROM projects WHERE owner_email = ?"
        params: List[Any] = [owner_email]

        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY created_at DESC"

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_projects_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Get all projects with a specific status."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM projects WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
            return [dict(row) for row in rows]

    def update_project_status(
        self, project_id: str, status: str, completed_at: Optional[datetime] = None
    ) -> None:
        """Update a project's status."""
        with self._get_connection() as conn:
            if status == "completed" and completed_at is None:
                completed_at = datetime.now()

            conn.execute(
                """
                UPDATE projects SET status = ?, completed_at = ?
                WHERE id = ?
                """,
                (status, completed_at.isoformat() if completed_at else None, project_id),
            )

    def update_project_teams_info(
        self, project_id: str, team_id: str, channel_id: str
    ) -> None:
        """Update project with Teams channel information."""
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE projects SET teams_team_id = ?, teams_channel_id = ?
                WHERE id = ?
                """,
                (team_id, channel_id, project_id),
            )

    # ==========================================================================
    # Project Task Operations
    # ==========================================================================

    def create_project_task(
        self,
        task_id: str,
        project_id: str,
        title: str,
        description: Optional[str] = None,
        skill_required: Optional[str] = None,
        priority: str = "normal",
        due_date: Optional[datetime] = None,
    ) -> None:
        """Create a new task for a project."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO project_tasks (id, project_id, title, description,
                    skill_required, priority, due_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    project_id,
                    title,
                    description,
                    skill_required,
                    priority,
                    due_date.isoformat() if due_date else None,
                ),
            )

    def get_project_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get a project task by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM project_tasks WHERE id = ?", (task_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_tasks_for_project(self, project_id: str) -> List[Dict[str, Any]]:
        """Get all tasks for a project."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM project_tasks WHERE project_id = ?
                ORDER BY priority DESC, created_at ASC
                """,
                (project_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_tasks_assigned_to(
        self, assignee_email: str, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all tasks assigned to an agent."""
        query = "SELECT * FROM project_tasks WHERE assigned_to = ?"
        params: List[Any] = [assignee_email]

        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY priority DESC, created_at ASC"

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def assign_task(
        self,
        task_id: str,
        assignee_email: str,
        assigned_via: str,
        message_id: Optional[str] = None,
    ) -> None:
        """Assign a task to an agent."""
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE project_tasks
                SET assigned_to = ?, assigned_via = ?, assignment_message_id = ?, status = 'assigned'
                WHERE id = ?
                """,
                (assignee_email, assigned_via, message_id, task_id),
            )

    def update_task_status(
        self, task_id: str, status: str, completed_at: Optional[datetime] = None
    ) -> None:
        """Update a task's status."""
        with self._get_connection() as conn:
            if status == "completed" and completed_at is None:
                completed_at = datetime.now()

            conn.execute(
                """
                UPDATE project_tasks SET status = ?, completed_at = ?
                WHERE id = ?
                """,
                (status, completed_at.isoformat() if completed_at else None, task_id),
            )

    def get_pending_tasks(self, status: str = "pending") -> List[Dict[str, Any]]:
        """Get all tasks with a specific status (default: pending/unassigned)."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT pt.*, p.title as project_title, p.owner_email as project_owner
                FROM project_tasks pt
                JOIN projects p ON pt.project_id = p.id
                WHERE pt.status = ?
                ORDER BY pt.priority DESC, pt.created_at ASC
                """,
                (status,),
            ).fetchall()
            return [dict(row) for row in rows]

    # ==========================================================================
    # Project Comment Operations
    # ==========================================================================

    def add_project_comment(
        self,
        project_id: str,
        author_email: str,
        content: str,
        task_id: Optional[str] = None,
        source: str = "internal",
        source_message_id: Optional[str] = None,
    ) -> int:
        """Add a comment to a project. Returns comment ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO project_comments (project_id, task_id, author_email,
                    content, source, source_message_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (project_id, task_id, author_email, content, source, source_message_id),
            )
            return cursor.lastrowid

    def get_project_comments(
        self, project_id: str, task_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get comments for a project, optionally filtered by task."""
        query = "SELECT * FROM project_comments WHERE project_id = ?"
        params: List[Any] = [project_id]

        if task_id:
            query += " AND task_id = ?"
            params.append(task_id)

        query += " ORDER BY created_at ASC"

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    # ==========================================================================
    # Pulse Execution Operations
    # ==========================================================================

    def log_pulse_execution(
        self,
        agent_email: str,
        pulse_name: str,
        result: str,
        action_data: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Log a pulse execution. Returns the log entry ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO pulse_executions (agent_email, pulse_name, result, action_data)
                VALUES (?, ?, ?, ?)
                """,
                (
                    agent_email,
                    pulse_name,
                    result,
                    json.dumps(action_data) if action_data else None,
                ),
            )
            return cursor.lastrowid

    def get_last_pulse_execution(
        self, agent_email: str, pulse_name: str
    ) -> Optional[datetime]:
        """Get the last execution time for a pulse."""
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT executed_at FROM pulse_executions
                WHERE agent_email = ? AND pulse_name = ?
                ORDER BY executed_at DESC
                LIMIT 1
                """,
                (agent_email, pulse_name),
            ).fetchone()

            if row:
                return self._parse_datetime(row["executed_at"])
            return None

    def get_recent_pulse_executions(
        self, agent_email: str, hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Get recent pulse executions for an agent."""
        cutoff = (
            datetime.now()
            .__sub__(__import__("datetime").timedelta(hours=hours))
            .isoformat()
        )
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM pulse_executions
                WHERE agent_email = ? AND executed_at >= ?
                ORDER BY executed_at DESC
                """,
                (agent_email, cutoff),
            ).fetchall()
            return [
                {
                    **dict(row),
                    "action_data": json.loads(row["action_data"])
                    if row["action_data"]
                    else None,
                }
                for row in rows
            ]


    # ==========================================================================
    # Rate Limit State Operations
    # ==========================================================================

    def get_rate_limit_state(self, agent_email: str) -> Optional[Dict[str, Any]]:
        """Get rate limit state for an agent."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM rate_limit_state WHERE agent_email = ?",
                (agent_email,),
            ).fetchone()
            return dict(row) if row else None

    def upsert_rate_limit_state(
        self,
        agent_email: str,
        emails_sent_today: int = 0,
        api_calls_today: int = 0,
        api_calls_this_hour: int = 0,
        teams_messages_today: int = 0,
        calendar_changes_today: int = 0,
        last_email_at: Optional[datetime] = None,
        last_api_call_at: Optional[datetime] = None,
        last_teams_message_at: Optional[datetime] = None,
        last_calendar_change_at: Optional[datetime] = None,
        quota_reset_date: Optional[str] = None,
        hour_reset_time: Optional[datetime] = None,
    ) -> None:
        """Create or update rate limit state for an agent."""
        if quota_reset_date is None:
            quota_reset_date = datetime.now().strftime("%Y-%m-%d")

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO rate_limit_state (
                    agent_email, emails_sent_today, api_calls_today, api_calls_this_hour,
                    teams_messages_today, calendar_changes_today,
                    last_email_at, last_api_call_at, last_teams_message_at,
                    last_calendar_change_at, quota_reset_date, hour_reset_time
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(agent_email) DO UPDATE SET
                    emails_sent_today = excluded.emails_sent_today,
                    api_calls_today = excluded.api_calls_today,
                    api_calls_this_hour = excluded.api_calls_this_hour,
                    teams_messages_today = excluded.teams_messages_today,
                    calendar_changes_today = excluded.calendar_changes_today,
                    last_email_at = excluded.last_email_at,
                    last_api_call_at = excluded.last_api_call_at,
                    last_teams_message_at = excluded.last_teams_message_at,
                    last_calendar_change_at = excluded.last_calendar_change_at,
                    quota_reset_date = excluded.quota_reset_date,
                    hour_reset_time = excluded.hour_reset_time
                """,
                (
                    agent_email,
                    emails_sent_today,
                    api_calls_today,
                    api_calls_this_hour,
                    teams_messages_today,
                    calendar_changes_today,
                    last_email_at.isoformat() if last_email_at else None,
                    last_api_call_at.isoformat() if last_api_call_at else None,
                    last_teams_message_at.isoformat() if last_teams_message_at else None,
                    last_calendar_change_at.isoformat() if last_calendar_change_at else None,
                    quota_reset_date,
                    hour_reset_time.isoformat() if hour_reset_time else None,
                ),
            )

    def increment_rate_limit_counter(
        self,
        agent_email: str,
        counter_name: str,
        value: int = 1,
    ) -> None:
        """
        Increment a rate limit counter for an agent.

        Args:
            agent_email: Agent email
            counter_name: One of 'emails_sent_today', 'api_calls_today',
                         'api_calls_this_hour', 'teams_messages_today',
                         'calendar_changes_today'
            value: Amount to increment (default 1)
        """
        valid_counters = [
            "emails_sent_today",
            "api_calls_today",
            "api_calls_this_hour",
            "teams_messages_today",
            "calendar_changes_today",
        ]
        if counter_name not in valid_counters:
            raise ValueError(f"Invalid counter name: {counter_name}")

        today = datetime.now().strftime("%Y-%m-%d")

        with self._get_connection() as conn:
            # Ensure row exists
            conn.execute(
                """
                INSERT INTO rate_limit_state (agent_email, quota_reset_date)
                VALUES (?, ?)
                ON CONFLICT(agent_email) DO NOTHING
                """,
                (agent_email, today),
            )
            # Increment counter
            conn.execute(
                f"""
                UPDATE rate_limit_state
                SET {counter_name} = {counter_name} + ?
                WHERE agent_email = ?
                """,
                (value, agent_email),
            )

    def update_rate_limit_timestamp(
        self,
        agent_email: str,
        timestamp_name: str,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Update a rate limit timestamp for an agent.

        Args:
            agent_email: Agent email
            timestamp_name: One of 'last_email_at', 'last_api_call_at',
                           'last_teams_message_at', 'last_calendar_change_at'
            timestamp: Timestamp to set (defaults to now)
        """
        valid_timestamps = [
            "last_email_at",
            "last_api_call_at",
            "last_teams_message_at",
            "last_calendar_change_at",
        ]
        if timestamp_name not in valid_timestamps:
            raise ValueError(f"Invalid timestamp name: {timestamp_name}")

        if timestamp is None:
            timestamp = datetime.now()

        today = datetime.now().strftime("%Y-%m-%d")

        with self._get_connection() as conn:
            # Ensure row exists
            conn.execute(
                """
                INSERT INTO rate_limit_state (agent_email, quota_reset_date)
                VALUES (?, ?)
                ON CONFLICT(agent_email) DO NOTHING
                """,
                (agent_email, today),
            )
            # Update timestamp
            conn.execute(
                f"""
                UPDATE rate_limit_state
                SET {timestamp_name} = ?
                WHERE agent_email = ?
                """,
                (timestamp.isoformat(), agent_email),
            )

    def reset_daily_rate_limits(self, agent_email: str) -> None:
        """Reset daily rate limit counters for an agent."""
        today = datetime.now().strftime("%Y-%m-%d")

        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE rate_limit_state
                SET emails_sent_today = 0,
                    api_calls_today = 0,
                    teams_messages_today = 0,
                    calendar_changes_today = 0,
                    quota_reset_date = ?
                WHERE agent_email = ?
                """,
                (today, agent_email),
            )

    def reset_hourly_rate_limits(self, agent_email: str) -> None:
        """Reset hourly rate limit counters for an agent."""
        now = datetime.now()
        hour_reset = now.replace(minute=0, second=0, microsecond=0)

        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE rate_limit_state
                SET api_calls_this_hour = 0,
                    hour_reset_time = ?
                WHERE agent_email = ?
                """,
                (hour_reset.isoformat(), agent_email),
            )

    def get_all_rate_limit_states(self) -> List[Dict[str, Any]]:
        """Get rate limit states for all agents."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM rate_limit_state ORDER BY agent_email"
            ).fetchall()
            return [dict(row) for row in rows]


# Global database instance
_db: Optional[DatabaseService] = None


def get_db() -> DatabaseService:
    """Get or create the global database service instance."""
    global _db
    if _db is None:
        _db = DatabaseService()
    return _db
