-- Schema for Synthetic Employees Agent Orchestration Platform
-- SQLite Database

-- Agent State Table
-- Tracks current state of each agent
CREATE TABLE IF NOT EXISTS agent_state (
    email TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'stopped' CHECK (status IN ('stopped', 'running', 'paused', 'error')),
    last_tick_at TEXT,
    next_tick_at TEXT,
    error_count INTEGER DEFAULT 0,
    last_error TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Activity Log Table
-- Records all agent actions for monitoring and debugging
CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_email TEXT NOT NULL,
    action_type TEXT NOT NULL,
    action_data TEXT,  -- JSON blob
    result TEXT,       -- 'success', 'error', 'skipped'
    error_message TEXT,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (agent_email) REFERENCES agent_state(email)
);

-- Create index for efficient log queries
CREATE INDEX IF NOT EXISTS idx_activity_log_agent ON activity_log(agent_email);
CREATE INDEX IF NOT EXISTS idx_activity_log_timestamp ON activity_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_activity_log_type ON activity_log(action_type);

-- Email Threads Table
-- Tracks ongoing email conversations
CREATE TABLE IF NOT EXISTS email_threads (
    thread_id TEXT PRIMARY KEY,
    agent_email TEXT NOT NULL,
    subject TEXT,
    participants TEXT,  -- JSON array of email addresses
    message_count INTEGER DEFAULT 0,
    last_message_at TEXT,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'archived', 'responded')),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (agent_email) REFERENCES agent_state(email)
);

CREATE INDEX IF NOT EXISTS idx_email_threads_agent ON email_threads(agent_email);

-- Meetings Table
-- Tracks calendar events and responses
CREATE TABLE IF NOT EXISTS meetings (
    event_id TEXT PRIMARY KEY,
    agent_email TEXT NOT NULL,
    subject TEXT,
    organizer_email TEXT,
    start_time TEXT,
    end_time TEXT,
    response TEXT CHECK (response IN ('pending', 'accepted', 'declined', 'tentative')),
    is_online INTEGER DEFAULT 0,
    response_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (agent_email) REFERENCES agent_state(email)
);

CREATE INDEX IF NOT EXISTS idx_meetings_agent ON meetings(agent_email);
CREATE INDEX IF NOT EXISTS idx_meetings_start ON meetings(start_time);

-- Token Storage Table
-- Stores encrypted MCP tokens for agents
CREATE TABLE IF NOT EXISTS token_storage (
    agent_email TEXT PRIMARY KEY,
    mcp_token_encrypted TEXT,
    expires_at TEXT,
    refresh_token_encrypted TEXT,
    last_refreshed_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (agent_email) REFERENCES agent_state(email)
);

-- Agent Metrics Table
-- Aggregated metrics for dashboard
CREATE TABLE IF NOT EXISTS agent_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_email TEXT NOT NULL,
    metric_date TEXT NOT NULL,
    emails_received INTEGER DEFAULT 0,
    emails_sent INTEGER DEFAULT 0,
    emails_responded INTEGER DEFAULT 0,
    meetings_attended INTEGER DEFAULT 0,
    meetings_declined INTEGER DEFAULT 0,
    tick_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    avg_response_time_seconds REAL,
    UNIQUE(agent_email, metric_date),
    FOREIGN KEY (agent_email) REFERENCES agent_state(email)
);

CREATE INDEX IF NOT EXISTS idx_agent_metrics_date ON agent_metrics(metric_date);

-- Trigger to update agent_state.updated_at
CREATE TRIGGER IF NOT EXISTS update_agent_state_timestamp
AFTER UPDATE ON agent_state
BEGIN
    UPDATE agent_state SET updated_at = CURRENT_TIMESTAMP WHERE email = NEW.email;
END;

-- Trigger to update token_storage.updated_at
CREATE TRIGGER IF NOT EXISTS update_token_storage_timestamp
AFTER UPDATE ON token_storage
BEGIN
    UPDATE token_storage SET updated_at = CURRENT_TIMESTAMP WHERE agent_email = NEW.agent_email;
END;

-- =============================================================================
-- Project Coordination Tables
-- =============================================================================

-- Projects Table
-- Tracks projects created from external client requests
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'review', 'completed', 'cancelled')),
    owner_email TEXT NOT NULL,
    client_email TEXT,
    client_name TEXT,
    source_email_id TEXT,
    teams_channel_id TEXT,
    teams_team_id TEXT,
    priority TEXT DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    due_date TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    FOREIGN KEY (owner_email) REFERENCES agent_state(email)
);

CREATE INDEX IF NOT EXISTS idx_projects_owner ON projects(owner_email);
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS idx_projects_client ON projects(client_email);

-- Project Tasks Table
-- Individual tasks within a project
CREATE TABLE IF NOT EXISTS project_tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'assigned', 'in_progress', 'review', 'completed', 'cancelled')),
    assigned_to TEXT,
    assigned_via TEXT CHECK (assigned_via IN ('email', 'teams', 'direct')),
    assignment_message_id TEXT,
    skill_required TEXT,
    priority TEXT DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    due_date TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (assigned_to) REFERENCES agent_state(email)
);

CREATE INDEX IF NOT EXISTS idx_project_tasks_project ON project_tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_project_tasks_assignee ON project_tasks(assigned_to);
CREATE INDEX IF NOT EXISTS idx_project_tasks_status ON project_tasks(status);

-- Project Comments Table
-- Communication within a project
CREATE TABLE IF NOT EXISTS project_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    task_id TEXT,
    author_email TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT CHECK (source IN ('email', 'teams', 'internal')),
    source_message_id TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (task_id) REFERENCES project_tasks(id)
);

CREATE INDEX IF NOT EXISTS idx_project_comments_project ON project_comments(project_id);

-- Pulse Execution Log
-- Tracks pulse executions for cooldown management
CREATE TABLE IF NOT EXISTS pulse_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_email TEXT NOT NULL,
    pulse_name TEXT NOT NULL,
    executed_at TEXT DEFAULT CURRENT_TIMESTAMP,
    result TEXT,
    action_data TEXT,
    FOREIGN KEY (agent_email) REFERENCES agent_state(email)
);

CREATE INDEX IF NOT EXISTS idx_pulse_executions_agent ON pulse_executions(agent_email);
CREATE INDEX IF NOT EXISTS idx_pulse_executions_pulse ON pulse_executions(pulse_name);
CREATE INDEX IF NOT EXISTS idx_pulse_executions_time ON pulse_executions(executed_at);

-- Trigger to update projects.updated_at
CREATE TRIGGER IF NOT EXISTS update_projects_timestamp
AFTER UPDATE ON projects
BEGIN
    UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- Trigger to update project_tasks.updated_at
CREATE TRIGGER IF NOT EXISTS update_project_tasks_timestamp
AFTER UPDATE ON project_tasks
BEGIN
    UPDATE project_tasks SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- =============================================================================
-- Rate Limiting Tables
-- =============================================================================

-- Rate Limit State Table
-- Tracks rate limiting state for each agent (daily quotas, last action times)
CREATE TABLE IF NOT EXISTS rate_limit_state (
    agent_email TEXT PRIMARY KEY,
    emails_sent_today INTEGER DEFAULT 0,
    api_calls_today INTEGER DEFAULT 0,
    api_calls_this_hour INTEGER DEFAULT 0,
    teams_messages_today INTEGER DEFAULT 0,
    calendar_changes_today INTEGER DEFAULT 0,
    last_email_at TEXT,
    last_api_call_at TEXT,
    last_teams_message_at TEXT,
    last_calendar_change_at TEXT,
    quota_reset_date TEXT,
    hour_reset_time TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (agent_email) REFERENCES agent_state(email)
);

-- Trigger to update rate_limit_state.updated_at
CREATE TRIGGER IF NOT EXISTS update_rate_limit_state_timestamp
AFTER UPDATE ON rate_limit_state
BEGIN
    UPDATE rate_limit_state SET updated_at = CURRENT_TIMESTAMP WHERE agent_email = NEW.agent_email;
END;
