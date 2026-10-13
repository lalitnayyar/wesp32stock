"""Generate an AI insight for a portfolio. Shared by the admin API and the Telegram bot."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ...core.crypto import decrypt_secret
from ...models import AIProvider, Portfolio
from .. import analytics
from . import providers as ai

DISCLAIMER = "AI output may be wrong and is not financial advice. Figures in 'Facts' come from the backend."


class NoProvider(Exception):
    pass


def cfg_of(p: AIProvider) -> ai.AIConfig:
    return ai.AIConfig(kind=p.kind, base_url=p.base_url, model=p.model, api_key=decrypt_secret(p.api_key_enc),
                       timeout_s=p.timeout_s)


def default_provider(db: Session) -> AIProvider | None:
    return db.query(AIProvider).filter(AIProvider.is_default.is_(True), AIProvider.enabled.is_(True)).one_or_none()


def generate(db: Session, pf: Portfolio, task: str, question: str | None = None,
             provider: AIProvider | None = None, transport=None) -> dict:
    """Raises NoProvider, ai.AIError or transport errors; callers map them to their own channel."""
    p = provider or default_provider(db)
    if p is None or not p.enabled:
        raise NoProvider("No enabled AI provider configured")
    facts = ai.build_facts(analytics.portfolio_summary(db, pf), analytics.benchmarks(db))
    text = ai.insight(cfg_of(p), task, facts, question, transport=transport)
    return {"task": task, "provider": p.name, "model": p.model, "text": text, "facts": facts, "disclaimer": DISCLAIMER}
