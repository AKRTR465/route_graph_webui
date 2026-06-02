from __future__ import annotations

from .graphs import router as graphs_router
from .health import router as health_router
from .jobs import router as jobs_router
from .missions import router as missions_router
from .plans import router as plans_router
from .ui_state import router as ui_state_router

__all__ = [
    "graphs_router",
    "health_router",
    "jobs_router",
    "missions_router",
    "plans_router",
    "ui_state_router",
]
