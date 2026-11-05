"""HTML authorization and safe read projections, no SSH in these cases."""

import hashlib
import json
from pathlib import Path

import pytest

from app.core.database import unit_of_work
from app.models.console import ConsoleSession
from conftest import create_inventory, sign_in


@pytest.mark.parametrize(
    "path",
    [
        "/console/sessions",
        "/admin/console-clients",
        "/admin/console-grants",
        "/suts/1/connections",
        "/suts/1/console",
    ],
)
def test_console_pages_off_are_unavailable(client, path):
    sign_in(client)
    assert client.get(path).status_code == 404
    assert "Open Remote Console" not in client.get("/").text


def test_connection_edit_separate_from_terminal_policy(application, client):
    sign_in(client)
    _, sut = create_inventory(client)
    application.state.settings.console_enabled = True
    application.state.settings.console_allow_insecure_http = True
    sign_in(client, "rd")
    assert client.get(f"/suts/{sut}/connections").status_code == 200
    assert client.get(f"/suts/{sut}/console").status_code == 403
    assert client.get("/console/sessions").status_code == 200
    assert client.get("/admin/console-clients").status_code == 403
    assert client.get("/admin/console-grants").status_code == 403
    assert client.get("/api/v1/console/admin/grants").status_code == 403
    assert client.get("/api/v1/console/admin/grant-options").status_code == 403
    assert "Edit inventory" not in client.get(f"/suts/{sut}").text
    assert "Open Remote Console" in client.get(f"/suts/{sut}").text
    with unit_of_work(application.state.engine) as db:
        assert not list(db.query(ConsoleSession))


def test_admin_pages_and_secret_free_picker(application, client):
    sign_in(client)
    create_inventory(client)
    application.state.settings.console_enabled = True
    application.state.settings.console_allow_insecure_http = True
    sign_in(client, "lab")
    assert client.get("/admin/console-clients").status_code == 200
    assert client.get("/admin/console-grants").status_code == 200
    data = client.get("/api/v1/console/admin/grant-options").json()
    assert data["users"] and data["suts"] == []
    assert all(set(item) == {"id", "display_name", "team"} for item in data["users"])
    assert not {"password_hash", "email", "role", "must_change_password"} & set(data["users"][0])
    assert client.get("/api/v1/console/admin/grants").json() == {"items": []}


def test_terminal_transport_csp_and_no_probe(application, client):
    sign_in(client)
    _, sut = create_inventory(client)
    application.state.settings.console_enabled = True
    assert client.get(f"/suts/{sut}/console").status_code == 403
    application.state.settings.console_allow_insecure_http = True
    response = client.get(f"/suts/{sut}/console")
    assert response.status_code == 200
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert "unsafe-eval" not in response.headers["content-security-policy"]
    assert "'unsafe-inline'" not in client.get("/").headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"
    assert "Not Connected" in response.text and "Not Configured" not in response.text  # fetched without SSH
    assert "Clear Screen" not in response.text
    assert 'type="password"' in response.text


def test_pinned_local_terminal_assets_match_provenance():
    directory = Path(__file__).parents[1] / "app/static/vendor/console"
    provenance = json.loads((directory / "PROVENANCE.json").read_text())
    assert provenance["packages"]["@xterm/xterm"] == "6.0.0"
    manifest = json.loads((Path(__file__).parents[2] / "frontend/console/package.json").read_text())
    assert provenance["packages"] == manifest["dependencies"]
    for name, value in provenance["sha256"].items():
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == value
    assert all(
        (directory / name).exists()
        for name in [
            "xterm-xterm.LICENSE",
            "xterm-addon-fit.LICENSE",
            "xterm-addon-search.LICENSE",
            "noble-hashes.LICENSE",
        ]
    )
