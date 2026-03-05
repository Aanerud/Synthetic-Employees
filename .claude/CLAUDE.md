# Synthetic Employees - Claude Code Context

## True Purpose

This is a **Shadow M365 Tenant** for Experiences + Devices (E+D) testing.

**Primary Goals:**
1. Test **People Search** scenarios in Microsoft 365
2. Test **Microsoft Copilot** scenarios
3. Generate and measure **realistic enterprise signals**

**We are NOT just simulating employees. We are:**
- Creating a test bed for M365 features
- Generating authentic content, collaboration, and communication patterns
- Producing measurable signals that E+D can analyze

## System Overview

```
User Email → KAM → Project → Tasks → Team Collaboration → Deliverable
                                           ↓
                              All activity = M365 signals
```

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| MCP Client | `src/mcp_client/client.py` | Communicates with M365 via MCP server |
| Token Manager | `src/auth/mcp_token_manager.py` | MSAL auth → MCP JWT exchange |
| Agent Registry | `src/agents/agent_registry.py` | Loads/manages NPCs from config |
| Persona Loader | `src/agents/persona_loader.py` | Loads NPC personalities from `agents/` |
| Communication Channel | `src/behaviors/communication_channel.py` | Intelligent email vs Teams selection |
| Rate Limiter | `src/behaviors/rate_limiter.py` | Human-like rate limiting |
| KAM Workflow | `src/behaviors/kam_workflow.py` | Handles external requests |
| Pulse System | `src/behaviors/pulse.py` | Scheduled NPC behaviors |

### Authentication Flow

```
1. MSAL ROPC (username/password) → Azure AD token
2. Azure AD token → MCP server → MCP JWT
3. MCP JWT used for all M365 operations
```

Credentials in `.env`:
- `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`
- `DEFAULT_PASSWORD` for synthetic employees

### NPC Data

95 NPCs defined in two places:
1. **Seed data**: `textcraft-europe.csv` - All employee attributes
2. **Persona files**: `agents/<name>/` - Personality, background, expertise, relationships

Each NPC folder contains:
- `persona.json` - Identity, role, work preferences
- `background.md` - MBTI type, personal history
- `expertise.md` - Domain knowledge
- `relationships.md` - Team connections

## Signal Types Generated

| Signal | Source | M365 Feature |
|--------|--------|--------------|
| Emails | Assignment notifications, updates, deliverables | Exchange Online |
| Files | Documents, drafts, deliverables | OneDrive |
| Shares | Collaboration between team members | SharePoint |
| Teams messages | Quick updates, acknowledgments | Teams |
| Calendar events | Meetings, deadlines | Outlook Calendar |
| People data | Profiles, skills, relationships | People Search |

## Key Workflows

### 1. External Request → Deliverable

```
External User → Email to KAM
                    ↓
            KAM extracts requirements
                    ↓
            Project created in database
                    ↓
            Tasks assigned to team (email + Teams)
                    ↓
            Writers create content
                    ↓
            Editors/Proofreaders review
                    ↓
            Deliverable sent to external user
```

### 2. Communication Channel Selection

The system intelligently chooses email vs Teams:
- **Email**: External recipients, formal assignments, long content
- **Teams**: Internal quick updates, acknowledgments, replies

### 3. Rate Limiting

Human-like delays prevent robotic patterns:
- Per-role daily quotas
- Typing time simulation
- Reading time simulation
- Natural pauses between actions

## Documentation

| Document | Location | Content |
|----------|----------|---------|
| SETUP | `.claude/docs/SETUP.md` | Installation, configuration, troubleshooting |
| ARCHITECTURE | `.claude/docs/ARCHITECTURE.md` | System design, components, data flow |
| DEPLOYMENT | `.claude/docs/DEPLOYMENT.md` | Running, monitoring, scaling agents |
| SCENARIOS | `.claude/docs/SCENARIOS.md` | Pre-built test scenarios |
| Tests | `tests/README.md` | Test documentation and usage |

## Configuration Files

| File | Purpose | Tracked |
|------|---------|---------|
| `.env` | Credentials, settings | No (gitignored) |
| `.env.example` | Template for .env | Yes |
| `config/agents.json` | Agent tokens | No (gitignored) |
| `config/agents.json.example` | Template | Yes |
| `textcraft-europe.csv` | NPC seed data | Yes |

## Running the System

```bash
# Start agents
python -m src.main start

# Run specific scenario
python -m src.main scenario morning-routine

# Check status
python -m src.main status

# Run tests
pytest tests/
python tests/test_prysmian_workflow.py
```

## Remember

The goal is **authentic signal generation** for M365 testing.
Every email sent, document created, and collaboration performed is a measurable signal for E+D analysis.
