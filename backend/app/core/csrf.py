import secrets

from fastapi import HTTPException, Request


def csrf_token(request):
    if "csrf" not in request.session:
        request.session["csrf"] = secrets.token_urlsafe(32)
    return request.session["csrf"]


async def check_csrf(request: Request):
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    expected = request.session.get("csrf")
    supplied = request.headers.get("x-csrf-token")
    if supplied is None and request.headers.get("content-type", "").startswith(
        ("application/x-www-form-urlencoded", "multipart/form-data")
    ):
        supplied = (await request.form()).get("csrf_token")
    if not expected or not isinstance(supplied, str) or not secrets.compare_digest(expected, supplied):
        raise HTTPException(403, "Invalid CSRF token; reload the form and retry")
