# Setup Guide

## Prerequisites

- Python 3.10 or later
- pip or poetry for package management
- M365 tenant with provisioned synthetic users (CSV template included)
- MCP server for Microsoft 365 access - either:
  - Use the public MCP server at `mcp.nstop.no`
  - Self-host [MCP-Microsoft-Office](https://github.com/Aanerud/MCP-Microsoft-Office)
- (Optional) Anthropic API key for Claude-powered behaviors

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/microsoft/Synthetic-Employees.git
cd Synthetic-Employees
```

### 2. Create Virtual Environment

```bash
# Using venv
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Or using conda
conda create -n synthetic-employees python=3.10
conda activate synthetic-employees
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

Expected packages:
- crewai
- anthropic (for Claude API)
- requests (for MCP HTTP client)
- schedule (for work hours simulation)
- python-dotenv (for environment variables)

### 4. Verify Installation

```bash
python -m src.main --version
```

Expected output:
```
Synthetic Employees v1.0.0
```

## Configuration

### 1. Import Agent Configuration

The agent configuration comes from the M365-Agent-Provisioning project:

```bash
# Copy the generated config
cp ../M365-Agent-Provisioning/output/agents-config.json config/agents.json
```

**Important**: Ensure `agents-config.json` contains:
- Agent names, emails, roles, departments
- Valid MCP bearer tokens
- Correct MCP server URL

### 2. Environment Variables

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env`:

```env
# MCP Server Configuration
MCP_SERVER_URL=https://mcp.nstop.no

# Work Hours Configuration (local time)
WORK_START_HOUR=9
WORK_END_HOUR=17
TIMEZONE=America/Los_Angeles

# Agent Tick Configuration
TICK_INTERVAL_MINUTES=5
RANDOMIZE_TICKS=true

# LLM Configuration (optional, for advanced behaviors)
ANTHROPIC_API_KEY=sk-ant-...
LLM_MODEL=claude-3-5-sonnet-20241022

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/agents.log

# Database
DATABASE_PATH=data/agent_state.db

# Simulation Settings
TIME_ACCELERATION=1.0  # 1.0 = real-time, 10.0 = 10x speed
ENABLE_WEEKENDS=false
```

### Configuration Options Explained

#### Work Hours
- `WORK_START_HOUR`: When agents start (default: 9am)
- `WORK_END_HOUR`: When agents stop (default: 5pm)
- `TIMEZONE`: Local timezone for work hours
- `ENABLE_WEEKENDS`: Whether agents work on Sat/Sun

#### Tick Interval
- `TICK_INTERVAL_MINUTES`: Base interval for agent checks (default: 5 min)
- `RANDOMIZE_TICKS`: Add ±20% randomness to avoid patterns

#### LLM (Optional)
- `ANTHROPIC_API_KEY`: Required for complex decision-making
- `LLM_MODEL`: Claude model to use (sonnet recommended for balance)

If no API key provided, agents use rule-based behavior only.

#### Time Acceleration
- `1.0`: Real-time (1 simulated hour = 1 real hour)
- `10.0`: 10x speed (1 simulated hour = 6 real minutes)
- Useful for testing scenarios quickly

### 3. Create Required Directories

```bash
mkdir -p logs data
```

### 4. Initialize Database

```bash
python -m src.main init-db
```

This creates the SQLite database with required tables.

## Validate Setup

### Test 1: Load Agent Configuration

```bash
python -m src.main list-agents
```

Expected output:
```
✓ Loaded 12 agents from config/agents.json

Executive:
  - Sarah Chen (CEO) - sarah.chen@domain.com

Engineering:
  - Michael Rodriguez (CTO) - michael.rodriguez@domain.com
  - David Kim (Senior Developer) - david.kim@domain.com
  ...
```

### Test 2: Test MCP Connection

```bash
python -m src.main test-mcp
```

Expected output for each agent:
```
Testing MCP connectivity for 12 agents...

✓ sarah.chen@domain.com - Token valid, inbox accessible
✓ michael.rodriguez@domain.com - Token valid, inbox accessible
...
```

If any agent shows `✗`, their bearer token may be invalid. Regenerate tokens in M365-Agent-Provisioning project.

### Test 3: Dry Run

```bash
python -m src.main start --dry-run
```

This simulates agent activity without actually sending emails or creating meetings.

Expected output:
```
🚀 Starting Synthetic Employees (DRY RUN)

Work hours: 9:00 - 17:00 PST
Tick interval: 5 minutes (±20% randomization)
Agents: 12

[09:00] All agents starting work...
[09:00] Sarah Chen (CEO) - Would check inbox
[09:00] Michael Rodriguez (CTO) - Would check inbox
...
```

## Troubleshooting

### Issue: "No agents loaded"

**Cause**: Missing or invalid `config/agents.json`

**Solution**:
```bash
# Verify file exists
ls -l config/agents.json

# Validate JSON format
python -c "import json; json.load(open('config/agents.json'))"

# Re-import from M365-Agent-Provisioning
cp ../M365-Agent-Provisioning/output/agents-config.json config/agents.json
```

### Issue: "MCP server connection failed"

**Causes**:
- MCP server down
- Invalid bearer tokens
- Network connectivity

**Solution**:
```bash
# Test MCP server health
curl https://mcp.nstop.no/health

# Regenerate tokens in M365-Agent-Provisioning
cd ../M365-Agent-Provisioning
npm run generate-tokens
cp output/agents-config.json ../Synthetic-Employees/config/agents.json
```

### Issue: "Import Error: crewai not found"

**Cause**: Dependencies not installed or wrong Python environment

**Solution**:
```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt

# Verify installation
pip list | grep crewai
```

### Issue: "Permission denied: database"

**Cause**: Database file permissions or directory doesn't exist

**Solution**:
```bash
# Create data directory
mkdir -p data

# Fix permissions
chmod 755 data
chmod 644 data/agent_state.db  # If file exists
```

### Issue: "Anthropic API key invalid"

**Cause**: Wrong or expired API key

**Solution**:
This is optional. If you don't have a Claude API key:
```bash
# Remove from .env or comment out
# ANTHROPIC_API_KEY=...

# Agents will use rule-based behavior only
```

To get an API key:
1. Visit https://console.anthropic.com/
2. Create account or sign in
3. Generate API key
4. Add to `.env`

## Development Setup

### Install Development Dependencies

```bash
pip install -r requirements-dev.txt
```

Includes:
- pytest (testing)
- black (code formatting)
- mypy (type checking)
- pylint (linting)

### Run Tests

```bash
pytest tests/
```

### Code Formatting

```bash
black src/
```

### Type Checking

```bash
mypy src/
```

## Optional: IDE Setup

### VS Code

Install extensions:
- Python (Microsoft)
- Pylance
- Black Formatter

Create `.vscode/settings.json`:
```json
{
  "python.defaultInterpreterPath": "./venv/bin/python",
  "python.formatting.provider": "black",
  "editor.formatOnSave": true,
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": true
}
```

### PyCharm

1. Open project directory
2. Set interpreter: Settings → Project → Python Interpreter → venv/bin/python
3. Enable Black: Settings → Tools → Black → Enable on save

## Next Steps

Once setup is complete:

1. **Review ARCHITECTURE.md** to understand system design
2. **Review SCENARIOS.md** for example simulations to run
3. **Start with a simple scenario**:
   ```bash
   python -m src.main scenario morning-routine
   ```
4. **Monitor agent activity**:
   ```bash
   python -m src.main status
   ```
5. **Read DEPLOYMENT.md** for running agents continuously

## Production Checklist

Before running in a production-like environment:

- [ ] Valid MCP bearer tokens for all agents
- [ ] Database initialized
- [ ] Log rotation configured
- [ ] Error monitoring setup
- [ ] Backup strategy for `config/agents.json`
- [ ] Rate limiting configured (to avoid Graph API throttling)
- [ ] Work hours match actual business hours
- [ ] Timezone configured correctly
- [ ] (Optional) Claude API key and billing setup
