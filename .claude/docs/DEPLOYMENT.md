# Deployment Guide

## Running Agents

### Basic Usage

Start agents with default settings:

```bash
python -m src.main start
```

This will:
- Load agents from `config/agents.json`
- Run continuously during configured work hours
- Stop automatically at end of day
- Resume next work day

### Command Line Options

```bash
python -m src.main start [options]

Options:
  --duration DURATION    Run for specific duration (e.g., 8h, 30m, 1d)
  --dry-run              Simulate without making real API calls
  --agents AGENTS        Run specific agents only (comma-separated emails)
  --scenario SCENARIO    Run a predefined scenario
  --continuous           Run 24/7 (ignore work hours)
  --acceleration FACTOR  Time acceleration (e.g., 10 for 10x speed)
```

### Examples

```bash
# Run for 8 hours
python -m src.main start --duration 8h

# Run specific agents only
python -m src.main start --agents "sarah.chen@domain.com,david.kim@domain.com"

# Run at 10x speed for testing
python -m src.main start --acceleration 10 --duration 1h

# Dry run to preview behavior
python -m src.main start --dry-run --duration 30m
```

## Running in Background

### Using nohup (Linux/Mac)

```bash
nohup python -m src.main start > logs/nohup.out 2>&1 &

# Save process ID
echo $! > .pid

# View logs
tail -f logs/nohup.out

# Stop
kill $(cat .pid)
```

### Using screen (Linux/Mac)

```bash
# Start screen session
screen -S synthetic-employees

# Run agents
python -m src.main start

# Detach: Ctrl+A, then D

# Reattach later
screen -r synthetic-employees

# List sessions
screen -ls
```

### Using systemd (Linux)

Create `/etc/systemd/system/synthetic-employees.service`:

```ini
[Unit]
Description=Synthetic Employees Agent System
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/path/to/Synthetic-Employees
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/python -m src.main start
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Commands:
```bash
# Enable service
sudo systemctl enable synthetic-employees

# Start service
sudo systemctl start synthetic-employees

# Check status
sudo systemctl status synthetic-employees

# View logs
sudo journalctl -u synthetic-employees -f

# Stop service
sudo systemctl stop synthetic-employees
```

## Monitoring

### Real-time Status

```bash
# Show current agent status
python -m src.main status

# Refresh every 5 seconds
watch -n 5 "python -m src.main status"
```

Expected output:
```
Synthetic Employees Status
==========================

System:
  Status: Running
  Uptime: 2h 34m
  Work Hours: 9:00 - 17:00 PST
  Current Time: 11:34 PST

Agents: 12 active

Recent Activity (last 5 minutes):
  [11:32] Sarah Chen (CEO) - Checked email, 3 unread
  [11:31] David Kim (Developer) - Sent reply to code review
  [11:30] Emily Johnson (PM) - Scheduled meeting
  [11:29] Michael Rodriguez (CTO) - Checked email, 0 unread

Next Tick: 11:35 (1 minute)
```

### Activity Logs

```bash
# View recent activity
python -m src.main logs --tail 50

# Follow logs in real-time
python -m src.main logs --follow

# Filter by agent
python -m src.main logs --agent sarah.chen@domain.com

# Filter by action type
python -m src.main logs --action send_email
```

### Statistics

```bash
# Show statistics
python -m src.main stats

# Show stats for specific time range
python -m src.main stats --from "2024-01-15" --to "2024-01-16"

# Export stats to CSV
python -m src.main stats --export stats.csv
```

Expected output:
```
Agent Statistics (Today)
========================

Overall:
  Total Actions: 247
  Emails Sent: 89
  Emails Received: 158
  Meetings Created: 12
  Meetings Accepted: 34

By Agent:
  Sarah Chen (CEO)
    - Emails sent: 23
    - Emails received: 45
    - Meetings created: 5
    - Average response time: 32 minutes

  David Kim (Developer)
    - Emails sent: 12
    - Emails received: 28
    - Meetings accepted: 6
    - Average response time: 2.3 hours
  ...
```

## Scaling

### Adding More Agents

1. Provision new users in M365-Agent-Provisioning
2. Export updated config:
   ```bash
   cd ../M365-Agent-Provisioning
   npm run provision
   npm run export-to-synthetic-employees
   ```
3. Restart Synthetic-Employees:
   ```bash
   python -m src.main restart
   ```

New agents will be automatically loaded and activated.

### Performance Tuning

#### Tick Interval

Adjust how often agents check for new activity:

```env
# .env
TICK_INTERVAL_MINUTES=5  # Default
```

- Lower value = More responsive, higher API usage
- Higher value = Less responsive, lower API usage

Recommendations:
- **10-20 agents**: 5 minutes
- **20-50 agents**: 10 minutes
- **50+ agents**: 15-30 minutes

#### Concurrent Execution

For 50+ agents, enable parallel processing:

```python
# src/scheduler/scheduler.py

# Sequential (default, safe for 10-20 agents)
for agent in agents:
    self.tick_agent(agent)

# Parallel (for 50+ agents)
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=10) as executor:
    executor.map(self.tick_agent, agents)
```

### Distributed Deployment

For 100+ agents, distribute across multiple instances:

**Instance 1** (Executives + Management):
```bash
python -m src.main start --agents "sarah.chen@...,michael.rodriguez@..."
```

**Instance 2** (Engineering):
```bash
python -m src.main start --agents "david.kim@...,lisa.anderson@..."
```

**Instance 3** (Other departments):
```bash
python -m src.main start --agents "christopher.brown@...,amanda.martinez@..."
```

## Stopping Agents

### Graceful Shutdown

```bash
# Send SIGTERM
python -m src.main stop

# Or if running in foreground
Ctrl+C
```

Graceful shutdown will:
1. Finish current tick cycle
2. Save state to database
3. Log shutdown event
4. Exit cleanly

### Force Stop

```bash
# Find process
ps aux | grep "src.main"

# Kill process
kill -9 <PID>
```

**Warning**: Force stopping may leave agents in inconsistent state.

## Restarting Agents

```bash
# Stop and start
python -m src.main restart

# Restart specific agents only
python -m src.main restart --agents "sarah.chen@domain.com"
```

## Health Checks

### Automated Health Check

```bash
# Check if system is healthy
python -m src.main health

# Exit code 0 = healthy, non-zero = unhealthy
```

Health check verifies:
- Database accessible
- MCP server reachable
- All agent tokens valid
- No stuck agents (inactive > 1 hour)
- Log file writable

### Health Check Script

Create `scripts/health-check.sh`:

```bash
#!/bin/bash

if python -m src.main health; then
  echo "✓ System healthy"
  exit 0
else
  echo "✗ System unhealthy"
  # Send alert (email, Slack, etc.)
  exit 1
fi
```

Schedule with cron:
```bash
# Run health check every 15 minutes
*/15 * * * * /path/to/scripts/health-check.sh
```

## Error Recovery

### Automatic Retry

Agents automatically retry failed operations:

```python
# Exponential backoff
attempt = 0
max_attempts = 3
backoff = 1  # seconds

while attempt < max_attempts:
    try:
        response = mcp_client.get_inbox()
        break
    except MCPServerError as e:
        attempt += 1
        if attempt >= max_attempts:
            logger.error(f"Failed after {max_attempts} attempts")
            raise
        time.sleep(backoff)
        backoff *= 2  # Exponential backoff
```

### Error Notifications

Configure alerts for errors:

```python
# src/main.py

def send_alert(error: Exception):
    # Email alert
    # Slack webhook
    # PagerDuty
    pass
```

### Recovery from Database Corruption

```bash
# Backup existing database
cp data/agent_state.db data/agent_state.db.backup

# Reinitialize
python -m src.main init-db --force

# Restart agents
python -m src.main start
```

## Logging

### Log Levels

Configure in `.env`:
```env
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

- **DEBUG**: Verbose, all operations
- **INFO**: Normal operations (recommended)
- **WARNING**: Potential issues
- **ERROR**: Errors that didn't stop execution
- **CRITICAL**: Fatal errors

### Log Rotation

Using `logrotate` (Linux):

Create `/etc/logrotate.d/synthetic-employees`:

```
/path/to/Synthetic-Employees/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 your-username your-username
}
```

### Structured Logging

Logs are formatted as JSON for easy parsing:

```json
{
  "timestamp": "2024-01-15T11:34:22Z",
  "level": "INFO",
  "agent": "sarah.chen@domain.com",
  "action": "send_email",
  "details": {
    "to": "michael.rodriguez@domain.com",
    "subject": "Re: Q1 Planning"
  }
}
```

Parse logs with jq:
```bash
cat logs/agents.log | jq '.agent' | sort | uniq -c
```

## Backup and Recovery

### Backup Strategy

**Daily backups**:
```bash
#!/bin/bash
# scripts/backup.sh

DATE=$(date +%Y%m%d)
BACKUP_DIR=/backups/synthetic-employees

# Backup database
cp data/agent_state.db $BACKUP_DIR/agent_state_$DATE.db

# Backup config (includes bearer tokens!)
cp config/agents.json $BACKUP_DIR/agents_$DATE.json

# Compress old backups
find $BACKUP_DIR -name "*.db" -mtime +7 -exec gzip {} \;
find $BACKUP_DIR -name "*.json" -mtime +7 -exec gzip {} \;

# Delete backups older than 30 days
find $BACKUP_DIR -name "*.gz" -mtime +30 -delete
```

Schedule with cron:
```bash
# Daily backup at 2am
0 2 * * * /path/to/scripts/backup.sh
```

### Restore from Backup

```bash
# Stop agents
python -m src.main stop

# Restore database
cp /backups/synthetic-employees/agent_state_20240115.db data/agent_state.db

# Restore config
cp /backups/synthetic-employees/agents_20240115.json config/agents.json

# Restart agents
python -m src.main start
```

## Security

### Token Security

Protect bearer tokens:

```bash
# Restrict file permissions
chmod 600 config/agents.json
chmod 700 config/

# Ensure tokens not in version control
echo "config/agents.json" >> .gitignore
```

### Audit Logging

Track all agent actions:

```python
# All actions logged to database
INSERT INTO activity_log (agent_email, action, timestamp, details)
VALUES (?, ?, ?, ?)
```

Query audit log:
```bash
sqlite3 data/agent_state.db "SELECT * FROM activity_log WHERE action='send_email'"
```

## Troubleshooting

### Agents Not Running

**Check status**:
```bash
python -m src.main status
```

**Common causes**:
- Outside work hours
- Database locked
- Invalid configuration
- MCP server unreachable

### High API Usage

**Symptoms**:
- HTTP 429 errors (rate limited)
- Slow response times

**Solutions**:
1. Increase tick interval
2. Add delays between operations
3. Enable caching
4. Reduce number of active agents

### Agents Stuck

**Symptoms**:
- Agent hasn't ticked in > 1 hour
- No activity in logs

**Solutions**:
```bash
# Check for deadlocks
python -m src.main debug --agent sarah.chen@domain.com

# Force restart agent
python -m src.main restart --agent sarah.chen@domain.com
```

## Best Practices

1. **Start small**: Begin with 3-5 agents, scale up gradually
2. **Monitor closely**: Check logs and stats regularly in first week
3. **Use dry-run**: Test scenarios with `--dry-run` before running live
4. **Set work hours carefully**: Match actual business hours to avoid confusion
5. **Backup regularly**: Automate backups of database and config
6. **Rate limit**: Don't check email too frequently (5-10 min minimum)
7. **Handle errors gracefully**: Don't let one agent's failure stop others
8. **Document scenarios**: Keep track of interesting agent interactions
9. **Update tokens**: Regenerate bearer tokens monthly for security
10. **Test scenarios**: Validate expected behaviors before production

## Production Checklist

Before deploying to production:

- [ ] Tested with dry-run
- [ ] Validated all agent tokens
- [ ] Configured work hours correctly
- [ ] Set up logging and log rotation
- [ ] Configured automated backups
- [ ] Set up health checks
- [ ] Configured error alerts
- [ ] Documented recovery procedures
- [ ] Tested stop/start/restart
- [ ] Validated MCP server connectivity
- [ ] Set appropriate tick intervals
- [ ] Reviewed security settings
