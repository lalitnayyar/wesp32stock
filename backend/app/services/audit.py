from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from ..core.logging import redact
from ..models import AuditLog

log = logging.getLogger("audit")


def audit(db: Session, actor: str, action: str, entity: str = "", entity_id: object = "", details: dict | None = None,
          commit: bool = True) -> None:
    safe = json.loads(redact(json.dumps(details or {}, default=str)))
    db.add(AuditLog(actor=actor, action=action, entity=entity, entity_id=str(entity_id), details=safe))
    if commit:
        db.commit()
    log.info("%s %s %s:%s", actor, action, entity, entity_id)
