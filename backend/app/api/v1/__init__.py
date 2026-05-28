"""Aggregated router for all v1 endpoints."""

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    ai,
    analyses,
    auth,
    dictionaries,
    health,
    me,
    profile,
    recovery,
    telegram,
    tickets,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(recovery.router)
api_router.include_router(profile.router)
api_router.include_router(dictionaries.router)
api_router.include_router(analyses.router)
api_router.include_router(analyses.dict_router)
api_router.include_router(ai.router)
api_router.include_router(telegram.router)
api_router.include_router(tickets.router)
api_router.include_router(me.router)
