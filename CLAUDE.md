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

## How It Works

95 NPC employees with unique personalities, roles, and backgrounds work together:

1. **External trigger**: A real user emails a Key Account Manager
2. **Project creation**: KAM extracts requirements, creates project
3. **Task delegation**: Tasks assigned to writers, editors, proofreaders
4. **Content generation**: Team produces documents, collaborates
5. **Signal emission**: All activity creates M365 signals (emails, files, shares, Teams messages)
6. **Deliverable**: User receives polished work product

## What Signals We Generate

| Signal Type | Source |
|-------------|--------|
| Emails | Assignment notifications, updates, deliverables |
| OneDrive files | Documents, drafts, deliverables |
| Shared documents | Collaboration between team members |
| Teams messages | Quick updates, acknowledgments |
| Calendar events | Meetings, deadlines |
| Project metadata | Database records |

## NPC Characteristics

Each NPC in `/agents/` has:
- `persona.json` - Identity, role, work preferences
- `background.md` - Personality type (MBTI), personal history
- `expertise.md` - Domain knowledge
- `relationships.md` - Team connections

## Key Workflows

- **KAM Workflow** (`src/behaviors/kam_workflow.py`): Handles external requests
- **Project Service** (`src/projects/project_service.py`): Task assignment, coordination
- **Communication Channel** (`src/behaviors/communication_channel.py`): Intelligent email vs Teams selection

## Remember

The goal is **authentic signal generation** for M365 testing.
Every email sent, document created, and collaboration performed is a measurable signal.
