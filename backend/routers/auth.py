"""Authentication and root routes."""

from fastapi import APIRouter, HTTPException

from backend.auth import authenticate_user, create_token, create_user
from backend.config import settings
from backend.models import LoginRequest, RegisterRequest

router = APIRouter(prefix="/api")


@router.get("/auth/config")
def auth_config():
    """Public endpoint — tells the frontend whether registration is enabled."""
    return {"allow_registration": settings.allow_registration}


@router.post("/auth/register")
def register(req: RegisterRequest):
    user = create_user(req.email, req.password, req.name)
    token = create_token(user["id"])
    return {"token": token, "user": user}


@router.post("/auth/login")
def login(req: LoginRequest):
    user = authenticate_user(req.email, req.password)
    if not user:
        raise HTTPException(401, "Invalid email or password")
    token = create_token(user["id"])
    return {"token": token, "user": user}


@router.get("/")
def root():
    return {"service": "qidian-rehearsal-agent", "display_name": "奇点排练 Agent", "version": "0.1.0"}
