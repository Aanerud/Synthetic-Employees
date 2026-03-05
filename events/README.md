# Office Events

Drop YAML files here to create random office events that make the company feel alive. Each file describes one event that can fire randomly during the workday.

## How It Works

Every tick cycle (~60 seconds), the system checks each event file:
1. Is it within the time window?
2. Roll the probability dice
3. If it fires, pick affected agents and execute actions

Events generate real M365 signals (Teams messages, emails, calendar events) without needing Agency CLI.

## Creating an Event

```yaml
name: "bad_coffee"
description: "The coffee machine breaks down"
category: "office_life"              # office_life, emergency, social, hr, it

time_window: [9, 11]                 # Can fire 9am-11am
probability: 0.05                    # 5% chance per tick cycle
cooldown_minutes: 10080              # Max once per week
requires_workday: true

scope: "all_active"                  # Who is affected (see Scope below)

actions:
  - type: "teams_channel_message"
    channel: "general"
    templates:
      - "The coffee machine is broken again ☕"
      - "Who broke the coffee machine?"
    pick_agents: 3                   # 3 random agents post
```

## Scope Options

| Scope | Meaning |
|-------|---------|
| `all_active` | All employees currently in work hours |
| `department:Editorial` | Only employees in that department |
| `role:Key Account Manager` | Only employees with that role |
| `random:5` | Pick 5 random active employees |
| `country:Germany` | Only employees in that country |

## Action Types

| Type | What It Does | Signal |
|------|-------------|--------|
| `teams_channel_message` | Post in a Teams channel | Teams activity |
| `send_email` | Send email to someone | Exchange activity |
| `calendar_event` | Create a meeting | Calendar activity |
| `set_status` | Change Teams status | Presence signal |

## Examples

See the YAML files in this directory for working examples.

## Tips for Good Events

- **Low probability, high impact**: Fire drills (1%/month) are memorable
- **Cultural flavor**: Different offices react differently to events
- **Chain reactions**: One event can reference another (coffee → someone orders delivery)
- **Personality matters**: Include `pick_agents` to let random employees react
- **Templates with variety**: Multiple message templates prevent repetition
