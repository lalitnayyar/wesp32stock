"""Persistent, observable scheduling. Intervals live in app_settings; state is exposed via /market/status."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from ..core.db import SessionLocal
from . import settings_store
from .market import service as market

log = logging.getLogger(__name__)

_sched: BackgroundScheduler | None = None
JOB_STATE: dict[str, dict] = {}


def _run(name: str, fn) -> None:
    st = JOB_STATE.setdefault(name, {})
    st["last_started_at"] = datetime.now(timezone.utc).isoformat()
    db = SessionLocal()
    try:
        result = fn(db)
        st["last_ok_at"] = datetime.now(timezone.utc).isoformat()
        st["last_error"] = None
        if hasattr(result, "ok"):
            st["last_result"] = {"ok": result.ok, "failed": result.failed, "skipped": result.skipped}
    except Exception as exc:  # keep the scheduler alive
        log.exception("job %s failed", name)
        st["last_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    finally:
        db.close()


def quotes_job() -> None:
    _run("quotes", market.poll_once)


def history_job() -> None:
    def fn(db):
        if settings_store.get(db, "history_enabled"):
            return market.refresh_history(db)
    _run("history", fn)


def start() -> None:
    global _sched
    if _sched is not None:
        return
    db = SessionLocal()
    try:
        interval = settings_store.get(db, "quote_refresh_s")
    finally:
        db.close()
    _sched = BackgroundScheduler(timezone="UTC", job_defaults={"coalesce": True, "max_instances": 1,
                                                               "misfire_grace_time": 30})
    _sched.add_job(quotes_job, "interval", seconds=interval, id="quotes", next_run_time=datetime.now(timezone.utc))
    _sched.add_job(history_job, "cron", hour=22, minute=30, id="history")
    _sched.add_job(history_job, "date", run_date=datetime.now(timezone.utc), id="history_boot")
    _sched.start()
    log.info("scheduler started; quote refresh every %ss", interval)


def reschedule_quotes(interval_s: int) -> None:
    if _sched is not None:
        _sched.reschedule_job("quotes", trigger="interval", seconds=interval_s)
        log.info("quote refresh rescheduled to %ss", interval_s)


def status() -> dict:
    jobs = {}
    if _sched is not None:
        for job in _sched.get_jobs():
            jobs[job.id] = {"next_run_at": job.next_run_time.isoformat() if job.next_run_time else None,
                            "trigger": str(job.trigger), **JOB_STATE.get(job.id, {})}
    return {"running": _sched is not None and _sched.running, "jobs": jobs}


def shutdown() -> None:
    global _sched
    if _sched is not None:
        _sched.shutdown(wait=False)
        _sched = None
