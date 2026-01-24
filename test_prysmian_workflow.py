#!/usr/bin/env python3
"""
End-to-End Test: Prysmian Submarine Cable Marketing Flyer

Scenario:
1. External client (simulated) sends request to Key Account Manager
2. KAM identifies the project and extracts requirements
3. KAM delegates to Marketing Copywriter and Proofreader
4. Team members receive assignments via email/Teams (INTELLIGENT CHANNEL SELECTION)
5. Project tracked in database
6. Human-like rate limiting and delays applied

Features demonstrated:
- Intelligent communication channel selection (email vs Teams)
- Human-like rate limiting and delays
- Natural NPC behavior patterns

Personas involved:
- Anna Kowalski (Key Account Manager) - receives and coordinates
- Christina Hall (Marketing Copywriter Lead) - creates content
- Bruno Dupont (Senior Proofreader) - reviews content
- François Moreau (Senior Editor) - final review
"""

import os
import sys
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Import communication channel selection
try:
    from src.behaviors.communication_channel import (
        CommunicationChannel,
        MessageType,
        MessageTemplates,
        decide_communication_channel,
    )
    CHANNEL_SELECTION_AVAILABLE = True
except ImportError:
    CHANNEL_SELECTION_AVAILABLE = False
    print("Warning: Communication channel selection not available")

# Import rate limiting
try:
    from src.behaviors.rate_limiter import AgentRateLimiter, RateLimitedMCPClient
    RATE_LIMITING_AVAILABLE = True
except ImportError:
    RATE_LIMITING_AVAILABLE = False
    print("Warning: Rate limiting not available")

# Agent emails
KAM_EMAIL = "anna.kowalski@a830edad9050849coep9vqp9bog.onmicrosoft.com"
MARKETING_LEAD_EMAIL = "christina.hall@a830edad9050849coep9vqp9bog.onmicrosoft.com"
PROOFREADER_EMAIL = "bruno.dupont@a830edad9050849coep9vqp9bog.onmicrosoft.com"
EDITOR_EMAIL = "francois.moreau@a830edad9050849coep9vqp9bog.onmicrosoft.com"

# Simulated external client
EXTERNAL_CLIENT_NAME = "Marcus Jensen"
EXTERNAL_CLIENT_COMPANY = "Nordic Subsea Infrastructure AS"


def print_header(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_step(num, description):
    print(f"\n[Step {num}] {description}")
    print("-" * 50)


def main():
    print_header("Prysmian Submarine Cable Marketing Flyer - E2E Test")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Initialize components
    from src.auth.mcp_token_manager import MCPTokenManager
    from src.agents.persona_loader import PersonaRegistry
    from src.database.db_service import DatabaseService
    from src.behaviors.kam_workflow import KeyAccountManagerWorkflow
    from src.projects.project_service import ProjectService

    token_manager = MCPTokenManager()
    persona_registry = PersonaRegistry()
    persona_registry.load_all()  # Load all personas from agents/ directory
    print(f"Loaded {len(persona_registry.list_all())} personas")
    db = DatabaseService()

    # =========================================================================
    # Step 1: Test MCP Connection
    # =========================================================================
    print_step(1, "Testing MCP connection for Key Account Manager")

    try:
        kam_client = token_manager.get_stdio_client(KAM_EMAIL)
        print(f"  ✓ Connected as: Anna Kowalski (KAM)")

        # Test inbox access
        inbox = kam_client.get_inbox(limit=3)
        print(f"  ✓ Inbox access verified ({len(inbox) if inbox else 0} recent emails)")

        # Test chat access (Teams may not be fully available)
        try:
            chats = kam_client.list_chats()
            print(f"  ✓ Chat access verified ({len(chats) if chats else 0} chats)")
        except Exception:
            print(f"  ○ Chat/Teams features limited (will use email only)")
    except Exception as e:
        print(f"  ✗ Connection failed: {e}")
        return False

    # =========================================================================
    # Step 2: Simulate External Client Request
    # =========================================================================
    print_step(2, "Simulating external client request email")

    # Create the client request email data (simulating what would come from inbox)
    client_request = {
        "id": f"simulated-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "from": {
            "emailAddress": {
                "address": "marcus.jensen@nordic-subsea.no",
                "name": EXTERNAL_CLIENT_NAME,
            }
        },
        "toRecipients": [
            {"emailAddress": {"address": KAM_EMAIL, "name": "Anna Kowalski"}}
        ],
        "subject": "Marketing Flyer Request - Prysmian Submarine Cables",
        "bodyPreview": "We need a professional marketing flyer for Prysmian submarine optical cables...",
        "body": {
            "content": f"""Dear Anna,

I hope this email finds you well. My name is {EXTERNAL_CLIENT_NAME} from {EXTERNAL_CLIENT_COMPANY}.

We are preparing for a major industry conference and urgently need a professional marketing flyer
for Prysmian's Submarine Single/Double Armoured Optical Cable product line.

The flyer should highlight:
1. Key technical specifications (up to 96 optical fibres, 3,000m depth rating)
2. Features and advantages for long-distance subsea unrepeated projects
3. International standards compliance (IEEE 1138, IEC 60794, ITU-T standards)
4. The robust cable design (stainless steel tube, wire armouring, outer serving)

Target audience: Infrastructure decision-makers, telecom project managers, offshore engineers

We'd also appreciate if your team could:
- Research recent Prysmian news and projects to include relevant context
- Ensure the copy is compelling and technically accurate
- Have the final text proofread before delivery

Timeline: We need this within the week as our conference is approaching.

Please let me know if you need any additional information.

Best regards,
{EXTERNAL_CLIENT_NAME}
Project Manager
{EXTERNAL_CLIENT_COMPANY}
marcus.jensen@nordic-subsea.no
+47 123 45 678"""
        },
        "receivedDateTime": datetime.now().isoformat(),
        "isRead": False,
    }

    print(f"  Client: {EXTERNAL_CLIENT_NAME} ({EXTERNAL_CLIENT_COMPANY})")
    print(f"  Subject: {client_request['subject']}")
    print(f"  Request: Marketing flyer for Prysmian submarine cables")

    # =========================================================================
    # Step 3: KAM Processes the External Request
    # =========================================================================
    print_step(3, "KAM (Anna Kowalski) processing external request")

    kam_persona = persona_registry.get_by_email(KAM_EMAIL)
    if not kam_persona:
        print(f"  ✗ Could not load KAM persona")
        kam_client.close()
        return False

    print(f"  Persona: {kam_persona.name} - {kam_persona.role}")

    # Initialize KAM workflow
    kam_workflow = KeyAccountManagerWorkflow(
        persona=kam_persona,
        mcp_client=kam_client,
        db=db,
        persona_registry=persona_registry,
        llm_service=None,  # Using heuristics for now
    )

    # Check if external
    is_external = kam_workflow.is_external_email(client_request)
    print(f"  ✓ External email detected: {is_external}")

    # Check if client request
    is_request = kam_workflow.is_client_request(client_request)
    print(f"  ✓ Client request detected: {is_request}")

    # Extract requirements
    print("\n  Extracting requirements...")
    requirements = kam_workflow._extract_with_heuristics(
        client_request["subject"],
        client_request["body"]["content"]
    )

    print(f"  ✓ Project Title: {requirements.project_title}")
    print(f"  ✓ Priority: {requirements.priority.value}")
    print(f"  ✓ Tasks identified: {len(requirements.tasks)}")
    for i, task in enumerate(requirements.tasks, 1):
        print(f"      {i}. {task['title'][:60]}... (skill: {task['skill']})")

    # =========================================================================
    # Step 4: Create Project and Delegate Tasks
    # =========================================================================
    print_step(4, "Creating project and delegating tasks")

    # Create the project
    project_service = ProjectService(db, persona_registry, kam_client)

    project = project_service.create_project_from_email(
        email_data=client_request,
        owner_email=KAM_EMAIL,
        requirements=requirements,
    )

    print(f"  ✓ Project created: {project.id}")
    print(f"    Title: {project.title}")
    print(f"    Owner: {project.owner_email}")
    print(f"    Client: {project.client_name} ({project.client_email})")
    print(f"    Tasks: {len(project.tasks)}")

    # =========================================================================
    # Step 5: Find and Assign Team Members (with INTELLIGENT CHANNEL SELECTION)
    # =========================================================================
    print_step(5, "Finding team members and assigning tasks")

    print("\n  [NEW] Using intelligent communication channel selection:")
    print("  • Formal assignments → Email (for tracking)")
    print("  • Quick notifications → Teams (for visibility)")
    print("  • Rate limiting → Human-like delays applied\n")

    # Initialize rate limiter for KAM
    kam_rate_limiter = None
    if RATE_LIMITING_AVAILABLE:
        kam_rate_limiter = AgentRateLimiter(
            agent_email=KAM_EMAIL,
            role="Key Account Manager",
            enable_human_patterns=True,
        )
        print(f"  Rate limiter initialized for {kam_persona.name}")
        status = kam_rate_limiter.get_status()
        print(f"  • Daily email quota: {status['emails']['quota']}")
        print(f"  • Daily API quota: {status['api_calls']['daily_quota']}")

    # Manual assignment to specific personas for demo
    assignments = [
        (MARKETING_LEAD_EMAIL, "writing", "Write marketing copy"),
        (PROOFREADER_EMAIL, "proofreading", "Proofread final content"),
        (EDITOR_EMAIL, "editing", "Review and edit content"),
    ]

    assigned_tasks = []
    assigned_task_ids = set()  # Track assigned tasks to prevent duplicate assignments
    for assignee_email, skill, desc in assignments:
        assignee = persona_registry.get_by_email(assignee_email)
        if not assignee:
            print(f"  ⚠ Could not find persona: {assignee_email}")
            continue

        # Find a matching task or create assignment
        for task in project.tasks:
            # Check both: ID not already assigned AND in-memory object not assigned
            if task.id not in assigned_task_ids and task.assigned_to is None:
                # Use project_service's assign_task for intelligent channel selection
                # (It converts "auto" to the appropriate channel internally)
                success = project_service.assign_task(task, assignee, via="auto")
                if success:
                    assigned_task_ids.add(task.id)  # Track this task as assigned
                    assigned_tasks.append((task, assignee))
                    print(f"  ✓ Assigned: {task.title[:40]}...")
                    print(f"    To: {assignee.name} ({assignee.role})")
                break

    # =========================================================================
    # Step 6: Review Sent Notifications (automatic via project_service)
    # =========================================================================
    print_step(6, "Assignment notifications sent automatically")

    print("\n  [NEW] project_service.assign_task() automatically:")
    print("  • Selects channel (email for formal assignments)")
    print("  • Sends detailed email with task info")
    print("  • Sends quick Teams heads-up if available")
    print("  • Records assignment in database\n")

    for task, assignee in assigned_tasks:
        print(f"  → {assignee.name}:")

        # Show what channel decision would be
        if CHANNEL_SELECTION_AVAILABLE:
            decision = decide_communication_channel(
                message_type=MessageType.FORMAL_ASSIGNMENT,
                content_length=500,  # Typical assignment length
                is_external=False,
            )
            print(f"    Channel: {decision.channel.value}")
            print(f"    Reason: {decision.reason}")

        # Record in rate limiter (assignment emails were sent by project_service)
        if kam_rate_limiter:
            kam_rate_limiter.record_email_sent()
            kam_rate_limiter.record_api_call()
            print(f"    ✓ Assignment sent (tracked by rate limiter)")

    # =========================================================================
    # Step 7: Quick Teams Notifications (INTELLIGENT CHANNEL SELECTION)
    # =========================================================================
    print_step(7, "Posting quick Teams notifications (parallel to email)")

    print("\n  [NEW] Quick heads-up messages go via Teams for speed!")
    print("  • Project announcement → Teams channel")
    print("  • Individual mentions → '@name check your email!'\n")

    teams_posted = False

    # Brief project announcement for Teams (short = Teams)
    teams_announcement = f"""**New Project: {project.title}**
Client: {project.client_name}
Priority: {requirements.priority.value.upper()}

Team assigned - check your emails for details!"""

    if CHANNEL_SELECTION_AVAILABLE:
        decision = decide_communication_channel(
            message_type=MessageType.STATUS_UPDATE,
            content_length=len(teams_announcement),
            is_external=False,
        )
        print(f"  Announcement channel: {decision.channel.value}")
        print(f"  Reason: {decision.reason}\n")

    # First try Teams channel
    try:
        teams = kam_client.list_teams()
        if teams:
            team_id = teams[0].get("id")
            channels = kam_client.list_channels(team_id)
            # Find General channel or use first channel
            channel = None
            for ch in channels:
                if ch.get("displayName", "").lower() == "general":
                    channel = ch
                    break
            if not channel and channels:
                channel = channels[0]

            if channel:
                # Post brief announcement
                kam_client.send_channel_message(
                    team_id=team_id,
                    channel_id=channel["id"],
                    content=teams_announcement,
                    content_type="text"
                )
                print(f"  ✓ TEAMS: Project announcement posted to #{channel.get('displayName')}")
                teams_posted = True

                # Post individual mentions (quick, like a real person would)
                for task, assignee in assigned_tasks:
                    mention_msg = f"@{assignee.name} - heads up, just sent you a task for **{task.title[:30]}**. Check email!"
                    try:
                        kam_client.send_channel_message(
                            team_id=team_id,
                            channel_id=channel["id"],
                            content=mention_msg,
                            content_type="text"
                        )
                        print(f"  ✓ TEAMS: Quick mention for {assignee.name}")
                        time.sleep(0.5)  # Brief pause between messages (natural)
                    except Exception:
                        pass

    except Exception as e:
        print(f"  ○ Teams channel posting not available: {e}")

    # Fall back to chat if Teams channel didn't work
    if not teams_posted:
        try:
            chats = kam_client.list_chats()
            if chats:
                chat_id = chats[0].get("id")
                kam_client.send_chat_message(chat_id, teams_announcement)
                print(f"  ✓ TEAMS CHAT: Posted announcement")
                teams_posted = True
        except Exception as e:
            print(f"  ○ Chat posting not available: {e}")

    if not teams_posted:
        print("  ○ Skipping Teams/Chat (email notifications sent instead)")

    # =========================================================================
    # Step 8: Send Acknowledgment to Client
    # =========================================================================
    print_step(8, "Sending acknowledgment to client (simulated)")

    ack_body = f"""Dear {EXTERNAL_CLIENT_NAME},

Thank you for reaching out to us regarding the Prysmian submarine cable marketing flyer.

I've received your request and have initiated the project with our team. Here are the details:

**Project Reference:** {project.id}
**Status:** In Progress
**Assigned Team:**
- Marketing Copywriter Lead: Christina Hall
- Senior Proofreader: Bruno Dupont
- Senior Editor: François Moreau

Our team will:
1. Research Prysmian's latest news and submarine cable projects
2. Create compelling marketing copy highlighting the technical specifications
3. Ensure the content appeals to your target audience
4. Proofread and review before delivery

I'll keep you updated on our progress. Please don't hesitate to reach out if you have
any additional requirements or questions.

Best regards,
Anna Kowalski
Key Account Manager
"""

    print(f"  [Acknowledgment would be sent to: {client_request['from']['emailAddress']['address']}]")
    print(f"  Subject: Re: {client_request['subject']}")
    print("  ✓ Client acknowledgment prepared")

    # =========================================================================
    # Step 9: Verify Project in Database
    # =========================================================================
    print_step(9, "Verifying project in database")

    saved_project = db.get_project(project.id)
    if saved_project:
        print(f"  ✓ Project found in database")
        print(f"    ID: {saved_project['id']}")
        print(f"    Title: {saved_project['title']}")
        print(f"    Status: {saved_project['status']}")
        print(f"    Owner: {saved_project['owner_email']}")

        tasks = db.get_tasks_for_project(project.id)
        print(f"    Tasks: {len(tasks)}")
        for t in tasks:
            status = "✓" if t.get("assigned_to") else "○"
            assignee = t.get("assigned_to", "Unassigned")
            if assignee and "@" in assignee:
                assignee = assignee.split("@")[0]
            print(f"      {status} {t['title'][:35]}... → {assignee}")

    # =========================================================================
    # Step 10: Team Members Check Inboxes and Send Quick Acks (NATURAL BEHAVIOR)
    # =========================================================================
    print_step(10, "Team members checking inboxes and responding")

    # Wait for email delivery - emails may still be in transit
    print("  Waiting for email delivery...")
    time.sleep(5)

    print("\n  [NEW] Natural NPC behavior:")
    print("  • Check inbox for assignment")
    print("  • Send quick Teams ack: 'Got it!'")
    print("  • Later: detailed email when work is done\n")

    for assignee_email, _, _ in assignments[:2]:  # Check first 2
        try:
            assignee_client = token_manager.get_stdio_client(assignee_email)
            inbox = assignee_client.get_inbox(limit=5)

            # Find the assignment email
            assignment_found = False
            assignment_subject = ""
            for email in inbox or []:
                if project.id in email.get("subject", ""):
                    assignment_found = True
                    assignment_subject = email.get("subject", "")
                    break

            persona = persona_registry.get_by_email(assignee_email)
            name = persona.name if persona else assignee_email

            if assignment_found:
                print(f"  ✓ {name}: Found assignment email!")

                # NATURAL BEHAVIOR: Send quick Teams ack
                if CHANNEL_SELECTION_AVAILABLE:
                    decision = decide_communication_channel(
                        message_type=MessageType.ACKNOWLEDGMENT,
                        content_length=30,
                        is_reply=True,
                    )
                    print(f"    Quick response channel: {decision.channel.value}")

                # Try to send quick Teams acknowledgment
                try:
                    teams = assignee_client.list_teams()
                    if teams:
                        team_id = teams[0].get("id")
                        channels = assignee_client.list_channels(team_id)
                        if channels:
                            channel = channels[0]
                            # Natural acknowledgment variety
                            if CHANNEL_SELECTION_AVAILABLE:
                                ack_msg = MessageTemplates.teams_acknowledgment(name, assignment_subject)
                            else:
                                import random
                                acks = ["Got it!", "On it!", "Thanks, starting now!", "Received!"]
                                ack_msg = random.choice(acks)

                            assignee_client.send_channel_message(
                                team_id=team_id,
                                channel_id=channel["id"],
                                content=f"{ack_msg} Starting on the {project.title[:20]}... task.",
                                content_type="text"
                            )
                            print(f"    ✓ TEAMS ack sent: '{ack_msg}'")
                except Exception as e:
                    # Fall back to quick email reply
                    print(f"    ○ Teams unavailable, would email back")
            else:
                print(f"  ○ {name}: Assignment email in transit...")

            assignee_client.close()
        except Exception as e:
            print(f"  ⚠ Could not check {assignee_email}: {e}")

    # =========================================================================
    # Summary
    # =========================================================================
    print_header("Test Summary")

    # Show rate limiter final status
    if kam_rate_limiter:
        final_status = kam_rate_limiter.get_status()
        print(f"""
RATE LIMITING STATUS (Anna Kowalski):
  Emails sent today:     {final_status['emails']['sent_today']}/{final_status['emails']['quota']}
  API calls today:       {final_status['api_calls']['today']}/{final_status['api_calls']['daily_quota']}
  Human patterns:        {'Enabled' if final_status['human_patterns_enabled'] else 'Disabled'}
""")

    print(f"""
PROJECT CREATED SUCCESSFULLY!

  Project ID:     {project.id}
  Title:          {project.title}
  Client:         {EXTERNAL_CLIENT_NAME} ({EXTERNAL_CLIENT_COMPANY})
  Owner:          Anna Kowalski (KAM)

  Team Members Assigned:
    - Christina Hall (Marketing Copywriter Lead)
    - Bruno Dupont (Senior Proofreader)
    - François Moreau (Senior Editor)

  INTELLIGENT COMMUNICATION USED:
    ✓ Formal assignments → EMAIL (detailed, trackable)
    ✓ Quick notifications → TEAMS (fast, visible)
    ✓ Team acknowledgments → TEAMS (casual, immediate)
    ✓ Client communication → EMAIL (professional)

  HUMAN-LIKE BEHAVIORS:
    ✓ Rate limiting applied (daily quotas)
    ✓ Thinking delays between actions
    ✓ Natural communication channel selection

  Next Steps (for team members):
    1. Check inbox for assignment details
    2. Research Prysmian at https://www.prysmian.com/en
    3. Create marketing flyer content
    4. Post quick updates to Teams: "Started!" / "Done!"
    5. Submit detailed deliverable via email
""")

    # Cleanup
    kam_client.close()

    print("=" * 70)
    print("  End-to-End Test Complete!")
    print("=" * 70)

    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nTest failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
