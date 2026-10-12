"""Admin authentication (JWT in HttpOnly cookie + CSRF double-submit, server-side revocation) and
device authentication (scoped, hashed API keys). The two are deliberately separate."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from ..models import AdminSession, ApiAccessLog, ApiKey, User
from .config import get_settings
from .crypto import hmac_digest
from .db import get_db
from .ratelimit import limiter

SESSION_COOKIE = "ls_session"
CSRF_COOKIE = "ls_csrf"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

DEVICE_SCOPES = {
    "device:dashboard": "Read the device dashboard",
    "device:heartbeat": "Report device health",
}


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


# ----------------------------------------------------------------------------- admin sessions

def create_session(db: Session, user: User, request: Request, response: Response) -> str:
    s = get_settings()
    jti = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    exp = now + timedelta(hours=s.session_hours)
    db.add(AdminSession(jti=jti, user_id=user.id, expires_at=exp, ip=client_ip(request),
                        user_agent=(request.headers.get("user-agent") or "")[:255]))
    user.last_login_at = now
    db.commit()
    token = jwt.encode({"sub": str(user.id), "jti": jti, "iat": now, "exp": exp}, s.app_secret_key, algorithm="HS256")
    csrf = secrets.token_urlsafe(24)
    max_age = s.session_hours * 3600
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=s.cookie_secure, samesite="strict",
                        max_age=max_age, path="/")
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, secure=s.cookie_secure, samesite="strict",
                        max_age=max_age, path="/")
    return csrf


def revoke_session(db: Session, request: Request, response: Response) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        try:
            claims = jwt.decode(token, get_settings().app_secret_key, algorithms=["HS256"])
            sess = db.query(AdminSession).filter(AdminSession.jti == claims.get("jti")).one_or_none()
            if sess and not sess.revoked_at:
                sess.revoked_at = datetime.now(timezone.utc)
                db.commit()
        except jwt.PyJWTError:
            pass
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def current_admin(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        claims = jwt.decode(token, get_settings().app_secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session invalid or expired")
    sess = db.query(AdminSession).filter(AdminSession.jti == claims.get("jti")).one_or_none()
    if sess is None or sess.revoked_at is not None or sess.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session revoked or expired")
    user = db.get(User, sess.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User disabled")
    if request.method not in SAFE_METHODS:
        header = request.headers.get(CSRF_HEADER)
        cookie = request.cookies.get(CSRF_COOKIE)
        if not header or not cookie or not secrets.compare_digest(header, cookie):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF token missing or invalid")
    return user


# ----------------------------------------------------------------------------- device API keys

KEY_PREFIX = "lsk_"


def generate_api_key() -> tuple[str, str, str]:
    """Return (full_key, prefix, hash). Only the hash and prefix are stored."""
    prefix = secrets.token_hex(4)  # 8 hex chars, used for lookup only
    secret = secrets.token_urlsafe(32)
    full = f"{KEY_PREFIX}{prefix}_{secret}"
    return full, prefix, hmac_digest(full)


def _parse_key(raw: str) -> str | None:
    if not raw.startswith(KEY_PREFIX):
        return None
    parts = raw[len(KEY_PREFIX):].split("_", 1)
    if len(parts) != 2 or len(parts[0]) != 8:
        return None
    return parts[0]


def _log_access(db: Session, key_id: int | None, request: Request, code: int) -> None:
    db.add(ApiAccessLog(api_key_id=key_id, method=request.method, path=request.url.path[:200], status=code,
                        ip=client_ip(request)))
    db.commit()


def require_device_key(scope: str):
    def dep(request: Request, db: Session = Depends(get_db)) -> ApiKey:
        from ..services import settings_store

        auth = request.headers.get("authorization", "")
        raw = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        ip = client_ip(request)
        if not limiter.allow(f"devip:{ip}", 120):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded")
        prefix = _parse_key(raw) if raw else None
        key = db.query(ApiKey).filter(ApiKey.prefix == prefix).one_or_none() if prefix else None
        if key is None or not secrets.compare_digest(key.key_hash, hmac_digest(raw)):
            _log_access(db, None, request, 401)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key",
                                headers={"WWW-Authenticate": "Bearer"})
        now = datetime.now(timezone.utc)
        if key.revoked_at is not None:
            _log_access(db, key.id, request, 401)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API key revoked")
        if key.expires_at is not None and key.expires_at < now:
            _log_access(db, key.id, request, 401)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API key expired")
        if scope not in (key.scopes or []):
            _log_access(db, key.id, request, 403)
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"API key lacks scope {scope}")
        per_min = settings_store.get(db, "device_rate_limit_per_min")
        if not limiter.allow(f"key:{key.id}", per_min):
            _log_access(db, key.id, request, 429)
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded")
        key.last_used_at = now
        key.last_used_ip = ip
        _log_access(db, key.id, request, 200)
        return key

    return dep
