"""Phase C routes registered only for explicitly configured live Broker mode."""

from fastapi import APIRouter, Depends, Request, WebSocket

from app.console_broker.ipc import BrokerError
from app.core.csrf import check_csrf
from app.models.console import ConsoleClient
from app.schemas.console import ClientInput
from app.schemas.console_live import (
    Attach,
    Challenge,
    ClientCommit,
    ClientValidation,
    SessionCreate,
    TrustAccept,
    VerifiedPatch,
)
from app.services.common import require_role
from app.services.console import foundation as f

router = APIRouter(prefix="/api/v1/console", dependencies=[Depends(check_csrf)])
ws_router = APIRouter()


def runtime(request):
    value = request.app.state.console_runtime
    if not value or not request.app.state.settings.console_enabled:
        f.fail(404, "console_disabled")
    value.origin(request)
    return value


async def safe(awaitable):
    try:
        return await awaitable
    except BrokerError as error:
        f.fail(
            503 if error.code in ("broker_unavailable", "broker_restarted", "resource_limit") else 422,
            error.code,
        )


@router.post("/client-validations")
async def validate_client(data: ClientValidation, request: Request):
    return await safe(runtime(request).validation.validate(request, data))


@router.post("/clients", status_code=201)
async def create_client(data: ClientCommit | ClientInput, request: Request):
    rt = runtime(request)
    rt.require_ready()
    if isinstance(data, ClientInput):
        f.fail(409, "client_validation_required")
    return rt.validation.commit(request, data.validation_id)


@router.patch("/clients/{client_id}")
async def change_client(client_id: int, data: VerifiedPatch, request: Request):
    rt = runtime(request)
    login = rt.authenticate(request)
    if data.validation_id:
        return rt.validation.commit(request, data.validation_id, client_id=client_id, data=data)
    with rt.db(write=True) as db:
        actor, _ = rt.actor(db, login)
        return f.save_client_metadata(db, actor, login, client_id, data)


@router.post("/clients/{client_id}/preview")
async def preview_client(client_id: int, data: VerifiedPatch, request: Request):
    rt = runtime(request)
    login = rt.authenticate(request)
    with rt.db(write=True) as db:
        actor, _ = rt.actor(db, login)
        require_role(actor, *f.ADMIN)
        if data.validation_id:
            rt.validation.candidate(db, actor, login, data.validation_id, client_id, data)
            client = db.get(ConsoleClient, client_id)
            if data.expected_version != client.metadata_version:
                f.fail(409, "client_stale")
            return f.preview(
                db,
                actor,
                login,
                "validated-client:" + str(client_id),
                data,
                f.affected(db, client_id=client_id),
            )
        return f.client_preview(db, actor, login, client_id, data)


@router.post("/trust/challenges")
async def challenge(data: Challenge, request: Request):
    return await safe(runtime(request).validation.challenge(request, data))


@router.post("/trust/accept")
async def accept(data: TrustAccept, request: Request):
    return await safe(runtime(request).validation.accept(request, data))


@router.post("/sessions", status_code=201)
async def session(data: SessionCreate, request: Request):
    return await safe(runtime(request).issue(request, data))


@router.post("/sessions/{identity}/attach")
async def attach(identity: str, data: Attach, request: Request):
    return await safe(runtime(request).attach(request, identity, data))


@ws_router.websocket("/ws/console/v1/sessions/{identity}")
async def terminal(websocket: WebSocket, identity: str):
    rt = websocket.app.state.console_runtime
    if not rt or not websocket.app.state.settings.console_enabled:
        await websocket.close(code=1008, reason="console_disabled")
        return
    await rt.websocket(websocket, identity)
