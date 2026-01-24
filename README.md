# Synthetic Employees

Multi-agent orchestration system that simulates 10-20 AI employees working in Microsoft 365, powered by CrewAI and Claude.

## True Purpose

> **This is a Shadow M365 Tenant for E+D testing.**

While this project simulates a company with 95 AI employees, its **primary purpose** is:

1. **People Search Testing** - Generate realistic people data and relationships
2. **Copilot Testing** - Create authentic content for Copilot scenarios
3. **Signal Measurement** - Produce measurable M365 activity patterns

### The Signal Generation Cycle

```
User -> Email to KAM -> Project Created -> Tasks Delegated -> Team Collaborates
                                                              |
                              <- Deliverable <- Review <- Documents Created
                                                              |
                                              All activity = M365 signals
```

Every action (emails, documents, shares, Teams messages) creates signals that E+D can measure and analyze.

## Overview

This project creates realistic workplace simulations where AI agents:
- Check and respond to emails
- Schedule and attend meetings
- Collaborate on projects
- Follow role-based behavior patterns
- Operate during work hours (9am-5pm, weekdays)

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Synthetic Employees (Python + CrewAI)                 │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐          │
│  │  Agent 1  │  │  Agent 2  │  │  Agent N  │          │
│  │   (CEO)   │  │   (Dev)   │  │   (PM)    │          │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘          │
│        │              │              │                  │
│        └──────────────┴──────────────┘                  │
│                       │                                 │
│            ┌──────────▼──────────┐                      │
│            │   MCP Client        │                      │
│            │ (HTTP → mcp.nstop.no)│                      │
│            └──────────┬──────────┘                      │
└───────────────────────┼──────────────────────────────────┘
                        │ Bearer Token Auth
                        ▼
┌─────────────────────────────────────────────────────────┐
│  MCP Server (mcp.nstop.no)                              │
│  → Microsoft Graph API → Microsoft 365                  │
└─────────────────────────────────────────────────────────┘
```

## Features

- **Role-based behavior**: Each agent has unique responsibilities and communication patterns
- **Work hours simulation**: Agents only active 9am-5pm on weekdays
- **Rule-based + LLM hybrid**: Fast rule-based decisions with LLM fallback for complex scenarios
- **MCP integration**: Secure access to Microsoft 365 via bearer tokens
- **Scenario support**: Pre-built scenarios for testing (team meetings, email threads, etc.)

## Quick Start

### Prerequisites

- Python 3.10+
- An M365 tenant with provisioned synthetic users
- MCP server for Microsoft 365 access (see [MCP-Microsoft-Office](https://github.com/Aanerud/MCP-Microsoft-Office))
- (Optional) Anthropic API key for Claude-powered behaviors

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/microsoft/Synthetic-Employees.git
cd Synthetic-Employees

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure agents
# Copy the example and add your agent credentials
cp config/agents.json.example config/agents.json
# Edit config/agents.json with your M365 user details

# 5. Configure environment
cp .env.example .env
# Edit .env with your MCP server URL and API keys

# 6. Start the simulation
python -m src.main start

# 7. Monitor agents
python -m src.main status
```

### Agent Configuration

The `config/agents.json` file contains your synthetic employee credentials. You can:
- Manually create entries for each M365 user
- Import from the included `textcraft-europe.csv` file using the CSV importer

**Important**: Never commit `config/agents.json` - it contains credentials. The file is in `.gitignore`.

### MCP Server Setup

This project requires an MCP server for Microsoft 365 access. Options:

1. **Use the public MCP server**: Configure `MCP_SERVER_URL=https://mcp.nstop.no` in `.env`
2. **Self-host**: Deploy [MCP-Microsoft-Office](https://github.com/Aanerud/MCP-Microsoft-Office)

## Documentation

- **[ARCHITECTURE.md](./ARCHITECTURE.md)**: System design and agent behavior
- **[SETUP.md](./SETUP.md)**: Installation and configuration
- **[DEPLOYMENT.md](./DEPLOYMENT.md)**: Running and monitoring agents
- **[SCENARIOS.md](./SCENARIOS.md)**: Example scenarios to run

## Project Structure

```
Synthetic-Employees/
├── src/
│   ├── main.py                 # CLI entry point
│   ├── agents/
│   │   ├── agent_registry.py   # Agent loading and management
│   │   └── roles.py            # Role definitions and behaviors
│   ├── crew/
│   │   └── crew_config.py      # CrewAI configuration
│   ├── mcp_client/
│   │   └── client.py           # MCP HTTP client
│   ├── scheduler/
│   │   └── scheduler.py        # Work hours and tick scheduler
│   └── behaviors/
│       └── rules.py            # Rule-based behavior engine
├── config/
│   └── agents.json             # Agent configuration (from Project 1)
└── data/
    └── agent_state.db          # SQLite state database
```

## Example Usage

### Run a Morning Routine

```bash
# All agents check email at 9am
python -m src.main scenario morning-routine
```

### Simulate a Team Meeting

```bash
# CEO schedules meeting, team responds
python -m src.main scenario team-meeting --participants "sarah.chen,david.kim,emily.johnson"
```

### Continuous Simulation

```bash
# Run agents continuously during work hours
python -m src.main start --duration 8h
```

## Agent Behavior

Each agent follows a behavior pattern based on their role:

### CEO (Sarah Chen)
- Checks email every 30 minutes
- Schedules weekly team meetings
- Responds to high-priority emails within 1 hour
- Delegates tasks to department heads

### Developers (David, Lisa, James)
- Check email every hour
- Respond to code review requests
- Participate in standups
- Update project status

### Product Manager (Emily)
- Reviews feature requests
- Coordinates with engineering
- Schedules planning meetings
- Tracks project milestones

## Monitoring

View real-time agent activity:

```bash
# Show current status
python -m src.main status

# Show activity log
python -m src.main logs --tail 50

# Show statistics
python -m src.main stats
```

## Requirements

- Python 3.10+
- M365 tenant with synthetic users provisioned
- MCP server access ([MCP-Microsoft-Office](https://github.com/Aanerud/MCP-Microsoft-Office))
- (Optional) Anthropic API key for Claude-powered advanced behaviors

## Technology Stack

- **CrewAI**: Multi-agent orchestration framework
- **Python 3.10+**: Runtime environment
- **SQLite**: Agent state persistence
- **Schedule**: Work hours simulation
- **Anthropic Claude**: LLM for complex decision-making (optional)

## Contributing

This is a simulation framework designed to be extended:

1. Add new roles in `src/agents/roles.py`
2. Create custom scenarios in `SCENARIOS.md`
3. Extend behavior rules in `src/behaviors/rules.py`
4. Add new MCP tools in `src/mcp_client/client.py`

## License

MIT

## Related Projects

- **[MCP-Microsoft-Office](https://github.com/Aanerud/MCP-Microsoft-Office)**: MCP server providing Microsoft 365 access via Graph API
- **Synthetic Users CSV**: The `textcraft-europe.csv` file contains 95 pre-defined synthetic employees for TextCraft Europe
