"""
backend/api/v1/router.py
=========================
Aggregates all v1 routers into one prefix=/api/v1 router.
"""
from fastapi import APIRouter

from api.v1.auth          import router as auth_router
from api.v1.simulation    import router as sim_router
from api.v1.prediction    import router as pred_router
from api.v1.optimization  import router as opt_router
from api.v1.explainability import router as expl_router

v1_router = APIRouter(prefix="/api/v1")

v1_router.include_router(auth_router)
v1_router.include_router(sim_router)
v1_router.include_router(pred_router)
v1_router.include_router(opt_router)
v1_router.include_router(expl_router)
