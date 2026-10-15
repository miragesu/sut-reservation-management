from fastapi import HTTPException

from app.models.domain import AuditEvent


def get_or_404(db, model, identity):
    obj = db.get(model, identity)
    if obj is None:
        raise HTTPException(404, f"{model.__name__} not found")
    return obj


def require_role(actor, *roles):
    if actor.role not in roles:
        raise HTTPException(403, "Permission denied")


def audit(db, actor, event, *, sut_id=None, **details):
    db.add(
        AuditEvent(
            actor_user_id=actor.id if actor else None, sut_id=sut_id, event_type=event, details_json=details
        )
    )
