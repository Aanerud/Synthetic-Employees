# Tests

## Quick Start

```bash
# Offline (no server needed)
python tests/test_agency_v2.py

# Online (requires MCP server at localhost:3000)
python tests/test_agency_v2.py --online

# Multi-agent scenario
python tests/test_scenario_e2e.py --dry-run        # Preview
python tests/test_scenario_e2e.py --skip-agency     # MCP only
python tests/test_scenario_e2e.py                   # Full

# Other unit tests
pytest tests/test_communication_channel.py -v
pytest tests/test_rate_limiting.py -v
```

## Test Files

### Main Test Suite (`test_agency_v2.py`)

11 offline + 7 online tests. Run with `--online` for MCP server tests.

**Offline (no dependencies):**

| Test | Coverage |
|------|----------|
| Cultural Schedules | 14 country codes, timezone mapping, fallback |
| Employee Scheduler | Registration, timezone, first check-in, tick variance |
| Concurrency Manager | Circuit breaker, debounce, async workers |
| Task Types | All 7 types, instructions, custom append |
| Task Selector | Morning routine, pending, default, proactive |
| Agency CLI Runner | Backend selection, template mapping, JSON parsing |
| Result Parser | Success/failure, DB updates, memory persistence |
| Context Assembler | Conversations, knowledge, pending items, last cycle |
| Persona to Agency Vars | 12 Handlebars keys, values |
| Employee State DB | CRUD, error counting |
| Integration Smoke | Full pipeline: personas, scheduler, task, context, CLI command |

**Online (requires MCP server + .env credentials):**

| Test | Coverage |
|------|----------|
| Token Exchange | MSAL ROPC, Graph, MCP JWT |
| Read Inbox | Real emails via stdio MCP adapter |
| Calendar Events | Real calendar data |
| Send Email | Victoria sends to Francois (confirmed) |
| DataFetcher | Format real M365 data for Agency |
| ActionExecutor | Execute no-op action |
| Full Pipeline | Pre-tick fetch, context build, command assembly |

### Scenario Test (`test_scenario_e2e.py`)

Multi-agent interaction through the MCP server:

1. Victoria sends a project request to Anna (KAM)
2. Anna's agent reads inbox, decides to reply and delegate
3. Francois's agent reads inbox, sees assignment, responds
4. Verify emails arrived across mailboxes

Three modes: `--dry-run`, `--skip-agency`, or full.

### Other Tests

| File | Mode | Coverage |
|------|------|----------|
| `test_communication_channel.py` | Offline | Email vs Teams channel selection |
| `test_rate_limiting.py` | Offline | Rate limiting, retry, human patterns |
| `test_npc_lifecycle.py` | Offline | Pulse system, DB schema, KAM workflow |

## Prerequisites

**Offline tests:** `pip install pytest python-dotenv PyYAML`

**Online tests:** MCP server at localhost:3000, valid `.env` with Azure credentials, `config/agents.json`
