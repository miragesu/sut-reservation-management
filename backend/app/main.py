import logging
import secrets
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.exceptions import HTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import Settings
from app.core.csrf import csrf_token
from app.core.database import make_engine
from app.core.rate_limit import LoginLimiter

ROOT = Path(__file__).parent
logger = logging.getLogger("sut.requests")


def create_app(settings=None):
    settings = settings or Settings()
    app = FastAPI(title="SUT Reservation Management — Day 1", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url)
    app.state.login_limiter = LoginLimiter()
    app.state.templates = Jinja2Templates(directory=str(ROOT / "templates"))
    app.state.templates.env.filters["taipei"] = lambda value: (
        value.astimezone(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M") if value else "—"
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key.get_secret_value(),
        session_cookie="sut_session",
        max_age=settings.session_hours * 3600,
        same_site="lax",
        https_only=settings.cookie_secure,
    )
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

    @app.middleware("http")
    async def headers(request, call_next):
        request_id = secrets.token_hex(12)
        response = await call_next(request)
        response.headers.update(
            {
                "X-Request-ID": request_id,
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "same-origin",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'; form-action 'self'; base-uri 'self'",
            }
        )
        if not request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        logger.info("request=%s method=%s status=%s", request_id, request.method, response.status_code)
        return response

    def error(request, status, detail, headers=None):
        if request.url.path.startswith("/api/") or request.url.path == "/health":
            return JSONResponse({"detail": detail}, status_code=status, headers=headers)
        if status == 401:
            return RedirectResponse("/login", status_code=303)
        if detail == "password_change_required":
            return RedirectResponse("/change-password", status_code=303)
        return app.state.templates.TemplateResponse(
            request=request,
            name="error.html",
            context={"message": detail, "status": status, "user": None, "csrf_token": csrf_token(request)},
            status_code=status,
            headers=headers,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error(request, exc.status_code, exc.detail, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        # Never echo raw input (passwords may be present in validation errors).
        return error(
            request,
            422,
            "Invalid input: "
            + "; ".join(".".join(str(x) for x in e["loc"]) + ": " + e["msg"] for e in exc.errors()),
        )

    @app.exception_handler(IntegrityError)
    async def integrity(request, exc):
        return error(
            request,
            409,
            "Duplicate name/email/username or a referenced record prevents this operation. SUT names must be unique within their Lab, including archives.",
        )

    @app.exception_handler(OperationalError)
    async def operational(request, exc):
        if "locked" in str(exc.orig).lower():
            return error(request, 503, "Database busy; retry shortly", {"Retry-After": "1"})
        logger.error("Database operation failed; request database configuration review")
        return error(request, 503, "Database unavailable")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    from app.routers.api.routes import router as api
    from app.routers.web.routes import router as web

    app.include_router(api)
    app.include_router(web)
    return app
