# Scenarios

Pre-built scenarios for testing and demonstrating the Synthetic-Employees system.

## Running Scenarios

```bash
python -m src.main scenario <scenario-name> [options]

Options:
  --dry-run          Preview without executing
  --acceleration N   Run at Nx speed
  --participants     Comma-separated list of agent emails
```

## Basic Scenarios

### 1. Morning Routine

**Description**: All agents start their work day by checking email.

**Duration**: ~5 minutes

**What happens**:
1. All agents check inbox at 9:00am
2. Agents with unread emails process them
3. High-priority emails get immediate responses
4. Lower-priority emails queued for later

**Run**:
```bash
python -m src.main scenario morning-routine
```

**Expected outcomes**:
- All agents show "checked email" activity
- ~40-60% of agents have unread emails
- ~20-30% send replies
- Activity logged to database

---

### 2. Quick Email Exchange

**Description**: Two agents have a short email conversation.

**Duration**: ~10 minutes

**What happens**:
1. Agent A sends email to Agent B
2. Agent B receives and responds within 1 tick cycle
3. Agent A replies back
4. Conversation ends naturally after 2-3 exchanges

**Run**:
```bash
python -m src.main scenario email-exchange \
  --participants "sarah.chen@domain.com,michael.rodriguez@domain.com"
```

**Customization**:
```python
# Seed email from CEO to CTO
{
  "from": "sarah.chen@domain.com",
  "to": "michael.rodriguez@domain.com",
  "subject": "Q1 Planning",
  "body": "Hi Michael, can we schedule time to discuss Q1 priorities?"
}
```

**Expected outcomes**:
- 2-3 email exchanges
- Appropriate response times based on roles
- Meeting scheduled as result (optional)

---

### 3. Team Meeting

**Description**: CEO schedules a meeting, team members respond.

**Duration**: ~15 minutes

**What happens**:
1. CEO creates meeting invite for 5-8 attendees
2. Invites sent via calendar
3. Each agent checks calendar and decides: accept/decline/tentative
4. Responses logged
5. CEO receives notifications

**Run**:
```bash
python -m src.main scenario team-meeting \
  --participants "sarah.chen@domain.com,michael.rodriguez@domain.com,emily.johnson@domain.com,david.kim@domain.com"
```

**Meeting details**:
```python
{
  "subject": "Q1 Planning Meeting",
  "start": "2024-01-20T14:00:00Z",
  "end": "2024-01-20T15:00:00Z",
  "attendees": [...],
  "organizer": "sarah.chen@domain.com"
}
```

**Expected outcomes**:
- 80-90% acceptance rate
- Conflicts detected and declined appropriately
- Tentative responses if uncertain
- Meeting shows in all calendars

---

### 4. Code Review Request

**Description**: Senior developer requests code review from team.

**Duration**: ~20 minutes

**What happens**:
1. Senior dev sends code review request email
2. Tagged developers receive notification
3. Each developer checks their workload
4. Developers respond: accept, suggest alternate reviewer, or decline
5. One developer accepts and reviews

**Run**:
```bash
python -m src.main scenario code-review \
  --participants "david.kim@domain.com,lisa.anderson@domain.com,james.wilson@domain.com"
```

**Expected outcomes**:
- 1-2 developers accept review
- Response within role-appropriate SLA
- Technical tone in communications
- Follow-up email with review feedback

---

## Intermediate Scenarios

### 5. Project Kickoff

**Description**: Product Manager starts new project with email thread and planning meeting.

**Duration**: ~30 minutes

**What happens**:
1. PM sends project kickoff email to team
2. Team members read and respond with questions
3. Email thread develops (5-10 messages)
4. PM schedules kickoff meeting
5. Team accepts meeting
6. Follow-up emails with action items

**Run**:
```bash
python -m src.main scenario project-kickoff \
  --participants "emily.johnson@domain.com,david.kim@domain.com,lisa.anderson@domain.com,jennifer.lee@domain.com"
```

**Expected outcomes**:
- Multi-threaded email conversation
- 90%+ meeting acceptance
- Realistic project-related questions
- Action items captured in emails

---

### 6. Daily Standup

**Description**: Engineering team's daily standup coordination.

**Duration**: ~25 minutes

**What happens**:
1. Tech lead sends standup reminder at 9:45am
2. Developers send status updates
3. Blockers identified
4. Tech lead summarizes and sends to PM
5. PM responds to blockers

**Run**:
```bash
python -m src.main scenario daily-standup \
  --participants "michael.rodriguez@domain.com,david.kim@domain.com,lisa.anderson@domain.com,james.wilson@domain.com"
```

**Expected outcomes**:
- All developers send status
- 1-2 blockers identified
- PM follows up on blockers
- Summary email sent

---

### 7. Urgent Bug Report

**Description**: High-priority bug reported, team responds urgently.

**Duration**: ~45 minutes

**What happens**:
1. QA engineer reports critical bug
2. Email marked "URGENT" triggers fast response
3. Tech lead assigns to developer
4. Developer acknowledges within 15 minutes
5. Status updates every 15 minutes
6. Resolution email sent

**Run**:
```bash
python -m src.main scenario urgent-bug \
  --participants "robert.taylor@domain.com,michael.rodriguez@domain.com,david.kim@domain.com"
```

**Expected outcomes**:
- Sub-15-minute response times
- Multiple status updates
- Escalation if not resolved in 1 hour
- CEO looped in if critical

---

### 8. Cross-Department Collaboration

**Description**: Marketing requests feature from Engineering, coordination required.

**Duration**: ~1 hour

**What happens**:
1. Marketing manager emails feature request
2. Product manager triages request
3. PM schedules meeting with engineering
4. Engineering provides feasibility assessment
5. PM relays to marketing with timeline
6. Marketing confirms or negotiates

**Run**:
```bash
python -m src.main scenario cross-department \
  --participants "christopher.brown@domain.com,emily.johnson@domain.com,michael.rodriguez@domain.com,david.kim@domain.com"
```

**Expected outcomes**:
- Multi-department email thread
- Meeting scheduled
- Technical assessment provided
- Timeline agreed upon

---

## Advanced Scenarios

### 9. Weekly Executive Summary

**Description**: Department heads send weekly reports to CEO.

**Duration**: ~2 hours

**What happens**:
1. Every Friday at 4pm, department heads send reports
2. CEO reviews reports
3. CEO responds with feedback or questions
4. Follow-up discussions as needed
5. CEO synthesizes into exec summary

**Run**:
```bash
python -m src.main scenario weekly-summary \
  --participants "sarah.chen@domain.com,michael.rodriguez@domain.com,christopher.brown@domain.com,daniel.thompson@domain.com"
```

**Expected outcomes**:
- All department heads send reports
- CEO provides feedback to each
- Consistent Friday timing
- Executive summary generated

---

### 10. Hiring Workflow

**Description**: HR Manager coordinates interview process with team.

**Duration**: ~3 hours

**What happens**:
1. HR sends candidate profile to hiring manager
2. Hiring manager reviews and approves
3. HR schedules interviews with team
4. Interviewers accept meeting invites
5. Post-interview feedback collected
6. Hiring decision made

**Run**:
```bash
python -m src.main scenario hiring-workflow \
  --participants "daniel.thompson@domain.com,michael.rodriguez@domain.com,david.kim@domain.com,emily.johnson@domain.com"
```

**Expected outcomes**:
- Interview slots scheduled
- All interviewers participate
- Feedback emails sent
- Decision communicated

---

### 11. Product Launch

**Description**: Full product launch coordination across all departments.

**Duration**: ~8 hours (full work day)

**What happens**:
1. CEO announces launch date
2. Department heads create action plans
3. Engineering finalizes features
4. Marketing prepares campaigns
5. Sales prepares pitch
6. HR plans celebration event
7. Coordinated email updates
8. Launch day celebrations

**Run**:
```bash
python -m src.main scenario product-launch --acceleration 10
```

**Note**: Use time acceleration to complete in ~1 hour real time.

**Expected outcomes**:
- 50+ emails exchanged
- 5-10 meetings scheduled
- All departments coordinate
- Realistic launch timeline

---

### 12. Crisis Management

**Description**: Service outage, team responds urgently.

**Duration**: ~4 hours

**What happens**:
1. DevOps detects outage
2. CTO notified immediately
3. War room meeting scheduled within 15 minutes
4. Engineering team assembles
5. Status updates every 15 minutes
6. CEO informed of progress
7. Resolution and postmortem

**Run**:
```bash
python -m src.main scenario crisis-management \
  --participants "maria.garcia@domain.com,michael.rodriguez@domain.com,david.kim@domain.com,lisa.anderson@domain.com,sarah.chen@domain.com"
```

**Expected outcomes**:
- Immediate response (< 5 minutes)
- Frequent status updates
- Executive visibility
- Postmortem scheduled

---

## Custom Scenarios

### Creating Custom Scenarios

1. Define scenario in `src/scenarios/custom/`
2. Specify initial conditions
3. Define expected behaviors
4. Set success criteria

Example:

```python
# src/scenarios/custom/onboarding.py

from src.scenarios.base import Scenario

class OnboardingScenario(Scenario):
    name = "onboarding"
    description = "New employee onboarding process"
    duration_minutes = 120

    def setup(self):
        # Seed initial email
        self.send_email(
            from_email="daniel.thompson@domain.com",
            to_email="new.hire@domain.com",
            subject="Welcome to the Team!",
            body="..."
        )

    def validate(self):
        # Check expected outcomes
        assert self.count_emails(to="new.hire@domain.com") >= 5
        assert self.meeting_scheduled(attendees=["new.hire@domain.com"])

    def teardown(self):
        # Cleanup
        pass
```

Run custom scenario:
```bash
python -m src.main scenario custom/onboarding
```

---

## Scenario Testing

### Validation

Each scenario has success criteria:

```bash
# Run scenario and validate
python -m src.main scenario team-meeting --validate
```

Output:
```
✓ Meeting created
✓ All invites sent
✓ 80%+ acceptance rate
✓ Meeting on calendars
✗ CEO response time exceeded SLA (expected: 1h, actual: 1.5h)

Scenario: PASSED (4/5 checks)
```

### Metrics

Track scenario metrics:

```bash
python -m src.main scenario team-meeting --metrics
```

Output:
```
Scenario Metrics: Team Meeting
==============================

Timing:
  Start: 10:00:00
  End: 10:15:23
  Duration: 15m 23s

Actions:
  Emails sent: 1
  Calendar invites: 1
  Responses: 4 accept, 0 decline, 0 tentative

Response Times:
  Average: 4m 12s
  Min: 2m 5s (David Kim)
  Max: 7m 38s (Amanda Martinez)

Success Rate: 100%
```

---

## Batch Running Scenarios

Run multiple scenarios sequentially:

```bash
python -m src.main scenario-batch \
  morning-routine \
  email-exchange \
  team-meeting \
  daily-standup
```

Or create a scenario suite:

```yaml
# scenarios/suites/daily.yaml
name: Daily Operations
scenarios:
  - morning-routine
  - daily-standup
  - email-exchange
  - team-meeting
```

Run:
```bash
python -m src.main scenario-suite daily
```

---

## Scenario Best Practices

1. **Start simple**: Begin with morning-routine, validate basics
2. **Use dry-run**: Test scenarios with `--dry-run` first
3. **Accelerate time**: Use `--acceleration 10` for faster testing
4. **Validate outcomes**: Use `--validate` to check success criteria
5. **Review logs**: Check logs after each scenario for issues
6. **Iterate**: Refine scenarios based on observed behaviors
7. **Document**: Record interesting agent interactions
8. **Clean up**: Reset database between major scenario runs
9. **Monitor API usage**: Watch for rate limiting during long scenarios
10. **Test realistic**: Use actual work schedules, not 24/7

---

## Troubleshooting Scenarios

### Scenario Doesn't Start

**Causes**:
- Agents not configured
- Outside work hours
- MCP server unavailable

**Solution**:
```bash
# Check prerequisites
python -m src.main preflight-check

# Run with debug logging
python -m src.main scenario team-meeting --log-level DEBUG
```

### Unexpected Behavior

**Causes**:
- Rule logic error
- LLM hallucination
- Rate limiting

**Solution**:
```bash
# Review agent decisions
python -m src.main logs --scenario team-meeting --action decision

# Analyze behavior
python -m src.main debug-scenario team-meeting
```

### Low Activity

**Causes**:
- Long tick intervals
- Agents filtering out actions
- MCP errors

**Solution**:
```bash
# Reduce tick interval temporarily
python -m src.main scenario team-meeting --tick-interval 1

# Check MCP connectivity
python -m src.main test-mcp
```

---

## Contributing Scenarios

Share interesting scenarios with the community:

1. Document scenario in this file
2. Include expected outcomes
3. Provide example run commands
4. Note any special requirements
5. Submit pull request

Example template:

```markdown
### X. Scenario Name

**Description**: Brief description

**Duration**: Estimated time

**What happens**:
1. Step by step flow

**Run**:
```bash
python -m src.main scenario scenario-name
```

**Expected outcomes**:
- Outcome 1
- Outcome 2
```
