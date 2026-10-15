from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import delete, select

from app.core.csrf import check_csrf, csrf_token
from app.core.dependencies import authenticated, current_user, database, super_admin
from app.models.domain import Lab, LoginSession, User
from app.schemas.inputs import (
    LabInput,
    LoginInput,
    OperationalInput,
    PasswordInput,
    ProfileInput,
    ResetInput,
    RoleInput,
    StatusInput,
    SUTInput,
    SUTUpdate,
    UserInput,
)
from app.schemas.outputs import (
    LabView,
    ProfileView,
    UserView,
    SUTView,
    DashboardView,
    Collection,
    LoginView,
    CSRFView,
    ImpactView,
)
from app.services import accounts, inventory

router = APIRouter(prefix="/api/v1", dependencies=[Depends(check_csrf)])
DB = Annotated[object, Depends(database, scope="function")]
Actor = Annotated[User, Depends(current_user)]
Super = Annotated[User, Depends(super_admin)]


@router.get("/auth/csrf", response_model=CSRFView)
def csrf(request: Request):
    return {"csrf_token": csrf_token(request)}


@router.post("/auth/login", response_model=LoginView)
def login(data: LoginInput, request: Request, db: DB):
    request.app.state.login_limiter.check(request)
    actor, raw = accounts.login(db, data, request.app.state.settings)
    old = request.session.get("login")
    if old:
        db.execute(delete(LoginSession).where(LoginSession.id == accounts.token_hash(old)))
    request.session.clear()
    request.session["login"] = raw
    csrf_token(request)
    return {"must_change_password": actor.must_change_password}


@router.post("/auth/logout", status_code=204)
def logout(request: Request, db: DB, actor: Annotated[User, Depends(authenticated)]):
    db.execute(delete(LoginSession).where(LoginSession.id == accounts.token_hash(request.session["login"])))
    request.session.clear()
    return Response(status_code=204)


@router.post("/auth/change-password", status_code=204)
def password(data: PasswordInput, request: Request, db: DB, actor: Annotated[User, Depends(authenticated)]):
    accounts.change_password(db, actor, data, request.app.state.settings)
    request.session.clear()
    return Response(status_code=204)


@router.get("/users/me", response_model=ProfileView)
def me(actor: Actor):
    return accounts.profile(actor)


@router.patch("/users/me", response_model=ProfileView)
def profile(data: ProfileInput, db: DB, actor: Actor):
    return accounts.update_profile(db, actor, data)


@router.get("/users", response_model=Collection[UserView])
def users(db: DB, actor: Super, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    rows = db.scalars(select(User).order_by(User.id).offset((page - 1) * page_size).limit(page_size))
    return {"items": [accounts.public_user(u) for u in rows]}


@router.post("/users", status_code=201, response_model=UserView)
def create_user(data: UserInput, request: Request, db: DB, actor: Super):
    return accounts.public_user(accounts.provision(db, actor, data, request.app.state.settings))


@router.patch("/users/{identity}", response_model=UserView)
def role(identity: int, data: RoleInput, db: DB, actor: Super):
    return accounts.change_role(db, actor, identity, data)


@router.get("/users/{identity}/impact", response_model=ImpactView)
def impact(identity: int, db: DB, actor: Super):
    return accounts.impact(db, identity)


@router.patch("/users/{identity}/status", response_model=UserView)
def status(identity: int, data: StatusInput, request: Request, db: DB, actor: Super):
    return accounts.change_status(db, actor, identity, data, now=request.app.state.clock())


@router.post("/users/{identity}/reset-password", status_code=204)
def reset(identity: int, data: ResetInput, request: Request, db: DB, actor: Super):
    accounts.reset_password(db, actor, identity, data, request.app.state.settings)
    return Response(status_code=204)


@router.get("/labs", response_model=Collection[LabView])
def labs(db: DB, actor: Actor, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    return {
        "items": [
            inventory.lab_dict(lab)
            for lab in db.scalars(
                select(Lab).order_by(Lab.name).offset((page - 1) * page_size).limit(page_size)
            )
        ]
    }


@router.post("/labs", status_code=201, response_model=LabView)
def create_lab(data: LabInput, db: DB, actor: Actor):
    return inventory.lab_save(db, actor, data)


@router.put("/labs/{identity}", response_model=LabView)
def edit_lab(identity: int, data: LabInput, db: DB, actor: Actor):
    return inventory.lab_save(db, actor, data, identity)


@router.delete("/labs/{identity}", status_code=204)
def delete_lab(identity: int, db: DB, actor: Actor):
    inventory.lab_delete(db, actor, identity)
    return Response(status_code=204)


@router.get("/suts", response_model=DashboardView)
def suts(
    db: DB,
    actor: Actor,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str = "",
    lab_id: int | None = None,
    platform: str = "",
    owner_team: str = "",
    status: str = "",
    include_archived: bool = False,
    sort: str = "name",
):
    data = inventory.snapshot(
        db,
        actor,
        include_archived=include_archived,
        search=search,
        lab_id=lab_id,
        platform=platform,
        owner_team=owner_team,
        status=status,
        sort=sort,
    )
    data["items"] = data["items"][(page - 1) * page_size : page * page_size]
    return data


@router.get("/dashboard", response_model=DashboardView)
def dashboard(
    db: DB,
    actor: Actor,
    search: str = "",
    lab_id: int | None = None,
    platform: str = "",
    owner_team: str = "",
    status: str = "",
    sort: str = "name",
):
    return inventory.snapshot(
        db,
        actor,
        search=search,
        lab_id=lab_id,
        platform=platform,
        owner_team=owner_team,
        status=status,
        sort=sort,
    )


@router.post("/suts", status_code=201, response_model=SUTView)
def create_sut(data: SUTInput, db: DB, actor: Actor):
    identity = inventory.sut_save(db, actor, data)
    return inventory.detail(db, actor, identity)


@router.get("/suts/{identity}", response_model=SUTView)
def sut(identity: int, db: DB, actor: Actor):
    return inventory.detail(db, actor, identity)


@router.put("/suts/{identity}", response_model=SUTView)
def edit_sut(identity: int, data: SUTUpdate, db: DB, actor: Actor):
    inventory.sut_save(db, actor, data, identity)
    return inventory.detail(db, actor, identity)


@router.delete("/suts/{identity}", status_code=204)
def archive(identity: int, db: DB, actor: Actor):
    inventory.archive(db, actor, identity)
    return Response(status_code=204)


@router.post("/suts/{identity}/restore", status_code=204)
def restore(identity: int, db: DB, actor: Actor):
    inventory.archive(db, actor, identity, restore=True)
    return Response(status_code=204)


@router.patch("/suts/{identity}/operational-state", response_model=SUTView)
def operational(identity: int, data: OperationalInput, request: Request, db: DB, actor: Actor):
    inventory.operational(db, actor, identity, data, now=request.app.state.clock())
    return inventory.detail(db, actor, identity)
