"""Console HTML entry points; GET never probes SSH or mutates lifecycle metadata."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.core.dependencies import current_user, database
from app.models.domain import Lab, SUT
from app.routers.api.console import gate
from app.routers.web.routes import render
from app.services.accounts import token_hash
from app.services.common import get_or_404, require_role
from app.services.console import foundation as f

router = APIRouter(dependencies=[Depends(gate)], include_in_schema=False)


@router.get("/suts/{identity}/console")
def terminal(identity: int, request: Request, db=Depends(database), actor=Depends(current_user)):
    sut = get_or_404(db, SUT, identity)
    access = f.authorization(db, actor, token_hash(request.session["login"]), sut, request.app.state.settings)
    if access["mode"] == "deny":
        f.fail(403, "console_access_denied")
    return render(request, "console_terminal.html", actor, sut=sut, lab_name=db.get(Lab, sut.lab_id).name)


@router.get("/suts/{identity}/connections")
def settings(identity: int, request: Request, db=Depends(database), actor=Depends(current_user)):
    sut = get_or_404(db, SUT, identity)
    return render(request, "console_settings.html", actor, sut=sut, lab_name=db.get(Lab, sut.lab_id).name)


@router.get("/console/sessions")
def sessions(request: Request, actor=Depends(current_user)):
    return render(request, "console_sessions.html", actor)


@router.get("/admin/console-clients")
def clients(request: Request, db=Depends(database), actor=Depends(current_user)):
    require_role(actor, *f.ADMIN)
    return render(
        request, "console_clients.html", actor, labs=db.scalars(select(Lab).order_by(Lab.name)).all()
    )


@router.get("/admin/console-grants")
def grants(request: Request, actor=Depends(current_user)):
    require_role(actor, *f.ADMIN)
    return render(request, "console_grants.html", actor)
