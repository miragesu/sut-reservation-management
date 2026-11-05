"""Foundation-only metadata APIs. No terminal/SSH/ticket redemption endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from app.core.csrf import check_csrf
from app.core.dependencies import current_user, database
from app.models.console import ConsoleClient, ConsoleGrant, ConsoleMappingEvent, ConsoleSession
from app.models.domain import Lab, SUT, User
from app.schemas.console import (
    BmcInput,
    ClientInput,
    ClientPatch,
    GrantExtension,
    GrantInput,
    RevisionInput,
    UartInput,
)
from app.services.accounts import token_hash
from app.services.common import get_or_404, require_role
from app.services.console import foundation as service


def gate(request: Request):
    settings = request.app.state.settings
    if not settings.console_enabled:
        service.fail(404, "console_disabled")
    if request.url.scheme != "https" and not settings.console_allow_insecure_http:
        service.fail(403, "console_http_not_opted_in")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin != str(request.base_url).rstrip("/"):
            service.fail(403, "console_origin_invalid")
        service.normalize_origin(origin, settings)


router = APIRouter(prefix="/api/v1/console", dependencies=[Depends(gate), Depends(check_csrf)])
DB = Annotated[object, Depends(database, scope="function")]
Actor = Annotated[User, Depends(current_user)]


def login(request):
    return token_hash(request.session["login"])


@router.get("/clients")
def clients(
    db: DB,
    actor: Actor,
    include_disabled: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
):
    if include_disabled:
        require_role(actor, *service.ADMIN)
    query = select(ConsoleClient).order_by(ConsoleClient.id)
    if not include_disabled:
        query = query.where(ConsoleClient.enabled.is_(True))
    return {
        "items": [
            service.client_view(c, admin=actor.role in service.ADMIN)
            for c in db.scalars(query.offset((page - 1) * page_size).limit(page_size))
        ]
    }


@router.post("/clients", status_code=201)
def create_client(data: ClientInput, db: DB, actor: Actor):
    require_role(actor, *service.ADMIN)
    # No network implementation and no fake success, even in APP_ENV=test.
    service.fail(503, "client_validation_unavailable")


@router.post("/client-validations")
def validate_client(data: ClientInput, db: DB, actor: Actor):
    require_role(actor, *service.ADMIN)
    service.fail(503, "client_validation_unavailable")


@router.post("/clients/{client_id}/preview")
def preview_client(client_id: int, data: ClientPatch, request: Request, db: DB, actor: Actor):
    return service.client_preview(db, actor, login(request), client_id, data)


@router.patch("/clients/{client_id}")
def patch_client(client_id: int, data: ClientPatch, request: Request, db: DB, actor: Actor):
    return service.save_client_metadata(db, actor, login(request), client_id, data)


@router.get("/suts/{sut_id}/connections")
def connections(sut_id: int, request: Request, db: DB, actor: Actor):
    sut = get_or_404(db, SUT, sut_id)
    uart = service.mapping_row(db, sut_id, "uart")
    client = db.get(ConsoleClient, uart.client_id) if uart and uart.client_id else None
    return {
        "uart": {
            **service.mapping_view(uart, "uart"),
            "client": service.client_view(client, admin=actor.role in service.ADMIN) if client else None,
        },
        "bmc": service.mapping_view(service.mapping_row(db, sut_id, "bmc"), "bmc"),
        "access": service.authorization(db, actor, login(request), sut, request.app.state.settings),
        "terminal_available": bool(
            request.app.state.console_runtime and request.app.state.console_runtime.ready
        ),
        "phase": "C_broker_gateway" if request.app.state.console_runtime else "B_mock_only",
    }


@router.post("/suts/{sut_id}/uart/preview")
def uart_preview(sut_id: int, data: UartInput, request: Request, db: DB, actor: Actor):
    return service.mapping_preview(
        db, actor, login(request), sut_id, "uart", data, request.app.state.settings
    )


@router.put("/suts/{sut_id}/uart")
def uart_save(sut_id: int, data: UartInput, request: Request, db: DB, actor: Actor):
    return service.save_mapping(db, actor, login(request), sut_id, "uart", data, request.app.state.settings)


@router.post("/suts/{sut_id}/bmc/preview")
def bmc_preview(sut_id: int, data: BmcInput, request: Request, db: DB, actor: Actor):
    return service.mapping_preview(db, actor, login(request), sut_id, "bmc", data, request.app.state.settings)


@router.put("/suts/{sut_id}/bmc")
def bmc_save(sut_id: int, data: BmcInput, request: Request, db: DB, actor: Actor):
    return service.save_mapping(db, actor, login(request), sut_id, "bmc", data, request.app.state.settings)


@router.get("/suts/{sut_id}/history")
def history(
    sut_id: int, db: DB, actor: Actor, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)
):
    get_or_404(db, SUT, sut_id)
    rows = db.scalars(
        select(ConsoleMappingEvent)
        .where(ConsoleMappingEvent.sut_id == sut_id)
        .order_by(ConsoleMappingEvent.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": [
            {
                **{
                    key: getattr(row, key)
                    for key in ("id", "actor_id", "transport", "old", "new", "reason", "created_at")
                },
                "actor_display_name": db.get(User, row.actor_id).display_name if row.actor_id else "System",
            }
            for row in rows
        ]
    }


@router.post("/trust/accept")
def trust_accept(db: DB, actor: Actor):
    service.fail(503, "host_key_verification_unavailable")


@router.post("/suts/{sut_id}/grants", status_code=201)
def create_grant(sut_id: int, data: GrantInput, db: DB, actor: Actor):
    return service.create_grant(db, actor, sut_id, data)


@router.patch("/grants/{grant_id}")
def extend_grant(grant_id: int, data: GrantExtension, db: DB, actor: Actor):
    return service.extend_grant(db, actor, grant_id, data)


@router.post("/grants/{grant_id}/revoke")
def revoke_grant(grant_id: int, data: RevisionInput, db: DB, actor: Actor):
    return service.revoke_grant(db, actor, grant_id, data.expected_revision)


@router.get("/suts/{sut_id}/my-grant")
def own_grant(sut_id: int, db: DB, actor: Actor):
    get_or_404(db, SUT, sut_id)
    rows = db.scalars(
        select(ConsoleGrant)
        .where(ConsoleGrant.sut_id == sut_id, ConsoleGrant.user_id == actor.id)
        .order_by(ConsoleGrant.id.desc())
        .limit(25)
    )
    return {"items": [service.grant_view(row) for row in rows]}


@router.get("/sessions/me")
def sessions(request: Request, db: DB, actor: Actor):
    rows = list(
        db.scalars(
            select(ConsoleSession)
            .where(ConsoleSession.user_id == actor.id, ConsoleSession.state != "closed")
            .order_by(ConsoleSession.created_at)
        )
    )
    return {
        "usage": len(rows),
        "limit": 10,
        "terminal_available": bool(
            request.app.state.console_runtime and request.app.state.console_runtime.ready
        ),
        "items": [
            {
                **{
                    key: getattr(row, key)
                    for key in (
                        "id",
                        "sut_id",
                        "transport",
                        "mode",
                        "state",
                        "created_at",
                        "lease_until",
                        "connected_at",
                    )
                },
                "sut_name": db.get(SUT, row.sut_id).name,
                "lab_name": db.get(Lab, db.get(SUT, row.sut_id).lab_id).name,
            }
            for row in rows
        ],
    }


@router.get("/admin/grants")
def admin_grants(db: DB, actor: Actor, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    require_role(actor, *service.ADMIN)
    rows = db.scalars(
        select(ConsoleGrant).order_by(ConsoleGrant.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return {
        "items": [
            {
                **service.grant_view(row),
                "display_name": db.get(User, row.user_id).display_name,
                "sut_name": db.get(SUT, row.sut_id).name,
            }
            for row in rows
        ]
    }


@router.get("/admin/grant-options")
def grant_options(db: DB, actor: Actor):
    require_role(actor, *service.ADMIN)
    # Safe provisioning picker, distinct from Super Admin account/security management.
    return {
        "users": [
            {"id": u.id, "display_name": u.display_name, "team": u.team}
            for u in db.scalars(
                select(User)
                .where(User.is_active.is_(True), User.must_change_password.is_(False))
                .order_by(User.display_name)
            )
        ],
        "suts": [
            {"id": sut.id, "name": sut.name, "operational_state": sut.operational_state}
            for sut in db.scalars(
                select(SUT)
                .where(SUT.is_archived.is_(False), SUT.operational_state != "normal")
                .order_by(SUT.name)
            )
        ],
    }
