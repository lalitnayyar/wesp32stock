from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.crypto import hash_password, verify_password
from ..core.db import get_db
from ..core.ratelimit import limiter
from ..core.security import client_ip, create_session, current_admin, revoke_session
from ..models import AdminSession, User
from ..services.audit import audit
from ..services.seed import MIN_ADMIN_PASSWORD

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class PasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=MIN_ADMIN_PASSWORD, max_length=256)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = client_ip(request)
    if not limiter.allow(f"login:{ip}", 10):
        raise HTTPException(429, "Too many login attempts; try again in a minute")
    user = db.query(User).filter(User.username == body.username).one_or_none()
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        audit(db, body.username[:64], "login_failed", "user", "", {"ip": ip})
        raise HTTPException(401, "Invalid username or password")
    csrf = create_session(db, user, request, response)
    audit(db, user.username, "login", "user", user.id, {"ip": ip})
    return {"username": user.username, "csrf_token": csrf}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    revoke_session(db, request, response)
    audit(db, user.username, "logout", "user", user.id)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_admin)):
    return {"username": user.username, "last_login_at": user.last_login_at}


@router.post("/password")
def change_password(body: PasswordIn, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    now = datetime.now(timezone.utc)
    db.query(AdminSession).filter(AdminSession.user_id == user.id, AdminSession.revoked_at.is_(None)).update(
        {AdminSession.revoked_at: now})
    db.commit()
    audit(db, user.username, "password_changed", "user", user.id)
    return {"ok": True, "message": "Password changed; all sessions revoked. Please log in again."}


@router.get("/sessions")
def sessions(db: Session = Depends(get_db), user: User = Depends(current_admin)):
    rows = (db.query(AdminSession).filter(AdminSession.user_id == user.id)
            .order_by(AdminSession.created_at.desc()).limit(20).all())
    return [{"id": s.id, "created_at": s.created_at, "expires_at": s.expires_at, "revoked_at": s.revoked_at,
             "ip": s.ip, "user_agent": s.user_agent} for s in rows]


@router.post("/sessions/{session_id}/revoke")
def revoke(session_id: int, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    s = db.get(AdminSession, session_id)
    if s is None or s.user_id != user.id:
        raise HTTPException(404, "Session not found")
    s.revoked_at = s.revoked_at or datetime.now(timezone.utc)
    db.commit()
    audit(db, user.username, "session_revoked", "session", session_id)
    return {"ok": True}
