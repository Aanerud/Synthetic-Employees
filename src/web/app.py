"""FastAPI web dashboard for Shadow Employees."""

import asyncio
import csv
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional, Set

import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from ..database.db_service import get_db
from ..agents.persona_loader import PersonaRegistry
from ..scheduler.employee_scheduler import EmployeeScheduler
from ..scheduler.cultural_schedules import COUNTRY_NAME_TO_CODE
from ..main import AgencyOrchestrator, load_config
from .routers import agents


class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict):
        dead = set()
        for conn in self.active_connections:
            try:
                await conn.send_json(message)
            except Exception:
                dead.add(conn)
        for conn in dead:
            self.active_connections.discard(conn)


ws_manager = ConnectionManager()

# Global orchestrator (lives across requests)
_orchestrator: Optional[AgencyOrchestrator] = None
_orchestrator_task: Optional[asyncio.Task] = None


def _load_csv_countries() -> dict:
    csv_path = Path("textcraft-europe.csv")
    if not csv_path.exists():
        return {}
    mapping = {}
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            email = row.get("email", "").lower()
            country = row.get("country", "")
            if email and country:
                mapping[email] = country
    return mapping


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting Shadow Employees Dashboard...")

    persona_registry = PersonaRegistry()
    count = persona_registry.load_all()
    print(f"Loaded {count} personas")

    scheduler = EmployeeScheduler()
    csv_countries = _load_csv_countries()
    for persona in persona_registry:
        country = csv_countries.get(persona.email.lower(), "United Kingdom")
        tz_override = persona.timezone
        if tz_override == "Europe/London" and country != "United Kingdom":
            tz_override = None
        scheduler.register_employee(
            email=persona.email,
            country=country,
            role=persona.role or persona.job_title,
            check_frequency_minutes=persona.email_check_frequency_minutes,
            timezone_override=tz_override,
        )

    db = get_db()

    app.state.persona_registry = persona_registry
    app.state.scheduler = scheduler
    app.state.csv_countries = csv_countries
    app.state.db = db

    broadcast_task = asyncio.create_task(status_broadcast_loop(app))

    yield

    # Shutdown
    global _orchestrator, _orchestrator_task
    if _orchestrator:
        _orchestrator.running = False
    if _orchestrator_task:
        _orchestrator_task.cancel()
        try:
            await _orchestrator_task
        except (asyncio.CancelledError, Exception):
            pass

    broadcast_task.cancel()
    try:
        await broadcast_task
    except asyncio.CancelledError:
        pass
    print("Dashboard stopped")


async def status_broadcast_loop(app: FastAPI):
    while True:
        try:
            await asyncio.sleep(3)
            if ws_manager.active_connections:
                scheduler = app.state.scheduler
                db = app.state.db
                active_emails = set(scheduler.get_active_employees())

                # Get orchestrator status
                orch_status = None
                if _orchestrator:
                    orch_status = _orchestrator.get_status()

                agents_status = []
                for persona in app.state.persona_registry:
                    state = db.get_agent_state(persona.email)
                    is_active = persona.email in active_emails
                    is_authed = _orchestrator and persona.email in _orchestrator.authed_employees

                    if not is_active:
                        status = "off_hours"
                    elif is_authed:
                        status = state.status if state else "idle"
                    else:
                        status = "pending_auth"

                    agents_status.append({
                        "email": persona.email,
                        "status": status,
                        "last_tick": state.last_tick_at.isoformat() if state and state.last_tick_at else None,
                        "error_count": state.error_count if state else 0,
                        "active": is_active,
                        "authed": is_authed,
                    })

                await ws_manager.broadcast({
                    "type": "status_update",
                    "timestamp": datetime.now().isoformat(),
                    "active_count": len(active_emails),
                    "total_count": scheduler.employee_count,
                    "orchestrator": orch_status,
                    "agents": agents_status,
                })
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Broadcast error: {e}")


app = FastAPI(
    title="Shadow Employees Dashboard",
    version="2.0.0",
    lifespan=lifespan,
)

templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

app.include_router(agents.router, prefix="/api/agents", tags=["agents"])


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": {}, "title": "Shadow Employees"},
    )


@app.post("/api/company/start")
async def start_company():
    """Start the company - begin progressive auth and ticking."""
    global _orchestrator, _orchestrator_task

    if _orchestrator and _orchestrator.running:
        return JSONResponse({"status": "already_running", "message": "Company is already running"})

    config = load_config()
    _orchestrator = AgencyOrchestrator(config)
    _orchestrator.initialize()

    async def _run():
        try:
            await _orchestrator.start()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Orchestrator error: {e}")

    _orchestrator_task = asyncio.create_task(_run())

    return JSONResponse({
        "status": "started",
        "message": f"Starting company with {_orchestrator.onboarding_total} employees (first batch of 12 now, rest every 15 min)",
    })


@app.post("/api/company/stop")
async def stop_company():
    """Stop the company."""
    global _orchestrator, _orchestrator_task

    if not _orchestrator or not _orchestrator.running:
        return JSONResponse({"status": "not_running", "message": "Company is not running"})

    _orchestrator.running = False

    return JSONResponse({"status": "stopping", "message": "Company is stopping..."})


@app.get("/api/company/status")
async def company_status():
    """Get company status."""
    if not _orchestrator:
        return {"running": False, "authed": 0, "total": 0}
    return _orchestrator.get_status()


@app.get("/api/company/kams")
async def get_kams():
    """Get Key Account Manager emails for sending work."""
    persona_registry = PersonaRegistry()
    persona_registry.load_all()

    kams = []
    for p in persona_registry.list_all():
        if "account" in (p.role or "").lower() or "account" in (p.job_title or "").lower():
            country_map = _load_csv_countries()
            country = country_map.get(p.email.lower(), "Unknown")
            kams.append({
                "name": p.name,
                "email": p.email,
                "role": p.job_title,
                "country": country,
            })

    return kams


@app.websocket("/ws/status")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"type": "ack"})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "company_running": _orchestrator.running if _orchestrator else False,
    }
