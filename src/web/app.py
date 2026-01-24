"""FastAPI web application for agent orchestration dashboard."""

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..orchestration import get_process_manager, cleanup_process_manager
from ..database import get_db
from ..agents.persona_loader import PersonaRegistry
from .routers import agents


# WebSocket connection manager
class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.add(connection)
        # Clean up disconnected
        for conn in disconnected:
            self.active_connections.discard(conn)


ws_manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    print("Starting Synthetic Employees Dashboard...")

    # Load personas
    persona_registry = PersonaRegistry()
    persona_count = persona_registry.load_all()
    print(f"Loaded {persona_count} personas")

    # Initialize database
    db = get_db()
    print("Database initialized")

    # Store in app state
    app.state.persona_registry = persona_registry
    app.state.db = db

    # Start status broadcast task
    broadcast_task = asyncio.create_task(status_broadcast_loop())

    yield

    # Shutdown
    print("Shutting down...")
    broadcast_task.cancel()
    try:
        await broadcast_task
    except asyncio.CancelledError:
        pass
    cleanup_process_manager()
    print("Shutdown complete")


async def status_broadcast_loop():
    """Periodically broadcast status updates via WebSocket."""
    while True:
        try:
            await asyncio.sleep(5)  # Update every 5 seconds
            if ws_manager.active_connections:
                manager = get_process_manager()
                states = manager.get_all_status()
                status_data = {
                    "type": "status_update",
                    "timestamp": datetime.now().isoformat(),
                    "agents": [
                        {
                            "email": s.email,
                            "status": s.status,
                            "last_tick": s.last_tick_at.isoformat() if s.last_tick_at else None,
                            "error_count": s.error_count,
                        }
                        for s in states
                    ],
                }
                await ws_manager.broadcast(status_data)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Broadcast error: {e}")


# Create FastAPI app
app = FastAPI(
    title="Synthetic Employees Dashboard",
    description="Agent orchestration platform for synthetic employees",
    version="1.0.0",
    lifespan=lifespan,
)

# Templates
templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# Include routers
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the main dashboard."""
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": {}, "title": "Synthetic Employees Dashboard"},
    )


@app.websocket("/ws/status")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time status updates."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Wait for client messages (ping/pong, commands)
            data = await websocket.receive_text()
            # Echo acknowledgment
            await websocket.send_json({"type": "ack", "received": data})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


def create_app() -> FastAPI:
    """Factory function to create the FastAPI app."""
    return app


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("WEB_HOST", "0.0.0.0")
    port = int(os.getenv("WEB_PORT", "8000"))

    uvicorn.run(app, host=host, port=port)
