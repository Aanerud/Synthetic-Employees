"""Agent Loop - continuous behavior loop for synthetic employees."""

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..agents.persona_loader import LoadedPersona, PersonaRegistry, build_system_prompt
from ..auth.mcp_token_manager import MCPTokenManager
from ..database.db_service import DatabaseService

# Import MCP clients - prefer stdio (1:1 with Claude Desktop), fallback to HTTP
try:
    from ..mcp_client.stdio_client import MCPStdioClient
    STDIO_AVAILABLE = True
except ImportError:
    STDIO_AVAILABLE = False

from ..mcp_client.client import MCPClient

# Import LLM service (optional - falls back to simple responses if unavailable)
try:
    from ..llm.claude_service import ClaudeService
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

# Import pulse system
try:
    from .pulse_executor import PulseExecutor
    PULSE_AVAILABLE = True
except ImportError:
    PULSE_AVAILABLE = False

# Import KAM workflow
try:
    from .kam_workflow import KeyAccountManagerWorkflow
    KAM_AVAILABLE = True
except ImportError:
    KAM_AVAILABLE = False

# Import rate limiting
try:
    from .rate_limiter import (
        AgentRateLimiter,
        RateLimitedMCPClient,
        RateLimitExceededError,
        RateLimitReason,
    )
    from .human_patterns import AvailabilityStatus
    RATE_LIMITING_AVAILABLE = True
except ImportError:
    RATE_LIMITING_AVAILABLE = False
    # Define a placeholder exception so code doesn't break
    class RateLimitExceededError(Exception):
        """Placeholder when rate limiting is unavailable."""
        pass

logger = logging.getLogger(__name__)

# Use stdio transport by default (same as Claude Desktop)
USE_STDIO_TRANSPORT = os.getenv("USE_STDIO_TRANSPORT", "true").lower() == "true"

# Enable rate limiting and human behavior patterns by default
ENABLE_RATE_LIMITING = os.getenv("ENABLE_RATE_LIMITING", "true").lower() == "true"
ENABLE_HUMAN_PATTERNS = os.getenv("ENABLE_HUMAN_PATTERNS", "true").lower() == "true"


def tick_agent(
    email: str,
    token_manager: MCPTokenManager,
    persona_registry: PersonaRegistry,
    db: DatabaseService,
    enable_rate_limiting: Optional[bool] = None,
    enable_human_patterns: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Execute a single tick for an agent.

    A tick includes:
    1. Check if agent is available (not on break, within work hours)
    2. Check inbox for unread emails
    3. Process and respond to emails if needed
    4. Check calendar for meeting invites
    5. Respond to pending meeting invites
    6. Execute proactive tasks if scheduled

    Args:
        email: Agent email address
        token_manager: MCP token manager for authentication
        persona_registry: Registry of loaded personas
        db: Database service for persistence
        enable_rate_limiting: Override global ENABLE_RATE_LIMITING setting
        enable_human_patterns: Override global ENABLE_HUMAN_PATTERNS setting

    Returns:
        Dict with tick results
    """
    # Determine rate limiting settings
    use_rate_limiting = (
        enable_rate_limiting if enable_rate_limiting is not None
        else ENABLE_RATE_LIMITING
    ) and RATE_LIMITING_AVAILABLE

    use_human_patterns = (
        enable_human_patterns if enable_human_patterns is not None
        else ENABLE_HUMAN_PATTERNS
    ) and RATE_LIMITING_AVAILABLE

    results = {
        "email": email,
        "tick_time": datetime.now().isoformat(),
        "actions": [],
        "errors": [],
        "rate_limited": False,
        "rate_limit_reason": None,
    }

    # Get persona
    persona = persona_registry.get_by_email(email)
    if not persona:
        results["errors"].append(f"Persona not found for {email}")
        db.log_activity(
            email, "tick", result="error", error_message="Persona not found"
        )
        return results

    # Initialize rate limiter if enabled
    rate_limiter = None
    if use_rate_limiting:
        rate_limiter = AgentRateLimiter(
            agent_email=email,
            role=persona.role,
            enable_human_patterns=use_human_patterns,
        )

        # Check if agent is available (not on break, within work hours)
        if use_human_patterns and rate_limiter.behavior:
            availability = rate_limiter.behavior.check_availability()
            if not availability.available:
                results["rate_limited"] = True
                results["rate_limit_reason"] = availability.status.value
                results["actions"].append({
                    "action": "availability_check",
                    "available": False,
                    "status": availability.status.value,
                    "reason": availability.reason,
                    "resume_at": availability.resume_at.isoformat() if availability.resume_at else None,
                })
                logger.info(
                    f"Agent {email} unavailable: {availability.reason}"
                )
                db.log_activity(
                    email,
                    "tick_skipped",
                    action_data={"reason": availability.reason, "status": availability.status.value},
                    result="skipped",
                )
                return results

    # Create MCP client (prefer stdio transport - same as Claude Desktop)
    mcp_client = None
    raw_client = None  # Keep reference for cleanup
    try:
        if USE_STDIO_TRANSPORT and STDIO_AVAILABLE:
            # Use stdio transport (spawns mcp-adapter.cjs subprocess)
            raw_client = token_manager.get_stdio_client(email)
            logger.debug(f"Using stdio MCP client for {email}")
        else:
            # Fall back to HTTP transport
            mcp_token = token_manager.get_mcp_token(email)
            raw_client = MCPClient(mcp_token.access_token)
            logger.debug(f"Using HTTP MCP client for {email}")

        # Wrap with rate limiter if enabled
        if use_rate_limiting and rate_limiter:
            mcp_client = RateLimitedMCPClient(raw_client, rate_limiter)
            logger.debug(f"Rate limiting enabled for {email}")
        else:
            mcp_client = raw_client

    except Exception as e:
        results["errors"].append(f"Failed to create MCP client: {e}")
        db.log_activity(
            email, "tick", result="error", error_message=f"MCP client error: {e}"
        )
        return results

    # 1. Check inbox (with KAM workflow for Key Account Managers)
    try:
        inbox_result = check_inbox(
            email, persona, mcp_client, db, persona_registry
        )
        results["actions"].append(inbox_result)
    except RateLimitExceededError as e:
        results["rate_limited"] = True
        results["rate_limit_reason"] = e.result.reason.value if e.result else "unknown"
        results["errors"].append(f"Rate limited during inbox check: {e}")
        logger.warning(f"Rate limit hit for {email} during inbox check: {e}")
    except Exception as e:
        results["errors"].append(f"Inbox check failed: {e}")

    # 2. Check calendar (skip if already rate limited)
    if not results["rate_limited"]:
        try:
            calendar_result = check_calendar(email, persona, mcp_client, db)
            results["actions"].append(calendar_result)
        except RateLimitExceededError as e:
            results["rate_limited"] = True
            results["rate_limit_reason"] = e.result.reason.value if e.result else "unknown"
            results["errors"].append(f"Rate limited during calendar check: {e}")
            logger.warning(f"Rate limit hit for {email} during calendar check: {e}")
        except Exception as e:
            results["errors"].append(f"Calendar check failed: {e}")

    # 3. Execute pulse-based proactive tasks (skip if rate limited)
    if PULSE_AVAILABLE and not results["rate_limited"]:
        try:
            llm_service = ClaudeService() if LLM_AVAILABLE else None
            pulse_executor = PulseExecutor(persona, mcp_client, db, llm_service)
            pulse_results = pulse_executor.execute_due_pulses()
            if pulse_results:
                results["actions"].append({
                    "action": "pulse_execution",
                    "pulses_executed": len(pulse_results),
                    "results": pulse_results,
                })
        except RateLimitExceededError as e:
            results["rate_limited"] = True
            results["rate_limit_reason"] = e.result.reason.value if e.result else "unknown"
            results["errors"].append(f"Rate limited during pulse execution: {e}")
            logger.warning(f"Rate limit hit for {email} during pulse execution: {e}")
        except Exception as e:
            results["errors"].append(f"Pulse execution failed: {e}")
            logger.error(f"Pulse execution failed for {email}: {e}")

    # Add rate limiter status to results
    if rate_limiter:
        results["rate_limiter_status"] = rate_limiter.get_status()

    # Cleanup stdio client if used (terminates subprocess)
    if USE_STDIO_TRANSPORT and STDIO_AVAILABLE and raw_client:
        try:
            raw_client.close()
        except Exception:
            pass  # Ignore cleanup errors

    # Log the tick
    db.log_activity(
        email,
        "tick",
        action_data=results,
        result="success" if not results["errors"] else "error",
    )

    return results


def check_inbox(
    email: str,
    persona: LoadedPersona,
    mcp_client: MCPClient,
    db: DatabaseService,
    persona_registry: Optional[PersonaRegistry] = None,
) -> Dict[str, Any]:
    """
    Check inbox for unread emails and process them.

    Args:
        email: Agent email
        persona: Agent persona
        mcp_client: MCP client for API calls
        db: Database service
        persona_registry: Optional registry for KAM workflow delegation

    Returns:
        Dict with inbox check results
    """
    result = {
        "action": "check_inbox",
        "unread_count": 0,
        "processed": 0,
        "responded": 0,
        "projects_created": 0,
    }

    # Get unread emails
    try:
        inbox = mcp_client.get_inbox(limit=20, filter_query="isRead eq false")
    except Exception as e:
        result["error"] = str(e)
        return result

    if not inbox or not isinstance(inbox, list):
        return result

    result["unread_count"] = len(inbox)

    # Check if this is a Key Account Manager (use KAM workflow for external emails)
    is_kam = "account manager" in persona.role.lower() or "kam" in persona.role.lower()
    kam_workflow = None

    if is_kam and KAM_AVAILABLE and persona_registry:
        try:
            llm_service = ClaudeService() if LLM_AVAILABLE else None
            kam_workflow = KeyAccountManagerWorkflow(
                persona=persona,
                mcp_client=mcp_client,
                db=db,
                persona_registry=persona_registry,
                llm_service=llm_service,
            )
        except Exception as e:
            logger.warning(f"Could not initialize KAM workflow: {e}")

    # Process each unread email
    for email_data in inbox:
        try:
            # Use KAM workflow for external client emails
            if kam_workflow and kam_workflow.is_external_email(email_data):
                kam_result = kam_workflow.process_external_email(email_data)
                if kam_result.get("project_created"):
                    result["projects_created"] += 1
                    result["processed"] += 1
                    # Mark as read after processing
                    try:
                        mcp_client.mark_as_read(email_data["id"])
                    except Exception:
                        pass
                    continue

            # Standard email processing
            processed = process_email(email, persona, email_data, mcp_client, db)
            result["processed"] += 1
            if processed.get("responded"):
                result["responded"] += 1
        except Exception as e:
            db.log_activity(
                email,
                "email_error",
                action_data={"message_id": email_data.get("id")},
                result="error",
                error_message=str(e),
            )

    db.increment_metric(email, "emails_received", result["unread_count"])
    if result["responded"] > 0:
        db.increment_metric(email, "emails_responded", result["responded"])

    return result


def process_email(
    agent_email: str,
    persona: LoadedPersona,
    email_data: Dict[str, Any],
    mcp_client: MCPClient,
    db: DatabaseService,
) -> Dict[str, Any]:
    """
    Process a single email and decide whether/how to respond.

    Args:
        agent_email: Agent email
        persona: Agent persona
        email_data: Email data from inbox
        mcp_client: MCP client
        db: Database service

    Returns:
        Dict with processing result
    """
    result = {"message_id": email_data.get("id"), "responded": False}

    sender = email_data.get("from", {})
    sender_email = sender.get("emailAddress", {}).get("address", "")
    subject = email_data.get("subject", "(No subject)")

    # Skip certain types of emails
    if should_skip_email(sender_email, subject):
        result["skipped"] = True
        result["reason"] = "System/notification email"
        # Mark as read
        try:
            mcp_client.mark_as_read(email_data["id"])
        except Exception:
            pass
        return result

    # Decide if we should respond
    should_respond = should_respond_to_email(persona, email_data)
    if not should_respond:
        result["skipped"] = True
        result["reason"] = "No response needed"
        return result

    # Generate response (simplified - in production would use LLM)
    response_body = generate_simple_response(persona, email_data)

    # Send reply
    try:
        mcp_client.reply_to_mail(email_data["id"], response_body)
        result["responded"] = True
        db.increment_metric(agent_email, "emails_sent")
    except Exception as e:
        result["error"] = str(e)

    # Log activity
    db.log_activity(
        agent_email,
        "email_response",
        action_data={
            "message_id": email_data["id"],
            "sender": sender_email,
            "subject": subject,
        },
        result="success" if result["responded"] else "error",
    )

    return result


def should_skip_email(sender_email: str, subject: str) -> bool:
    """Check if email should be skipped (system emails, notifications, etc.)."""
    skip_senders = [
        "noreply@",
        "no-reply@",
        "notifications@",
        "mailer-daemon@",
        "postmaster@",
    ]
    skip_subjects = [
        "out of office",
        "automatic reply",
        "undeliverable:",
        "delivery status",
    ]

    sender_lower = sender_email.lower()
    subject_lower = subject.lower()

    for skip in skip_senders:
        if skip in sender_lower:
            return True

    for skip in skip_subjects:
        if skip in subject_lower:
            return True

    return False


def should_respond_to_email(persona: LoadedPersona, email_data: Dict[str, Any]) -> bool:
    """
    Determine if agent should respond to this email.

    Simple heuristic based on:
    - Is it addressed to the agent directly (not CC)
    - Is it a question or request
    - Is it from a relevant sender
    """
    # Check if directly addressed
    to_recipients = email_data.get("toRecipients", [])
    is_direct = any(
        r.get("emailAddress", {}).get("address", "").lower() == persona.email.lower()
        for r in to_recipients
    )

    if not is_direct:
        return False

    # Check subject/body for question indicators
    subject = email_data.get("subject", "").lower()
    body_preview = email_data.get("bodyPreview", "").lower()

    question_indicators = ["?", "could you", "can you", "would you", "please", "help"]
    has_question = any(q in subject or q in body_preview for q in question_indicators)

    return has_question


def generate_simple_response(persona: LoadedPersona, email_data: Dict[str, Any]) -> str:
    """
    Generate a response to an email using Claude LLM.

    Falls back to a basic template if LLM is unavailable.
    """
    # Try to use Claude for intelligent responses
    if LLM_AVAILABLE:
        try:
            service = ClaudeService()
            response = service.generate_email_response(persona, email_data)
            if response:
                logger.info(f"Generated LLM response for {persona.email}")
                return response
        except Exception as e:
            logger.warning(f"LLM response failed, falling back to template: {e}")

    # Fallback to simple template
    sender = email_data.get("from", {})
    # Handle both normalized and raw MS Graph formats
    if "emailAddress" in sender:
        sender_name = sender.get("emailAddress", {}).get("name", "")
        if not sender_name:
            sender_name = sender.get("emailAddress", {}).get("address", "").split("@")[0]
    else:
        sender_name = sender.get("name", sender.get("email", "").split("@")[0])

    response = f"""Hi {sender_name},

Thank you for your email. I've received your message and will review it shortly.

Best regards,
{persona.name}
{persona.job_title}"""

    return response


def check_calendar(
    email: str,
    persona: LoadedPersona,
    mcp_client: MCPClient,
    db: DatabaseService,
) -> Dict[str, Any]:
    """
    Check calendar for pending meeting invites.

    Args:
        email: Agent email
        persona: Agent persona
        mcp_client: MCP client
        db: Database service

    Returns:
        Dict with calendar check results
    """
    result = {
        "action": "check_calendar",
        "pending_invites": 0,
        "accepted": 0,
        "declined": 0,
    }

    # Get today's events
    try:
        events = mcp_client.get_events(timeframe="today")
    except Exception as e:
        result["error"] = str(e)
        return result

    if not events or not isinstance(events, list):
        return result

    # Process events (look for pending invites)
    for event in events:
        response_status = event.get("responseStatus", {}).get("response", "")

        if response_status == "notResponded":
            result["pending_invites"] += 1

            # Decide whether to accept
            should_accept = should_accept_meeting(persona, event)

            if should_accept:
                try:
                    mcp_client.respond_to_event(event["id"], "accept")
                    result["accepted"] += 1
                    db.increment_metric(email, "meetings_attended")
                except Exception:
                    pass
            else:
                try:
                    mcp_client.respond_to_event(event["id"], "decline")
                    result["declined"] += 1
                    db.increment_metric(email, "meetings_declined")
                except Exception:
                    pass

    return result


def should_accept_meeting(persona: LoadedPersona, event: Dict[str, Any]) -> bool:
    """
    Determine if agent should accept a meeting invite.

    Based on:
    - Meeting is during work hours
    - Organizer is in auto-accept list
    - No conflicts
    """
    organizer = event.get("organizer", {}).get("emailAddress", {}).get("address", "")
    role_def = persona.get_role_definition()

    # Auto-accept from manager
    if persona.manager_email and organizer.lower() == persona.manager_email.lower():
        return True

    # Check role's meeting preferences
    meeting_prefs = role_def.meeting_preferences
    for auto_accept_role in meeting_prefs.auto_accept_from:
        if auto_accept_role.lower() in organizer.lower():
            return True

    # Default: accept most meetings during work hours
    # (A real implementation would check for conflicts)
    return True


def run_proactive_tasks(
    email: str,
    persona: LoadedPersona,
    mcp_client: MCPClient,
    db: DatabaseService,
) -> List[Dict[str, Any]]:
    """
    Run any proactive tasks for the agent.

    Proactive tasks are defined in the role definition and include
    things like sending daily standups, weekly reports, etc.
    """
    results = []
    role_def = persona.get_role_definition()

    for task in role_def.proactive_tasks:
        # Check if task should run (based on schedule, last run, etc.)
        # This is simplified - a real implementation would have scheduling logic
        pass

    return results
