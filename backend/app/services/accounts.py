import hashlib
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException
from sqlalchemy import delete, func, select

from app.core.database import utcnow
from app.models.domain import CurrentUsage, Lab, LoginSession, QueueEntry, Reservation, SUT, User
from app.services.common import audit, get_or_404, require_role

HASHER = PasswordHasher()
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))


def verify_password(encoded, raw):
    try:
        return HASHER.verify(encoded, raw)
    except (VerificationError, InvalidHashError):
        return False


def validate_password(raw, settings):
    if len(raw) < settings.minimum_password_length or len(raw) > 128 or raw.isspace():
        raise HTTPException(422, f"Password must contain {settings.minimum_password_length}–128 characters")


def token_hash(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def public_user(user):
    return {
        key: getattr(user, key)
        for key in (
            "id",
            "username",
            "display_name",
            "team",
            "email",
            "role",
            "is_active",
            "must_change_password",
        )
    }


def profile(user):
    return {key: getattr(user, key) for key in ("id", "username", "display_name", "team", "email")}


def provision(db, actor, data, settings, *, bootstrap=False):
    if bootstrap:
        if db.scalar(select(User.id).where(User.role == "super_admin").limit(1)):
            raise HTTPException(409, "Administrator already bootstrapped; use account management")
    else:
        require_role(actor, "super_admin")
    raw = data.temporary_password.get_secret_value()
    validate_password(raw, settings)
    user = User(
        **data.model_dump(exclude={"temporary_password"}),
        password_hash=HASHER.hash(raw),
        must_change_password=True,
    )
    db.add(user)
    db.flush()
    audit(db, actor, "admin_bootstrap" if bootstrap else "user_created", user_id=user.id, role=user.role)
    return user


def login(db, data, settings):
    user = db.scalar(select(User).where(User.username == data.username.casefold()))
    good = verify_password(user.password_hash if user else DUMMY_HASH, data.password.get_secret_value())
    if not user or not good or not user.is_active:
        raise HTTPException(401, "Invalid username or password")
    if HASHER.check_needs_rehash(user.password_hash):
        user.password_hash = HASHER.hash(data.password.get_secret_value())
    raw = secrets.token_urlsafe(32)
    session = LoginSession(
        id=token_hash(raw), user_id=user.id, expires_at=utcnow() + timedelta(hours=settings.session_hours)
    )
    db.add(session)
    # Expired sessions never authorize access and are pruned on successful login.
    db.execute(delete(LoginSession).where(LoginSession.expires_at <= utcnow()))
    audit(db, user, "login")
    return user, raw


def change_password(db, actor, data, settings):
    raw = data.new_password.get_secret_value()
    if not verify_password(actor.password_hash, data.current_password.get_secret_value()):
        raise HTTPException(403, "Current password is incorrect")
    validate_password(raw, settings)
    if verify_password(actor.password_hash, raw):
        raise HTTPException(422, "Choose a different password")
    actor.password_hash = HASHER.hash(raw)
    actor.must_change_password = False
    actor.password_changed_at = utcnow()
    db.execute(delete(LoginSession).where(LoginSession.user_id == actor.id))
    audit(db, actor, "password_changed", user_id=actor.id)


def update_profile(db, actor, data):
    before = profile(actor)
    for key, value in data.model_dump().items():
        setattr(actor, key, value)
    db.flush()
    audit(db, actor, "profile_updated", user_id=actor.id, before=before, after=profile(actor))
    return profile(actor)


def reset_password(db, actor, identity, data, settings):
    require_role(actor, "super_admin")
    target = get_or_404(db, User, identity)
    raw = data.temporary_password.get_secret_value()
    validate_password(raw, settings)
    target.password_hash = HASHER.hash(raw)
    target.must_change_password = True
    db.execute(delete(LoginSession).where(LoginSession.user_id == target.id))
    audit(db, actor, "password_reset", user_id=target.id)


def protect_last_admin(db, target):
    if target.role == "super_admin" and target.is_active:
        count = db.scalar(
            select(func.count()).select_from(User).where(User.role == "super_admin", User.is_active.is_(True))
        )
        if count <= 1:
            raise HTTPException(409, "Cannot disable or demote the last active Super Admin")


def change_role(db, actor, identity, data):
    require_role(actor, "super_admin")
    target = get_or_404(db, User, identity)
    if data.role != "super_admin":
        protect_last_admin(db, target)
    old = target.role
    target.role = data.role
    audit(db, actor, "role_changed", user_id=target.id, before=old, after=target.role)
    return public_user(target)


def impact(db, identity):
    get_or_404(db, User, identity)
    result = {}
    for key, model, conditions in (
        ("usages", CurrentUsage, []),
        ("queues", QueueEntry, []),
        (
            "reservations",
            Reservation,
            [
                Reservation.status.in_(["confirmed", "waiting_for_release", "claimed"]),
                Reservation.end_time > utcnow(),
            ],
        ),
    ):
        rows = db.execute(
            select(model, SUT, Lab)
            .join(SUT, model.sut_id == SUT.id)
            .join(Lab, SUT.lab_id == Lab.id)
            .where(model.user_id == identity, *conditions)
        ).all()
        result[key] = [
            {"id": row.id, "sut_id": sut.id, "sut_name": sut.name, "lab_name": lab.name}
            for row, sut, lab in rows
        ]
    return result


def change_status(db, actor, identity, data):
    require_role(actor, "super_admin")
    target = get_or_404(db, User, identity)
    if target.is_active == data.is_active:
        return public_user(target)
    if not data.is_active:
        protect_last_admin(db, target)
        if not data.reason:
            raise HTTPException(422, "Deactivation reason is required")
        if any(impact(db, identity).values()) and not data.acknowledge_resources:
            raise HTTPException(409, "Review outstanding resources and acknowledge before deactivation")
    target.is_active = data.is_active
    target.deactivated_at = None if data.is_active else utcnow()
    target.deactivated_by_user_id = None if data.is_active else actor.id
    target.deactivation_reason = None if data.is_active else data.reason
    db.execute(delete(LoginSession).where(LoginSession.user_id == identity))
    audit(db, actor, "user_status_changed", user_id=identity, is_active=data.is_active, reason=data.reason)
    return public_user(target)
