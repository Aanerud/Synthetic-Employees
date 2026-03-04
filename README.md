# Synthetic Employees

**AI agents that work in Microsoft 365 like real people.**

---

## The Problem

Test tenants have users but no behavior. Part 1 of this project populated a tenant with 95 realistic profiles. Part 2 gave those profiles an MCP server with 78 tools. But profiles and tools alone produce no signals. Nobody sends email. Nobody schedules meetings. Nobody collaborates.

People Search, Copilot, and the M365 signal pipeline need traffic. Not synthetic data injected into a database, but genuine Graph API operations from real user accounts that flow through the same pipeline production traffic uses.

## The Outcome

Synthetic Employees makes the test tenant behave like a real company. Each of the 95 employees:

- Checks their inbox on a schedule that matches their country and role
- Reads emails, decides how to respond, and sends replies
- Accepts or declines meeting invitations
- Delegates work to colleagues when a client request arrives
- Remembers what they have done and what remains unfinished

Every action produces a real M365 signal. The system generates the traffic that People Search, Copilot, and signal measurement depend on.

## How It Works

```
Pre-tick:   Python fetches Victoria's inbox via MCP (her own auth token)
                ↓
Brain:      agency copilot thinks as Victoria (free via Copilot subscription)
                ↓
Post-tick:  Python executes Victoria's decisions via MCP (send email, accept meeting)
```

The LLM never touches Microsoft 365 directly. Python handles authentication and execution. The LLM handles reasoning. Each employee authenticates with their own token through the [MCP Microsoft Office](https://github.com/Aanerud/MCP-Microsoft-Office) adapter, which calls the Graph API.

### The Three-Part System

| Part | Project | Purpose |
|------|---------|---------|
| 1 | [M365-Agent-Provisioning](https://github.com/Aanerud/M365-Agent-Provisioning) | Populate the tenant: 95 users, rich profiles, all 13 people data labels |
| 2 | [MCP Microsoft Office](https://github.com/Aanerud/MCP-Microsoft-Office) | Give agents tools: 78 Graph API operations via MCP protocol |
| **3** | **Synthetic Employees** (this project) | **Give agents agency: schedule, think, act, remember** |

## Architecture

```
config.yaml
     │
  main.py ──▶ EmployeeScheduler (per-employee, timezone-aware)
     │              │
     │         ConcurrencyManager (max 15 concurrent, circuit breaker)
     │              │
     │         TaskSelector (morning routine / inbox / proactive / end of day)
     │              │
     │         ┌────┴─────────────────────────────┐
     │         │                                   │
     │    DataFetcher                         ContextAssembler
     │    (MCP stdio → real inbox)            (DB → memory context)
     │         │                                   │
     │         └────────────┬──────────────────────┘
     │                      │
     │              AgencyCliRunner
     │              (agency copilot --agent employee-<role>)
     │                      │
     │              ActionExecutor
     │              (MCP stdio → send email, accept meeting)
     │                      │
     │              ResultParser → DB (activity log, memory, state)
```

### Per-Employee Scheduling

Each employee runs on their own clock. An Italian editor starts at 09:00 CET with a long lunch at 12:30. A Swedish developer starts at 08:00 CET with fika breaks. A Spanish writer observes the afternoon gap. Fourteen European countries, each with distinct work patterns.

### Agent Templates

Eight role-specific templates in `.github/agents/` define how each employee thinks. A KAM reads a client email and delegates to writers. An editor reviews submissions and provides feedback. A proofreader catches errors and returns corrections. Each template includes:

- Identity and persona (injected at runtime from persona files)
- Inbox and calendar data (fetched live from M365 before each tick)
- A constitution: ten rules that govern behavior
- A JSON output format that maps decisions to executable actions

### Memory

Agents remember across ticks. The database tracks:

- What emails they processed (to avoid re-reading)
- What items they flagged for follow-up
- What they know about colleagues and projects
- What actions they took last cycle

Each tick injects this context into the prompt, so the agent picks up where it left off.

## Quick Start

### Prerequisites

- Python 3.10+
- [MCP Microsoft Office](https://github.com/Aanerud/MCP-Microsoft-Office) server running at localhost:3000
- [Agency CLI](https://aka.ms/agency) installed (`agency copilot` in PATH)
- An M365 test tenant with provisioned users (Part 1)

### Install

```bash
git clone <repo-url>
cd Synthetic-Employees
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # Add your Azure AD credentials
cp config/agents.json.example config/agents.json  # Add employee entries
```

### Run

```bash
# Dry run (no real actions)
python -m src.main start --dry-run --duration 5m

# Single employee
python -m src.main start --agents victoria.palmer@<tenant>.onmicrosoft.com

# All employees
python -m src.main start

# Test MCP connectivity
python -m src.main test-mcp
```

### Test

The test suite has three layers. Start with offline, then online, then scenario.

```bash
# 1. Offline tests (no server, no tokens, no internet)
#    Validates scheduling, concurrency, task selection, JSON parsing,
#    DB operations, and the full pipeline assembly.
#    Expected: 11/11 passed
python tests/test_agency_v2.py

# 2. Online tests (requires MCP server at localhost:3000 + .env credentials)
#    Authenticates as Victoria Palmer, reads real inbox, sends real email,
#    verifies DataFetcher and ActionExecutor against live Graph API.
#    Expected: 18/18 passed (11 offline + 7 online)
python tests/test_agency_v2.py --online

# 3. Multi-agent scenario (requires MCP server + .env)
#    Victoria sends a project request to Anna (KAM).
#    Anna's agent reads inbox and decides actions.
#    Francois's agent reads inbox and responds.
#    Three modes:
python tests/test_scenario_e2e.py --dry-run        # Auth + fetch only
python tests/test_scenario_e2e.py --skip-agency     # Full MCP, mock brain
python tests/test_scenario_e2e.py                   # Full: Agency CLI + MCP

# Other unit tests (pytest)
pytest tests/test_communication_channel.py -v       # 18 tests
pytest tests/test_rate_limiting.py -v               # 18 tests
python tests/test_npc_lifecycle.py                  # Pulse, projects, KAM
```

If offline tests pass but online tests fail, check:
- Is the MCP server running? (`curl http://localhost:3000`)
- Is `.env` configured with valid Azure AD credentials?
- Are you rate-limited? (The token exchange allows 20 requests per 15 minutes)

## Project Structure

```
Synthetic-Employees/
├── .github/agents/              8 role-specific agent templates
├── config.yaml                  Central configuration (schedules, concurrency, rate limits)
├── agents/                      95 persona folders (persona.json, background.md, etc.)
├── src/
│   ├── main.py                  CLI entry point and async orchestrator
│   ├── agency/
│   │   ├── cli_runner.py        Agency CLI subprocess wrapper
│   │   ├── data_fetcher.py      Pre-tick: fetch inbox/calendar via MCP
│   │   ├── action_executor.py   Post-tick: execute JSON actions via MCP
│   │   └── result_parser.py     Parse output, update DB
│   ├── scheduler/
│   │   ├── employee_scheduler.py   Per-employee timezone-aware scheduling
│   │   └── cultural_schedules.py   14 European country work patterns
│   ├── concurrency/
│   │   └── manager.py           Semaphore, priority queue, circuit breaker
│   ├── tasks/
│   │   ├── task_selector.py     Pick the right task for each wake-up
│   │   └── task_types.py        Task definitions and instructions
│   ├── memory/
│   │   └── context_assembler.py Build prompt context from DB
│   ├── mcp_client/
│   │   ├── client.py            HTTP MCP client
│   │   └── stdio_client.py      Stdio MCP client (real Graph API)
│   ├── auth/
│   │   ├── token_manager.py     MSAL ROPC authentication
│   │   └── mcp_token_manager.py Graph token → MCP JWT exchange
│   ├── database/
│   │   ├── schema.sql           SQLite schema
│   │   └── db_service.py        Database operations
│   └── behaviors/
│       ├── pulse.py             Scheduled behavior system
│       ├── pulse_definitions.py Role-specific daily routines
│       ├── communication_channel.py  Email vs Teams selection
│       └── rate_limiter.py      Human-like rate limiting
├── tests/
│   ├── test_agency_v2.py        Main suite: 11 offline + 7 online tests
│   ├── test_scenario_e2e.py     Multi-agent interaction scenario
│   ├── test_communication_channel.py
│   ├── test_rate_limiting.py
│   └── test_npc_lifecycle.py
└── textcraft-europe.csv         95 employee seed data
```

## Related Projects

| Project | Role |
|---------|------|
| [M365-Agent-Provisioning](https://github.com/Aanerud/M365-Agent-Provisioning) | Part 1: Populate the tenant |
| [MCP Microsoft Office](https://github.com/Aanerud/MCP-Microsoft-Office) | Part 2: Agentic API for M365 |
| **Synthetic Employees** | Part 3: Agents that think and act |

## License

MIT
