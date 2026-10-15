import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import unit_of_work
from app.models.domain import AuditEvent, LoginSession, User
from app.services.accounts import verify_password
from conftest import NEW_PASSWORD, PASSWORD, csrf, identity, mutate, sign_in


def test_public_boundaries_and_csrf(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/login").status_code == 200
    for path in [
        "/api/v1/labs",
        "/api/v1/suts",
        "/api/v1/dashboard",
        "/api/v1/users/me",
        "/openapi.json",
        "/dashboard/fragment",
    ]:
        assert client.get(path, follow_redirects=False).status_code in (401, 303)
    assert client.get("/", follow_redirects=False).headers["location"] == "/login"
    assert (
        client.post("/api/v1/auth/login", json={"username": "root", "password": PASSWORD}).status_code == 403
    )
    assert client.get("/register").status_code == 404
    assert client.post("/api/v1/register").status_code == 404


def test_login_rotation_logout_and_cookie(client, application):
    sign_in(client)
    first = client.cookies.get("sut_session")
    with unit_of_work(application.state.engine) as db:
        login = db.scalar(select(LoginSession))
        assert len(login.id) == 64 and PASSWORD not in login.id
    sign_in(client)
    assert client.cookies.get("sut_session") != first
    assert mutate(client, "POST", "/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/labs").status_code == 401
    client.cookies.set("sut_session", first)
    assert client.get("/api/v1/labs").status_code == 401
    client.cookies.clear()
    response = client.get("/api/v1/auth/csrf")
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert response.headers["cache-control"] == "no-store"


def test_forced_password_gate_web_and_api(client):
    sign_in(client, "temp")
    assert client.get("/api/v1/labs").status_code == 403
    assert client.get("/profile", follow_redirects=False).headers["location"] == "/change-password"
    assert client.get("/", follow_redirects=False).headers["location"] == "/change-password"
    assert client.get("/change-password").status_code == 200
    assert (
        mutate(
            client,
            "PATCH",
            "/api/v1/users/me",
            {"display_name": "new", "team": "Demo", "email": "other@example.com"},
        ).status_code
        == 403
    )
    assert (
        mutate(
            client,
            "POST",
            "/api/v1/auth/change-password",
            {"current_password": "wrong", "new_password": NEW_PASSWORD},
        ).status_code
        == 403
    )
    assert (
        mutate(
            client,
            "POST",
            "/api/v1/auth/change-password",
            {"current_password": PASSWORD, "new_password": "short"},
        ).status_code
        == 422
    )
    assert (
        mutate(
            client,
            "POST",
            "/api/v1/auth/change-password",
            {"current_password": PASSWORD, "new_password": PASSWORD},
        ).status_code
        == 422
    )
    assert (
        mutate(
            client,
            "POST",
            "/api/v1/auth/change-password",
            {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        ).status_code
        == 204
    )
    assert client.get("/api/v1/labs").status_code == 401
    sign_in(client, "temp", NEW_PASSWORD)
    assert client.get("/").status_code == 200


def test_password_invalidates_other_sessions(root, application):
    with TestClient(application) as other:
        sign_in(other)
        assert (
            mutate(
                root,
                "POST",
                "/api/v1/auth/change-password",
                {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            ).status_code
            == 204
        )
        assert other.get("/api/v1/labs").status_code == 401
    with unit_of_work(application.state.engine) as db:
        assert db.scalar(select(LoginSession)) is None


def test_provision_reset_role_and_audit(root, application):
    response = mutate(
        root,
        "POST",
        "/api/v1/users",
        {
            "username": "new-rd",
            "display_name": "Synthetic RD",
            "team": "Demo",
            "email": "NEW@example.com",
            "temporary_password": PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    user_id = response.json()["id"]
    assert response.json()["must_change_password"] is True
    assert response.json()["email"] == "new@example.com"
    assert "password" not in response.text.replace("must_change_password", "")
    with unit_of_work(application.state.engine) as db:
        user = db.get(User, user_id)
        assert user.password_hash != PASSWORD and verify_password(user.password_hash, PASSWORD)
    assert (
        mutate(root, "PATCH", f"/api/v1/users/{user_id}", {"role": "lab_admin"}).json()["role"] == "lab_admin"
    )
    assert (
        mutate(
            root, "POST", f"/api/v1/users/{user_id}/reset-password", {"temporary_password": NEW_PASSWORD}
        ).status_code
        == 204
    )
    with unit_of_work(application.state.engine) as db:
        audit = json.dumps([a.details_json for a in db.scalars(select(AuditEvent))])
        assert PASSWORD not in audit and NEW_PASSWORD not in audit
    sign_in(root, "lab")
    assert (
        mutate(
            root,
            "POST",
            "/api/v1/users",
            {
                "username": "bad",
                "display_name": "Bad",
                "team": "Demo",
                "email": "bad@example.com",
                "temporary_password": PASSWORD,
            },
        ).status_code
        == 403
    )
    assert (
        mutate(
            root, "POST", f"/api/v1/users/{user_id}/reset-password", {"temporary_password": PASSWORD}
        ).status_code
        == 403
    )
    assert mutate(root, "PATCH", f"/api/v1/users/{user_id}", {"role": "super_admin"}).status_code == 403
    assert root.get("/admin/users", follow_redirects=False).status_code == 403


def test_reset_revokes_sessions_and_regates(root, application):
    user_id = identity(application, "rd")
    with TestClient(application) as other:
        sign_in(other, "rd")
        assert (
            mutate(
                root, "POST", f"/api/v1/users/{user_id}/reset-password", {"temporary_password": NEW_PASSWORD}
            ).status_code
            == 204
        )
        assert other.get("/api/v1/labs").status_code == 401
        sign_in(other, "rd", NEW_PASSWORD)
        assert other.get("/api/v1/labs").status_code == 403


@pytest.mark.parametrize(
    "extra",
    [
        {"role": "super_admin"},
        {"username": "root"},
        {"is_active": False},
        {"id": 1},
        {"must_change_password": False},
    ],
)
def test_profile_mass_assignment_denied(client, extra):
    sign_in(client, "rd")
    response = mutate(
        client,
        "PATCH",
        "/api/v1/users/me",
        {"display_name": "New", "team": "Demo", "email": "rd@example.com", **extra},
    )
    assert response.status_code == 422


def test_profile_allowlist_validation_and_uniqueness(client, application):
    sign_in(client, "rd")
    data = {"display_name": "New name", "team": "New team", "email": "Updated@Example.com"}
    assert mutate(client, "PATCH", "/api/v1/users/me", data).json()["email"] == "updated@example.com"
    assert client.get("/profile").status_code == 200
    assert (
        mutate(client, "PATCH", "/api/v1/users/me", {**data, "email": "ROOT@example.com"}).status_code == 409
    )
    assert mutate(client, "PATCH", "/api/v1/users/me", {**data, "email": "bad"}).status_code == 422
    assert mutate(client, "PATCH", "/api/v1/users/me", {**data, "display_name": "  "}).status_code == 422
    assert (
        mutate(
            client, "PATCH", f"/api/v1/users/{identity(application, 'root')}", {"role": "user"}
        ).status_code
        == 403
    )
    assert client.patch("/api/v1/users/me", json=data).status_code == 403


def test_password_validation_never_echoes_secret(client):
    marker = "PRIVATE-PASSWORD-MARKER"
    response = mutate(client, "POST", "/api/v1/auth/login", {"username": "root", "password": {"raw": marker}})
    assert response.status_code == 422 and marker not in response.text
    response = mutate(client, "POST", "/api/v1/auth/login", {"username": "root", "password": marker})
    assert response.status_code == 401 and marker not in response.text


def test_rate_limit(client):
    for _ in range(20):
        response = mutate(client, "POST", "/api/v1/auth/login", {"username": "absent", "password": "wrong"})
        assert response.status_code == 401
    assert (
        mutate(client, "POST", "/api/v1/auth/login", {"username": "root", "password": PASSWORD}).status_code
        == 429
    )


def test_expired_and_tampered_session(root, application):
    from datetime import timedelta
    from app.core.database import utcnow

    with unit_of_work(application.state.engine, write=True) as db:
        db.scalar(select(LoginSession)).expires_at = utcnow() - timedelta(seconds=1)
    assert root.get("/api/v1/labs").status_code == 401
    root.cookies.clear()
    root.cookies.set("sut_session", "invalid.signature")
    assert root.get("/api/v1/labs").status_code == 401


def test_admin_html_account_workflow(root, application):
    response = root.post(
        "/admin/users",
        data={
            "csrf_token": csrf(root),
            "username": "html-user",
            "display_name": "Synthetic HTML User",
            "team": "Demo",
            "email": "html@example.com",
            "temporary_password": PASSWORD,
            "role": "user",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    user_id = identity(application, "html-user")
    assert root.get(f"/admin/users/{user_id}").status_code == 200
    for action, data in [
        ("role", {"role": "lab_admin"}),
        ("reset-password", {"temporary_password": NEW_PASSWORD}),
        ("status", {"is_active": "false", "reason": "Synthetic test"}),
    ]:
        response = root.post(
            f"/admin/users/{user_id}/{action}",
            data={"csrf_token": csrf(root), **data},
            follow_redirects=False,
        )
        assert response.status_code == 303, response.text
    assert (
        root.post(
            f"/admin/users/{user_id}/status",
            data={"csrf_token": csrf(root), "is_active": "true"},
            follow_redirects=False,
        ).status_code
        == 303
    )
