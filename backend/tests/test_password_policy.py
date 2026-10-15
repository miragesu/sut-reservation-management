import secrets

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import delete, select

from app.core.config import Settings
from app.core.database import unit_of_work
from app.models.domain import User
from app.scripts import bootstrap_admin
from app.services.accounts import validate_password, verify_password
from conftest import mutate, sign_in


@pytest.mark.parametrize("low,minimum", [(False, 12), (True, 1)])
def test_password_boundaries(low, minimum):
    settings = Settings(secret_key=secrets.token_urlsafe(48), low_security_passwd=low)
    for good in ["x" * minimum, "密" * minimum, "a" * 128]:
        validate_password(good, settings)  # No composition rules.
    for bad in ["", " ", "\t", "a" * 129, "x" * (minimum - 1)]:
        with pytest.raises(HTTPException):
            validate_password(bad, settings)


@pytest.mark.parametrize("value", ["yes", "on", "1", "", "truthy", 1, None])
def test_low_security_rejects_invalid_boolean(value):
    with pytest.raises(ValidationError):
        Settings(secret_key=secrets.token_urlsafe(48), low_security_passwd=value)


@pytest.mark.parametrize("value,expected", [("true", True), ("TRUE", True), ("false", False), (False, False)])
def test_explicit_password_mode(value, expected):
    assert (
        Settings(secret_key=secrets.token_urlsafe(48), low_security_passwd=value).low_security_passwd
        is expected
    )


@pytest.mark.parametrize("low", [False, True])
@pytest.mark.parametrize("secret", ["", "a" * 31, "REPLACE" * 10])
def test_secret_key_never_relaxed(low, secret):
    with pytest.raises(ValidationError):
        Settings(secret_key=secret, low_security_passwd=low)


@pytest.mark.parametrize("role", ["user", "lab_admin", "super_admin"])
@pytest.mark.parametrize("low", [False, True])
def test_provision_reset_change_and_html_policy(application, root, role, low):
    application.state.settings.low_security_passwd = low
    short = "甲"
    data = dict(
        username="newuser",
        display_name="Synthetic",
        team="Demo",
        email="new@example.com",
        role=role,
        temporary_password=short,
    )
    response = mutate(root, "POST", "/api/v1/users", data)
    if not low:
        assert response.status_code == 422
        data["temporary_password"] = "a" * 12
        response = mutate(root, "POST", "/api/v1/users", data)
    assert response.status_code == 201, response.text
    uid = response.json()["id"]
    response = mutate(root, "POST", f"/api/v1/users/{uid}/reset-password", {"temporary_password": "乙"})
    assert response.status_code == (204 if low else 422)
    minimum = "1" if low else "12"
    assert f"Temporary password ({minimum}–128 characters)" in root.get("/admin/users").text
    for page in ["/admin/users", f"/admin/users/{uid}", "/change-password"]:
        assert f'minlength="{minimum}"' in root.get(page).text
    with unit_of_work(application.state.engine) as db:
        user = db.get(User, uid)
        assert user.password_hash.startswith("$argon2id$")
        assert verify_password(user.password_hash, "乙" if low else "a" * 12)
        assert user.must_change_password
    mutate(root, "POST", "/api/v1/auth/logout")
    sign_in(root, "newuser", "乙" if low else "a" * 12)
    assert root.get("/api/v1/suts").status_code == 403
    response = mutate(
        root,
        "POST",
        "/api/v1/auth/change-password",
        {"current_password": "乙" if low else "a" * 12, "new_password": "丙"},
    )
    assert response.status_code == (204 if low else 422)
    if low:
        assert root.get("/api/v1/suts").status_code == 401
        sign_in(root, "newuser", "丙")
        assert root.get("/api/v1/suts").status_code == 200
    # Empty remains rejected in all mutation paths, even when low mode is enabled.
    with pytest.raises(HTTPException):
        validate_password("", application.state.settings)


@pytest.mark.parametrize("low,password", [(False, "a" * 12), (True, "甲")])
def test_interactive_bootstrap_policy(application, monkeypatch, low, password):
    with unit_of_work(application.state.engine, write=True) as db:
        db.execute(delete(User))  # Isolated fixture only, before any sessions exist.
    monkeypatch.setenv("SECRET_KEY", secrets.token_urlsafe(48))
    monkeypatch.setenv("LOW_SECURITY_PASSWD", str(low).lower())
    values = iter(["initial", "Synthetic Admin", "Demo", "initial@example.com"])
    monkeypatch.setattr("builtins.input", lambda _: next(values))
    monkeypatch.setattr(bootstrap_admin.getpass, "getpass", lambda _: password)
    bootstrap_admin.main()
    with unit_of_work(application.state.engine) as db:
        user = db.scalar(select(User).where(User.username == "initial"))
        assert verify_password(user.password_hash, password)
        assert user.must_change_password and user.role == "super_admin"


def test_mode_absent_defaults_secure(monkeypatch):
    monkeypatch.delenv("LOW_SECURITY_PASSWD", raising=False)
    settings = Settings(secret_key=secrets.token_urlsafe(48), _env_file=None)
    assert settings.password_minimum == 12 and settings.low_security_passwd is False
