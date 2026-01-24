"""API router for agent management."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ...orchestration import get_process_manager
from ...database import get_db
from ...agents.persona_loader import PersonaRegistry


router = APIRouter()


# Pydantic models for API
class AgentSummary(BaseModel):
    """Summary of an agent's status."""

    email: str
    name: str
    role: str
    department: str
    status: str
    last_tick_at: Optional[str] = None
    next_tick_at: Optional[str] = None
    error_count: int = 0


class AgentDetail(BaseModel):
    """Detailed agent information."""

    email: str
    name: str
    role: str
    department: str
    job_title: str
    office_location: str
    status: str
    last_tick_at: Optional[str] = None
    next_tick_at: Optional[str] = None
    error_count: int = 0
    last_error: Optional[str] = None
    writing_style: str
    communication_style: str
    timezone: str
    manager_email: Optional[str] = None


class ActivityLogEntry(BaseModel):
    """Activity log entry."""

    id: int
    action_type: str
    action_data: Optional[dict] = None
    result: str
    error_message: Optional[str] = None
    timestamp: str


class ActionResponse(BaseModel):
    """Response for agent actions."""

    success: bool
    message: str
    agent_email: str


class BulkActionResponse(BaseModel):
    """Response for bulk agent actions."""

    success: bool
    results: dict


@router.get("", response_model=List[AgentSummary])
async def list_agents(
    department: Optional[str] = Query(None, description="Filter by department"),
    status: Optional[str] = Query(None, description="Filter by status"),
    role: Optional[str] = Query(None, description="Filter by role"),
):
    """
    List all agents with their current status.

    Optional filters: department, status, role
    """
    db = get_db()
    persona_registry = PersonaRegistry()
    persona_registry.load_all()

    agents = []
    for persona in persona_registry.list_all():
        # Apply filters
        if department and persona.department.lower() != department.lower():
            continue
        if role and role.lower() not in persona.role.lower():
            continue

        # Get state from DB
        state = db.get_agent_state(persona.email)
        agent_status = state.status if state else "stopped"

        if status and agent_status != status:
            continue

        agents.append(
            AgentSummary(
                email=persona.email,
                name=persona.name,
                role=persona.role,
                department=persona.department,
                status=agent_status,
                last_tick_at=state.last_tick_at.isoformat() if state and state.last_tick_at else None,
                next_tick_at=state.next_tick_at.isoformat() if state and state.next_tick_at else None,
                error_count=state.error_count if state else 0,
            )
        )

    return agents


@router.get("/{email:path}", response_model=AgentDetail)
async def get_agent(email: str):
    """Get detailed information about a specific agent."""
    db = get_db()
    persona_registry = PersonaRegistry()
    persona_registry.load_all()

    persona = persona_registry.get_by_email(email)
    if not persona:
        raise HTTPException(status_code=404, detail=f"Agent not found: {email}")

    state = db.get_agent_state(email)

    return AgentDetail(
        email=persona.email,
        name=persona.name,
        role=persona.role,
        department=persona.department,
        job_title=persona.job_title,
        office_location=persona.office_location,
        status=state.status if state else "stopped",
        last_tick_at=state.last_tick_at.isoformat() if state and state.last_tick_at else None,
        next_tick_at=state.next_tick_at.isoformat() if state and state.next_tick_at else None,
        error_count=state.error_count if state else 0,
        last_error=state.last_error if state else None,
        writing_style=persona.writing_style,
        communication_style=persona.communication_style,
        timezone=persona.timezone,
        manager_email=persona.manager_email,
    )


@router.get("/{email:path}/activity", response_model=List[ActivityLogEntry])
async def get_agent_activity(
    email: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Get activity log for a specific agent."""
    db = get_db()

    entries = db.get_activity_log(agent_email=email, limit=limit, offset=offset)

    return [
        ActivityLogEntry(
            id=e.id,
            action_type=e.action_type,
            action_data=e.action_data,
            result=e.result,
            error_message=e.error_message,
            timestamp=e.timestamp.isoformat(),
        )
        for e in entries
    ]


@router.post("/{email:path}/start", response_model=ActionResponse)
async def start_agent(email: str):
    """Start a specific agent."""
    manager = get_process_manager()

    # Verify agent exists
    persona_registry = PersonaRegistry()
    persona_registry.load_all()
    if not persona_registry.get_by_email(email):
        raise HTTPException(status_code=404, detail=f"Agent not found: {email}")

    success = manager.start_agent(email)

    return ActionResponse(
        success=success,
        message="Agent started" if success else "Failed to start agent",
        agent_email=email,
    )


@router.post("/{email:path}/stop", response_model=ActionResponse)
async def stop_agent(email: str):
    """Stop a specific agent."""
    manager = get_process_manager()
    success = manager.stop_agent(email)

    return ActionResponse(
        success=success,
        message="Agent stopped" if success else "Failed to stop agent",
        agent_email=email,
    )


@router.post("/{email:path}/pause", response_model=ActionResponse)
async def pause_agent(email: str):
    """Pause a specific agent."""
    manager = get_process_manager()
    success = manager.pause_agent(email)

    return ActionResponse(
        success=success,
        message="Agent paused" if success else "Failed to pause agent",
        agent_email=email,
    )


@router.post("/{email:path}/resume", response_model=ActionResponse)
async def resume_agent(email: str):
    """Resume a paused agent."""
    manager = get_process_manager()
    success = manager.resume_agent(email)

    return ActionResponse(
        success=success,
        message="Agent resumed" if success else "Failed to resume agent",
        agent_email=email,
    )


@router.post("/start-all", response_model=BulkActionResponse)
async def start_all_agents():
    """Start all agents."""
    manager = get_process_manager()
    persona_registry = PersonaRegistry()
    persona_registry.load_all()

    emails = persona_registry.get_emails()
    results = manager.start_all(emails)

    success_count = sum(1 for v in results.values() if v)

    return BulkActionResponse(
        success=success_count > 0,
        results={
            "started": success_count,
            "failed": len(results) - success_count,
            "total": len(results),
            "details": results,
        },
    )


@router.post("/stop-all", response_model=BulkActionResponse)
async def stop_all_agents():
    """Stop all agents."""
    manager = get_process_manager()
    results = manager.stop_all()

    success_count = sum(1 for v in results.values() if v)

    return BulkActionResponse(
        success=True,
        results={
            "stopped": success_count,
            "failed": len(results) - success_count,
            "total": len(results),
            "details": results,
        },
    )


@router.get("/stats/summary")
async def get_stats():
    """Get summary statistics."""
    db = get_db()
    persona_registry = PersonaRegistry()
    persona_registry.load_all()

    states = db.get_all_agent_states()

    status_counts = {"running": 0, "paused": 0, "stopped": 0, "error": 0}
    for state in states:
        if state.status in status_counts:
            status_counts[state.status] += 1

    # Count agents without state as stopped
    total_personas = len(persona_registry)
    tracked_count = len(states)
    status_counts["stopped"] += total_personas - tracked_count

    return {
        "total_agents": total_personas,
        "status_counts": status_counts,
        "departments": list(
            set(p.department for p in persona_registry.list_all())
        ),
    }
