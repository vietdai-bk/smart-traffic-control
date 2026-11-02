from fastapi import APIRouter

from app.api.routes import (
    alerts,
    audit,
    auth,
    cameras,
    evaluation,
    intersections,
    llm,
    signals,
    simulation,
    stats,
    system,
    users,
)

api_router = APIRouter(prefix="/api")
for module in (auth, users, intersections, cameras, signals, alerts, stats, evaluation, audit, simulation, system, llm):
    api_router.include_router(module.router)
