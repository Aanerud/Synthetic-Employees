# Architecture

## System Overview

Synthetic-Employees is a multi-agent simulation system that creates realistic workplace behaviors using AI agents integrated with Microsoft 365.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Synthetic Employees System                   │
│                                                                 │
│  ┌──────────────┐                                              │
│  │  Scheduler   │  (Work hours, tick frequency)                │
│  └──────┬───────┘                                              │
│         │                                                       │
│         ▼                                                       │
│  ┌──────────────────────────────────────────────────┐          │
│  │           Agent Registry                          │          │
│  │  (Loads agents from config, manages lifecycle)   │          │
│  └──────┬───────────────────────────────────────────┘          │
│         │                                                       │
│         ▼                                                       │
│  ┌─────────────────────────────────────────────────┐           │
│  │              CrewAI Agents                       │           │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐         │           │
│  │  │  Agent  │  │  Agent  │  │  Agent  │         │           │
│  │  │   CEO   │  │   Dev   │  │   PM    │  ...    │           │
│  │  └────┬────┘  └────┬────┘  └────┬────┘         │           │
│  └───────┼────────────┼────────────┼──────────────┘           │
│          │            │            │                           │
│          ▼            ▼            ▼                           │
│  ┌──────────────────────────────────────────────────┐          │
│  │        Behavior Engine (Rules + LLM)             │          │
│  │  - Email response rules                          │          │
│  │  - Meeting acceptance logic                      │          │
│  │  - LLM fallback for complex decisions            │          │
│  └──────┬───────────────────────────────────────────┘          │
│         │                                                       │
│         ▼                                                       │
│  ┌──────────────────────────────────────────────────┐          │
│  │            MCP Client (HTTP)                     │          │
│  │  - Bearer token authentication                   │          │
│  │  - Tools: getInbox, sendMail, createEvent, etc. │          │
│  └──────┬───────────────────────────────────────────┘          │
│         │                                                       │
│         ▼                                                       │
│  ┌──────────────────────────────────────────────────┐          │
│  │         State Database (SQLite)                  │          │
│  │  - Agent activity log                            │          │
│  │  - Email/meeting history                         │          │
│  │  - Conversation threads                          │          │
│  └──────────────────────────────────────────────────┘          │
│                                                                 │
└──────────────────────┬──────────────────────────────────────────┘
                       │ HTTP + Bearer Token
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  MCP Server (mcp.nstop.no)                                      │
│  - Validates bearer tokens                                      │
│  - Proxies to Microsoft Graph API                               │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Microsoft 365                                                  │
│  - Exchange Online (Email)                                      │
│  - Outlook Calendar (Meetings)                                  │
│  - OneDrive/SharePoint (Files)                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Scheduler

**Purpose**: Controls when agents are active and how often they "tick"

**Key Features**:
- Work hours enforcement (9am-5pm, configurable)
- Weekend/holiday skipping
- Per-agent tick frequency (CEO checks email more often than developers)
- Randomization to avoid robotic patterns

**Implementation**:
```python
class Scheduler:
    def is_work_hours(self) -> bool:
        # Check if current time is within work hours

    def next_tick_time(self, agent: Agent) -> datetime:
        # Calculate when agent should next be active
        # Based on role-specific frequency + randomization

    def run(self):
        # Main loop: tick eligible agents
        while True:
            if self.is_work_hours():
                agents = self.get_agents_due_for_tick()
                for agent in agents:
                    self.tick_agent(agent)
            sleep(60)  # Check every minute
```

### 2. Agent Registry

**Purpose**: Load and manage agent lifecycle

**Key Features**:
- Load agents from config JSON (from M365-Agent-Provisioning)
- Map agents to roles (CEO, Developer, PM, etc.)
- Initialize CrewAI agents with role-specific configs
- Provide MCP client to each agent

**Data Flow**:
```
agents.json → Agent Registry → CrewAI Agent instances
                  ↓
          Role definitions applied
                  ↓
          MCP client injected
```

### 3. Role Definitions

**Purpose**: Define behavior patterns for different job roles

**Structure**:
```python
class Role:
    name: str
    responsibilities: List[str]
    email_check_frequency: timedelta  # How often to check email
    response_time_sla: timedelta      # How quickly to respond
    meeting_preferences: MeetingPreferences
    communication_style: str

class MeetingPreferences:
    auto_accept_from: List[str]  # Auto-accept meetings from these roles
    decline_outside_hours: bool
    buffer_between_meetings: timedelta
```

**Example Roles**:

#### CEO
```python
CEO = Role(
    name="CEO",
    responsibilities=["Strategic decisions", "Team oversight", "Stakeholder communication"],
    email_check_frequency=timedelta(minutes=30),
    response_time_sla=timedelta(hours=1),
    meeting_preferences=MeetingPreferences(
        auto_accept_from=["CTO", "CFO", "Board"],
        decline_outside_hours=True,
        buffer_between_meetings=timedelta(minutes=15)
    ),
    communication_style="concise, strategic"
)
```

#### Developer
```python
DEVELOPER = Role(
    name="Developer",
    responsibilities=["Write code", "Code reviews", "Bug fixes", "Technical discussions"],
    email_check_frequency=timedelta(hours=1),
    response_time_sla=timedelta(hours=4),
    meeting_preferences=MeetingPreferences(
        auto_accept_from=["Tech Lead", "Product Manager"],
        decline_outside_hours=True,
        buffer_between_meetings=timedelta(minutes=5)
    ),
    communication_style="technical, detailed"
)
```

### 4. Behavior Engine

**Purpose**: Determine how agents respond to events (emails, meetings, etc.)

**Strategy**: Hybrid rule-based + LLM approach

```
Event → Rules Engine → Decision
           │
           ├─ Simple case? → Execute rule
           │
           └─ Complex case? → LLM decision
```

**Rule-Based Behaviors** (fast, deterministic):

1. **Email Response Rules**:
   - From CEO → Respond within 1 hour
   - Keyword "urgent" → High priority
   - CC'd only → Lower priority
   - Marketing emails → Archive

2. **Meeting Acceptance Rules**:
   - From direct manager → Auto-accept
   - Conflicts with existing meeting → Decline
   - Outside work hours → Decline
   - Optional meetings → Accept 70% of the time (randomized)

3. **Communication Templates**:
   - Quick replies for common scenarios
   - Role-appropriate tone
   - Context-aware (project names, names, etc.)

**LLM Behaviors** (flexible, context-aware):

Used for complex scenarios that don't fit rules:
- Multi-threaded email conversations
- Ambiguous meeting requests
- Cross-department collaboration
- Creative problem-solving

### 5. MCP Client

**Purpose**: Interface with Microsoft 365 via MCP server

**HTTP-Based Implementation**:
```python
class MCPClient:
    def __init__(self, bearer_token: str):
        self.base_url = "https://mcp.nstop.no"
        self.token = bearer_token

    def call_tool(self, tool_name: str, arguments: dict) -> dict:
        response = requests.post(
            f"{self.base_url}/tools/call",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"name": tool_name, "arguments": arguments}
        )
        return response.json()
```

**Available Tools**:
- `getInbox(limit, filter)` - Get inbox messages
- `sendMail(to, subject, body)` - Send email
- `replyToMail(messageId, body)` - Reply to thread
- `searchMail(query)` - Search mailbox
- `getEvents(timeframe)` - Get calendar events
- `createEvent(subject, start, end, attendees)` - Create meeting
- `updateEvent(eventId, changes)` - Update meeting
- `deleteEvent(eventId)` - Cancel meeting

### 6. State Database

**Purpose**: Track agent activity and conversation history

**Schema**:
```sql
-- Agent activity log
CREATE TABLE activity_log (
    id INTEGER PRIMARY KEY,
    agent_email TEXT,
    action TEXT,  -- 'check_email', 'send_email', 'schedule_meeting'
    timestamp DATETIME,
    details JSON
);

-- Email threads
CREATE TABLE email_threads (
    thread_id TEXT PRIMARY KEY,
    subject TEXT,
    participants JSON,
    last_message_at DATETIME,
    message_count INTEGER
);

-- Meeting history
CREATE TABLE meetings (
    event_id TEXT PRIMARY KEY,
    organizer TEXT,
    subject TEXT,
    start_time DATETIME,
    end_time DATETIME,
    attendees JSON,
    status TEXT  -- 'scheduled', 'completed', 'cancelled'
);

-- Agent state
CREATE TABLE agent_state (
    agent_email TEXT PRIMARY KEY,
    last_tick_at DATETIME,
    unread_count INTEGER,
    pending_tasks JSON
);
```

## Agent Tick Cycle

When an agent is "ticked" (activated):

```
1. Check Inbox
   ↓
2. Identify New/Unread Emails
   ↓
3. For Each Email:
   a. Apply behavior rules
   b. Decide: respond, archive, forward, ignore
   c. If respond: generate reply (template or LLM)
   d. Execute action via MCP
   ↓
4. Check Calendar
   ↓
5. Identify New Meeting Invites
   ↓
6. For Each Invite:
   a. Check meeting preferences
   b. Check for conflicts
   c. Decide: accept, decline, tentative
   d. Respond via MCP
   ↓
7. Proactive Tasks (role-specific)
   - CEO: Schedule weekly team meeting?
   - Dev: Send status update?
   - PM: Follow up on blockers?
   ↓
8. Log Activity to Database
   ↓
9. Sleep Until Next Tick
```

## CrewAI Integration

### Agent Definition

```python
from crewai import Agent, Task, Crew

# Define agent
agent = Agent(
    role=role.name,
    goal=f"Perform {role.name} responsibilities effectively",
    backstory=f"You are {agent_config.name}, {role.name} at the company.",
    tools=[mcp_client],  # MCP client as a CrewAI tool
    verbose=True
)

# Define recurring task
task = Task(
    description="Check email and respond appropriately",
    agent=agent,
    expected_output="Summary of actions taken"
)

# Create crew (can coordinate multiple agents)
crew = Crew(
    agents=[agent],
    tasks=[task],
    verbose=True
)
```

### Task Execution

CrewAI handles:
- Task planning
- Tool usage (MCP client)
- Agent coordination (for multi-agent scenarios)
- Execution logging

## Work Hours Simulation

### Time Acceleration

To test faster than real-time:

```python
class TimeSimulator:
    def __init__(self, acceleration_factor: float = 1.0):
        # 1.0 = real-time, 10.0 = 10x speed
        self.factor = acceleration_factor

    def sleep(self, seconds: float):
        time.sleep(seconds / self.factor)
```

### Daily Schedule Example

```
9:00am  - Morning email check (all agents)
9:30am  - CEO checks email again
10:00am - Developers check email
11:00am - Team standup meeting
12:00pm - Lunch (agents idle)
1:00pm  - Post-lunch email check
3:00pm  - Developers send status updates
4:00pm  - CEO schedules meetings for next week
5:00pm  - End of day (agents stop)
```

## Extensibility

### Adding a New Role

1. Define role in `src/agents/roles.py`
2. Add behavior rules in `src/behaviors/rules.py`
3. Update agent registry to recognize role
4. Add role-specific proactive tasks

### Adding a New MCP Tool

1. Add method to `src/mcp_client/client.py`
2. Register as CrewAI tool
3. Document in SCENARIOS.md

### Creating Custom Scenarios

1. Define scenario in `src/scenarios/`
2. Specify initial conditions (seed emails, meetings)
3. Define success criteria
4. Run via CLI: `python -m src.main scenario custom-scenario`

## Performance Considerations

### Scalability

- **10-20 agents**: No performance issues
- **50+ agents**: Consider async/concurrent execution
- **100+ agents**: Distribute across multiple processes

### Rate Limiting

Microsoft Graph API limits:
- ~2000 requests per second per app
- Per-user limits: varies by resource

Mitigation:
- Add delays between agent ticks
- Cache calendar/email data
- Batch operations where possible

### Database

SQLite is sufficient for:
- 10-20 agents
- 1000s of emails/meetings per day
- Local development

For production scale, consider PostgreSQL.

## Error Handling

### MCP Server Unavailable

```python
try:
    response = mcp_client.get_inbox()
except MCPServerError:
    # Log error, retry with exponential backoff
    # Skip this tick, agent will try again later
```

### Invalid Bearer Token

```python
if response.status_code == 401:
    # Token expired/invalid
    # Log error, disable agent
    # Notify admin to regenerate token
```

### Microsoft Graph API Errors

```python
if response.status_code == 429:  # Too many requests
    # Backoff and retry
    # Reduce agent tick frequency temporarily
```

## Security

### Token Storage

- Bearer tokens stored in `config/agents.json` (gitignored)
- File permissions: 600 (owner read/write only)
- Never log tokens

### Principle of Least Privilege

- Each agent can only access their own mailbox/calendar
- No cross-user access
- MCP server enforces per-token isolation

## Monitoring and Observability

### Metrics

- Emails processed per agent per day
- Response time to emails
- Meeting acceptance rate
- MCP API latency
- Error rate

### Logging

```python
logger.info(f"Agent {agent.name} checked email: {unread_count} unread")
logger.info(f"Agent {agent.name} sent reply to {recipient}")
logger.warning(f"Agent {agent.name} MCP call failed: {error}")
```

### Dashboard (Future)

- Real-time agent activity
- Email/meeting heatmaps
- Agent interaction graphs
- System health metrics
