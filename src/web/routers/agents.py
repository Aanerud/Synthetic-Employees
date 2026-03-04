"""API router for agent management."""

import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ...database.db_service import get_db
from ...agents.persona_loader import PersonaRegistry
from ...scheduler.cultural_schedules import get_cultural_schedule, COUNTRY_NAME_TO_CODE


router = APIRouter()

# Cached data (loaded once per request cycle)
_csv_countries: Optional[Dict[str, str]] = None


def _get_csv_countries() -> Dict[str, str]:
    global _csv_countries
    if _csv_countries is None:
        _csv_countries = {}
        csv_path = Path("textcraft-europe.csv")
        if csv_path.exists():
            with open(csv_path, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    email = row.get("email", "").lower()
                    country = row.get("country", "")
                    if email and country:
                        _csv_countries[email] = country
    return _csv_countries


def _get_country_for(email: str) -> str:
    return _get_csv_countries().get(email.lower(), "United Kingdom")


def _get_local_time(email: str) -> str:
    country = _get_country_for(email)
    code = COUNTRY_NAME_TO_CODE.get(country, "GB")
    sched = get_cultural_schedule(usage_location=code)
    try:
        return datetime.now(ZoneInfo(sched.timezone)).strftime("%H:%M")
    except Exception:
        return "??:??"


def _get_flag(country: str) -> str:
    flags = {
        "Italy": "🇮🇹", "Sweden": "🇸🇪", "France": "🇫🇷", "Germany": "🇩🇪",
        "Spain": "🇪🇸", "Poland": "🇵🇱", "Netherlands": "🇳🇱", "Belgium": "🇧🇪",
        "Portugal": "🇵🇹", "Austria": "🇦🇹", "Denmark": "🇩🇰", "Ireland": "🇮🇪",
        "Switzerland": "🇨🇭", "United Kingdom": "🇬🇧",
    }
    return flags.get(country, "🏳️")


class AgentSummary(BaseModel):
    email: str
    name: str
    role: str
    department: str
    status: str
    country: str = ""
    flag: str = ""
    local_time: str = ""
    last_tick_at: Optional[str] = None
    error_count: int = 0
    last_error: Optional[str] = None


class AgentDetail(AgentSummary):
    job_title: str = ""
    office_location: str = ""
    writing_style: str = ""
    communication_style: str = ""
    timezone: str = ""
    manager_email: Optional[str] = None


class ActivityLogEntry(BaseModel):
    id: int
    action_type: str
    action_data: Optional[dict] = None
    result: str
    error_message: Optional[str] = None
    timestamp: str


# ── ROUTES (order matters: specific routes BEFORE catch-all) ──


@router.get("/stats/summary")
async def get_stats():
    db = get_db()
    reg = PersonaRegistry()
    reg.load_all()
    states = db.get_all_agent_states()

    status_counts = {"running": 0, "stopped": 0, "error": 0}
    for s in states:
        if s.status == "error":
            status_counts["error"] += 1
        elif s.status == "running":
            status_counts["running"] += 1

    status_counts["stopped"] += len(reg) - len(states)

    # Country breakdown
    countries = {}
    for p in reg.list_all():
        c = _get_country_for(p.email)
        countries[c] = countries.get(c, 0) + 1

    return {
        "total_agents": len(reg),
        "status_counts": status_counts,
        "countries": countries,
        "departments": sorted(set(p.department for p in reg.list_all())),
    }


@router.get("/feed")
async def get_activity_feed(limit: int = Query(30, ge=1, le=100)):
    """Recent activity across ALL agents for the live feed."""
    db = get_db()
    reg = PersonaRegistry()
    reg.load_all()

    entries = db.get_activity_log(limit=limit)
    name_map = {p.email: p.name for p in reg.list_all()}

    feed = []
    for e in entries:
        name = name_map.get(e.agent_email, e.agent_email.split("@")[0])
        # Build human-readable description
        desc = e.action_type
        if e.action_data:
            actions = e.action_data.get("actions_taken", [])
            if actions:
                types = [a.get("type", "") for a in actions]
                email_count = sum(1 for t in types if t in ("send_email", "reply_email"))
                if email_count:
                    desc = f"Sent {email_count} email{'s' if email_count > 1 else ''}"
                elif "no_action" in types:
                    desc = "Checked inbox (no action needed)"
                else:
                    desc = ", ".join(t.replace("_", " ") for t in types[:3])

        feed.append({
            "id": e.id,
            "name": name,
            "email": e.agent_email,
            "action": desc,
            "result": e.result,
            "error": e.error_message,
            "timestamp": e.timestamp.isoformat(),
        })

    return feed


@router.get("/by-email/{email}/activity", response_model=List[ActivityLogEntry])
async def get_agent_activity(
    email: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
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


@router.get("/by-email/{email}", response_model=AgentDetail)
async def get_agent(email: str):
    db = get_db()
    reg = PersonaRegistry()
    reg.load_all()

    persona = reg.get_by_email(email)
    if not persona:
        raise HTTPException(status_code=404, detail=f"Agent not found: {email}")

    state = db.get_agent_state(email)
    country = _get_country_for(email)

    return AgentDetail(
        email=persona.email,
        name=persona.name,
        role=persona.role,
        department=persona.department,
        job_title=persona.job_title,
        office_location=persona.office_location,
        status=state.status if state else "stopped",
        country=country,
        flag=_get_flag(country),
        local_time=_get_local_time(email),
        last_tick_at=state.last_tick_at.isoformat() if state and state.last_tick_at else None,
        error_count=state.error_count if state else 0,
        last_error=state.last_error if state else None,
        writing_style=persona.writing_style,
        communication_style=persona.communication_style,
        timezone=persona.timezone,
        manager_email=persona.manager_email,
    )


# ── CATCH-ALL list route (must be LAST) ──


@router.get("", response_model=List[AgentSummary])
async def list_agents(
    department: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    db = get_db()
    reg = PersonaRegistry()
    reg.load_all()

    agents = []
    for persona in sorted(reg.list_all(), key=lambda p: p.name):
        state = db.get_agent_state(persona.email)
        agent_status = state.status if state else "stopped"

        if department and persona.department.lower() != department.lower():
            continue
        if status and agent_status != status:
            continue

        country = _get_country_for(persona.email)

        agents.append(AgentSummary(
            email=persona.email,
            name=persona.name,
            role=persona.role,
            department=persona.department,
            status=agent_status,
            country=country,
            flag=_get_flag(country),
            local_time=_get_local_time(persona.email),
            last_tick_at=state.last_tick_at.isoformat() if state and state.last_tick_at else None,
            error_count=state.error_count if state else 0,
            last_error=state.last_error if state else None,
        ))

    return agents
