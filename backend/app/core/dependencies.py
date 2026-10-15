from fastapi import Depends, HTTPException, Request

from app.core.database import unit_of_work, utcnow
from app.models.domain import LoginSession, User
from app.services.accounts import token_hash
from app.services.common import require_role


def database(request: Request):
    with unit_of_work(request.app.state.engine, write=request.method not in ("GET", "HEAD", "OPTIONS")) as db:
        yield db


def authenticated(request: Request, db=Depends(database, scope="function")):
    raw = request.session.get("login")
    login = db.get(LoginSession, token_hash(raw)) if raw else None
    user = db.get(User, login.user_id) if login and login.expires_at > utcnow() else None
    if user is None or not user.is_active:
        raise HTTPException(401, "Please sign in")
    return user


def current_user(user=Depends(authenticated)):
    if user.must_change_password:
        raise HTTPException(403, "password_change_required")
    return user


def admin(user=Depends(current_user)):
    require_role(user, "lab_admin", "super_admin")
    return user


def super_admin(user=Depends(current_user)):
    require_role(user, "super_admin")
    return user
