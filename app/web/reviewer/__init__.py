"""Reviewer console — GET/POST /reviewer/{sign-in,sign-out,queue,claims}.

A separate package to keep console lanes file-disjoint as they grow:
- auth.py: cookie session, sign-in, sign-out
- queue.py: queue listing, submit/approve/reject actions
- sources.py (stub)
- claims_forms.py (stub)
- published.py (stub)
- due.py (stub)
"""

from __future__ import annotations

from fastapi import APIRouter

from .auth import COOKIE_NAME
from .auth import router as auth_router
from .queue import router as queue_router

# Combine all reviewer routers into a single router registered in app/main.py
router = APIRouter()
router.include_router(auth_router)
router.include_router(queue_router)

__all__ = ["router", "COOKIE_NAME"]
