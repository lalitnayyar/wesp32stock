from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.crypto import decrypt_secret, encrypt_secret, mask_secret
from ..core.db import get_db
from ..core.security import current_admin
from ..models import AIProvider, Portfolio, User
from ..services.ai import providers as ai
from ..services.ai import run as ai_run
from ..services.audit import audit
from .common import get_or_404

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


class ProviderIn(BaseModel):
    kind: str = Field(pattern="^(openai|deepseek|ollama)$")
    name: str = Field(min_length=1, max_length=100)
    base_url: str | None = Field(None, max_length=255)
    model: str = Field(min_length=1, max_length=100)
    api_key: str | None = Field(None, max_length=500, description="Write-only; never returned")
    enabled: bool = True
    is_default: bool = False
    timeout_s: int = Field(60, ge=5, le=300)


class ProviderUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    base_url: str | None = Field(None, max_length=255)
    model: str | None = Field(None, min_length=1, max_length=100)
    api_key: str | None = Field(None, max_length=500)
    clear_api_key: bool = False
    enabled: bool | None = None
    is_default: bool | None = None
    timeout_s: int | None = Field(None, ge=5, le=300)


def p_out(p: AIProvider) -> dict:
    return {"id": p.id, "kind": p.kind, "name": p.name, "base_url": p.base_url, "model": p.model,
            "api_key_masked": mask_secret(decrypt_secret(p.api_key_enc)), "has_api_key": bool(p.api_key_enc),
            "enabled": p.enabled, "is_default": p.is_default, "timeout_s": p.timeout_s,
            "last_test_at": p.last_test_at, "last_test_ok": p.last_test_ok,
            "last_test_latency_ms": p.last_test_latency_ms, "last_test_message": p.last_test_message}


cfg_of = ai_run.cfg_of


def _set_default(db: Session, p: AIProvider) -> None:
    db.query(AIProvider).filter(AIProvider.id != p.id).update({AIProvider.is_default: False})
    p.is_default = True


@router.get("/providers")
def list_providers(db: Session = Depends(get_db), _: User = Depends(current_admin)):
    return {"providers": [p_out(p) for p in db.query(AIProvider).order_by(AIProvider.id).all()],
            "defaults": ai.DEFAULT_URLS, "tasks": ai.TASKS}


@router.post("/providers", status_code=201)
def create_provider(body: ProviderIn, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    p = AIProvider(kind=body.kind, name=body.name, base_url=(body.base_url or ai.DEFAULT_URLS[body.kind]).rstrip("/"),
                   model=body.model, api_key_enc=encrypt_secret(body.api_key) if body.api_key else None,
                   enabled=body.enabled, timeout_s=body.timeout_s)
    db.add(p)
    db.flush()
    if body.is_default or db.query(AIProvider).count() == 1:
        _set_default(db, p)
    db.commit()
    audit(db, user.username, "ai_provider_created", "ai_provider", p.id,
          {"kind": p.kind, "name": p.name, "model": p.model, "api_key_set": bool(body.api_key)})
    return p_out(p)


@router.put("/providers/{pid}")
def update_provider(pid: int, body: ProviderUpdate, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    p = get_or_404(db, AIProvider, pid, "AI provider")
    for k in ("name", "model", "enabled", "timeout_s"):
        v = getattr(body, k)
        if v is not None:
            setattr(p, k, v)
    if body.base_url:
        p.base_url = body.base_url.rstrip("/")
    if body.clear_api_key:
        p.api_key_enc = None
    elif body.api_key:
        p.api_key_enc = encrypt_secret(body.api_key)
    if body.is_default:
        _set_default(db, p)
    db.commit()
    audit(db, user.username, "ai_provider_updated", "ai_provider", pid,
          {**body.model_dump(exclude={"api_key"}, exclude_none=True), "api_key_changed": bool(body.api_key)})
    return p_out(p)


@router.delete("/providers/{pid}")
def delete_provider(pid: int, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    p = get_or_404(db, AIProvider, pid, "AI provider")
    db.delete(p)
    db.commit()
    audit(db, user.username, "ai_provider_deleted", "ai_provider", pid)
    return {"ok": True}


@router.post("/providers/{pid}/test")
def test_provider(pid: int, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    p = get_or_404(db, AIProvider, pid, "AI provider")
    res = ai.test_connection(cfg_of(p))
    p.last_test_at = datetime.now(timezone.utc)
    p.last_test_ok = res["ok"]
    p.last_test_latency_ms = res["latency_ms"]
    p.last_test_message = res["message"][:500]
    db.commit()
    audit(db, user.username, "ai_provider_tested", "ai_provider", pid, {"ok": res["ok"]})
    return res


class InsightIn(BaseModel):
    portfolio_id: int
    task: str
    question: str | None = Field(None, max_length=1000)
    provider_id: int | None = None


@router.post("/insights")
def insights(body: InsightIn, db: Session = Depends(get_db), user: User = Depends(current_admin)):
    pf = get_or_404(db, Portfolio, body.portfolio_id, "Portfolio")
    p = get_or_404(db, AIProvider, body.provider_id, "AI provider") if body.provider_id else None
    try:
        out = ai_run.generate(db, pf, body.task, body.question, provider=p)
    except ai_run.NoProvider as exc:
        raise HTTPException(409, str(exc))
    except ai.AIError as exc:
        raise HTTPException(502, f"AI provider error: {exc}")
    except Exception as exc:
        raise HTTPException(502, f"AI provider unreachable: {type(exc).__name__}")
    audit(db, user.username, "ai_insight", "portfolio", pf.id, {"task": body.task, "provider": out["provider"]})
    return out
