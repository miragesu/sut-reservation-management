from starlette.concurrency import run_in_threadpool
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy import delete, select
from app.core.csrf import check_csrf, csrf_token
from app.core.dependencies import admin, authenticated, current_user, database, super_admin
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
from app.services import accounts, inventory, coordination_queries

router = APIRouter(dependencies=[Depends(check_csrf)], include_in_schema=False)
DB = Annotated[object, Depends(database, scope="function")]
Actor = Annotated[User, Depends(current_user)]
Admin = Annotated[User, Depends(admin)]
Super = Annotated[User, Depends(super_admin)]


def render(request, name, user=None, **context):
    return request.app.state.templates.TemplateResponse(
        request=request,
        name=name,
        context={
            "user": user,
            "csrf_token": csrf_token(request),
            "password_minimum": request.app.state.settings.password_minimum,
            **context,
        },
    )


async def payload(request, schema):
    form = dict(await request.form())
    form.pop("csrf_token", None)
    try:
        return schema.model_validate(form)
    except ValidationError as exc:
        raise HTTPException(
            422,
            "Invalid input: "
            + "; ".join((".".join((str(x) for x in e["loc"])) + ": " + e["msg"] for e in exc.errors())),
        ) from None


def redirect(path):
    return RedirectResponse(path, status_code=303)


@router.get("/login")
def login_form(request: Request):
    return render(request, "login.html")


@router.post("/login")
async def login(request: Request, db: DB):
    request.app.state.login_limiter.check(request)
    data = await payload(request, LoginInput)
    actor, raw = await run_in_threadpool(accounts.login, db, data, request.app.state.settings)
    old = request.session.get("login")
    if old:
        db.execute(
            delete(LoginSession).where(LoginSession.id == await run_in_threadpool(accounts.token_hash, old))
        )
    request.session.clear()
    request.session["login"] = raw
    csrf_token(request)
    return redirect("/change-password" if actor.must_change_password else "/")


@router.post("/logout")
def logout(request: Request, db: DB, actor: Annotated[User, Depends(authenticated)]):
    db.execute(delete(LoginSession).where(LoginSession.id == accounts.token_hash(request.session["login"])))
    request.session.clear()
    return redirect("/login")


@router.get("/change-password")
def password_form(request: Request, actor: Annotated[User, Depends(authenticated)]):
    return render(request, "password.html", actor)


@router.post("/change-password")
async def password(request: Request, db: DB, actor: Annotated[User, Depends(authenticated)]):
    await run_in_threadpool(
        accounts.change_password, db, actor, await payload(request, PasswordInput), request.app.state.settings
    )
    request.session.clear()
    return redirect("/login")


@router.get("/profile")
def profile_form(request: Request, actor: Actor):
    return render(request, "profile.html", actor)


@router.post("/profile")
async def profile(request: Request, db: DB, actor: Actor):
    await run_in_threadpool(accounts.update_profile, db, actor, await payload(request, ProfileInput))
    return redirect("/profile")


@router.get("/")
def dashboard(request: Request, db: DB, actor: Actor):
    data = inventory.snapshot(db, actor)
    labs = [inventory.lab_dict(lab) for lab in db.scalars(select(Lab).order_by(Lab.name))]
    return render(request, "dashboard.html", actor, data=data, labs=labs)


@router.get("/labs")
def labs(request: Request, db: DB, actor: Actor):
    return render(request, "labs.html", actor, labs=db.scalars(select(Lab).order_by(Lab.name)).all())


@router.post("/labs")
async def create_lab(request: Request, db: DB, actor: Admin):
    await run_in_threadpool(inventory.lab_save, db, actor, await payload(request, LabInput))
    return redirect("/labs")


@router.post("/labs/{identity}/edit")
async def edit_lab(identity: int, request: Request, db: DB, actor: Admin):
    await run_in_threadpool(inventory.lab_save, db, actor, await payload(request, LabInput), identity)
    return redirect("/labs")


@router.post("/labs/{identity}/delete")
def delete_lab(identity: int, db: DB, actor: Admin):
    inventory.lab_delete(db, actor, identity)
    return redirect("/labs")


@router.get("/suts")
def suts(
    request: Request,
    db: DB,
    actor: Actor,
    include_archived: bool = False,
    page: int = 1,
    search: str = "",
    lab_id: str = "",
    platform: str = "",
    owner_team: str = "",
    status: str = "",
    sort: str = "name",
):
    if page < 1:
        raise HTTPException(422, "Page must be positive")
    try:
        selected_lab = int(lab_id) if lab_id else None
        if selected_lab is not None and selected_lab < 1:
            raise ValueError
    except ValueError:
        raise HTTPException(422, "Lab must be a positive ID") from None
    data = inventory.snapshot(
        db,
        actor,
        include_archived=include_archived,
        search=search,
        lab_id=selected_lab,
        platform=platform,
        owner_team=owner_team,
        status=status,
        sort=sort,
    )
    data["items"] = data["items"][(page - 1) * 25 : page * 25]
    return render(
        request,
        "suts.html",
        actor,
        data=data,
        page=page,
        include_archived=include_archived,
        labs=db.scalars(select(Lab).order_by(Lab.name)).all(),
    )


@router.get("/suts/new")
def sut_form(request: Request, db: DB, actor: Admin):
    return render(
        request, "sut_form.html", actor, sut=None, labs=db.scalars(select(Lab).order_by(Lab.name)).all()
    )


@router.post("/suts")
async def create_sut(request: Request, db: DB, actor: Admin):
    identity = await run_in_threadpool(inventory.sut_save, db, actor, await payload(request, SUTInput))
    return redirect(f"/suts/{identity}")


@router.get("/suts/{identity}")
def sut(identity: int, request: Request, db: DB, actor: Actor):
    return render(
        request,
        "sut_detail.html",
        actor,
        sut=inventory.detail(db, actor, identity),
        coordination=coordination_queries.coordination_view(db, identity, request.app.state.clock()),
    )


@router.get("/suts/{identity}/edit")
def edit_sut_form(identity: int, request: Request, db: DB, actor: Admin):
    return render(request, "sut_form.html", actor, sut=inventory.detail(db, actor, identity), labs=[])


@router.post("/suts/{identity}/edit")
async def edit_sut(identity: int, request: Request, db: DB, actor: Admin):
    await run_in_threadpool(inventory.sut_save, db, actor, await payload(request, SUTUpdate), identity)
    return redirect(f"/suts/{identity}")


@router.post("/suts/{identity}/archive")
def archive(identity: int, db: DB, actor: Admin):
    inventory.archive(db, actor, identity)
    return redirect("/suts")


@router.post("/suts/{identity}/restore")
def restore(identity: int, db: DB, actor: Admin):
    inventory.archive(db, actor, identity, restore=True)
    return redirect(f"/suts/{identity}")


@router.post("/suts/{identity}/operational-state")
async def operational(identity: int, request: Request, db: DB, actor: Admin):
    await run_in_threadpool(
        inventory.operational,
        db,
        actor,
        identity,
        await payload(request, OperationalInput),
        now=request.app.state.clock(),
    )
    return redirect(f"/suts/{identity}")


@router.get("/admin")
def administration(request: Request, actor: Admin):
    return render(request, "admin.html", actor)


@router.get("/admin/users")
def users(request: Request, db: DB, actor: Super):
    users = db.scalars(select(User).order_by(User.username)).all()
    attention = [{"user": u, "impact": accounts.impact(db, u.id)} for u in users if not u.is_active]
    return render(request, "users.html", actor, users=users, attention=attention)


@router.post("/admin/users")
async def create_user(request: Request, db: DB, actor: Super):
    await run_in_threadpool(
        accounts.provision, db, actor, await payload(request, UserInput), request.app.state.settings
    )
    return redirect("/admin/users")


@router.get("/admin/users/{identity}")
def user_detail(identity: int, request: Request, db: DB, actor: Super):
    target = accounts.get_or_404(db, User, identity)
    return render(request, "user_detail.html", actor, target=target, impact=accounts.impact(db, identity))


@router.post("/admin/users/{identity}/role")
async def role(identity: int, request: Request, db: DB, actor: Super):
    await run_in_threadpool(accounts.change_role, db, actor, identity, await payload(request, RoleInput))
    return redirect(f"/admin/users/{identity}")


@router.post("/admin/users/{identity}/status")
async def status(identity: int, request: Request, db: DB, actor: Super):
    await run_in_threadpool(
        accounts.change_status,
        db,
        actor,
        identity,
        await payload(request, StatusInput),
        now=request.app.state.clock(),
    )
    return redirect(f"/admin/users/{identity}")


@router.post("/admin/users/{identity}/reset-password")
async def reset(identity: int, request: Request, db: DB, actor: Super):
    await run_in_threadpool(
        accounts.reset_password,
        db,
        actor,
        identity,
        await payload(request, ResetInput),
        request.app.state.settings,
    )
    return redirect(f"/admin/users/{identity}")


@router.get("/openapi.json")
def schema(request: Request, actor: Actor):
    return get_openapi(title=request.app.title, version="0.1.0", routes=request.app.routes)


@router.get("/dashboard/fragment")
def fragment(
    request: Request,
    db: DB,
    actor: Actor,
    search: str = "",
    lab_id: int | None = None,
    platform: str = "",
    owner_team: str = "",
    status: str = "",
    sort: str = "name",
):
    data = inventory.snapshot(
        db,
        actor,
        search=search,
        lab_id=lab_id,
        platform=platform,
        owner_team=owner_team,
        status=status,
        sort=sort,
    )
    return render(request, "dashboard_content.html", actor, data=data)
