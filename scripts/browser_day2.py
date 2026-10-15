"""Real multi-user Chromium coordination workflow against disposable migrated SQLite."""

import os
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
TAIPEI = ZoneInfo("Asia/Taipei")


def main():
    with tempfile.TemporaryDirectory(prefix="sut-day2-browser-") as temp, ExitStack() as stack:
        database = Path(temp) / "sut.db"
        initial = secrets.token_urlsafe(24)
        passwords = {name: secrets.token_urlsafe(24) for name in ("demo", "rd", "lab")}
        environment = {
            **os.environ,
            "PYTHONPATH": str(ROOT / "backend"),
            "SECRET_KEY": secrets.token_urlsafe(48),
            "DATABASE_URL": f"sqlite:///{database}",
            "APP_ENV": "development",
            "COOKIE_SECURE": "false",
            "BOOTSTRAP_USERNAME": "demo",
            "BOOTSTRAP_DISPLAY_NAME": "Browser Admin",
            "BOOTSTRAP_TEAM": "Demo",
            "BOOTSTRAP_EMAIL": "demo@example.com",
            "BOOTSTRAP_PASSWORD": initial,
        }
        for args in [
            ["-m", "alembic", "upgrade", "head"],
            ["-m", "app.scripts.bootstrap_admin"],
            ["-m", "app.scripts.seed"],
        ]:
            subprocess.run([sys.executable, *args], cwd=ROOT / "backend", env=environment, check=True)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        log = stack.enter_context(open(Path(temp) / "server.log", "w"))
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=ROOT / "backend",
            env=environment,
            stdout=log,
            stderr=log,
        )
        try:
            for _ in range(100):
                try:
                    if httpx.get(base + "/health", timeout=1, trust_env=False).status_code == 200:
                        break
                except httpx.HTTPError:
                    if process.poll() is not None:
                        raise RuntimeError("Server failed to start")
                    time.sleep(0.1)
            else:
                raise RuntimeError("Server readiness timeout")
            api = {
                name: stack.enter_context(httpx.Client(base_url=base, trust_env=False)) for name in passwords
            }

            def mutate(client, method, path, data=None):
                token = client.get("/api/v1/auth/csrf").json()["csrf_token"]
                return client.request(method, path, json=data, headers={"X-CSRF-Token": token})

            def login_api(client, name, password):
                response = mutate(
                    client, "POST", "/api/v1/auth/login", {"username": name, "password": password}
                )
                assert response.status_code == 200, response.text

            login_api(api["demo"], "demo", initial)
            assert (
                mutate(
                    api["demo"],
                    "POST",
                    "/api/v1/auth/change-password",
                    {"current_password": initial, "new_password": passwords["demo"]},
                ).status_code
                == 204
            )
            login_api(api["demo"], "demo", passwords["demo"])
            for name, role in [("rd", "user"), ("lab", "lab_admin")]:
                assert (
                    mutate(
                        api["demo"],
                        "POST",
                        "/api/v1/users",
                        {
                            "username": name,
                            "display_name": "Browser " + name,
                            "team": "Demo",
                            "email": name + "@example.com",
                            "temporary_password": initial,
                            "role": role,
                        },
                    ).status_code
                    == 201
                )
                login_api(api[name], name, initial)
                assert (
                    mutate(
                        api[name],
                        "POST",
                        "/api/v1/auth/change-password",
                        {"current_password": initial, "new_password": passwords[name]},
                    ).status_code
                    == 204
                )
                login_api(api[name], name, passwords[name])
            with sync_playwright() as p:
                executable = os.environ.get("CHROMIUM_PATH") or shutil.which("chromium")
                browser = p.chromium.launch(**({"executable_path": executable} if executable else {}))
                errors = []
                pages = {}
                for name in passwords:
                    page = browser.new_context().new_page()
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(base + "/login")
                    page.get_by_label("Username", exact=True).fill(name)
                    page.get_by_label("Password", exact=True).fill(passwords[name])
                    page.get_by_role("button", name="Sign in", exact=True).click()
                    page.wait_for_url(base + "/")
                    pages[name] = page
                admin, rd, lab = (pages[n] for n in ("demo", "rd", "lab"))

                def visit(page, sut=1):
                    page.goto(base + f"/suts/{sut}")

                def claim_ui(page, minutes, purpose):
                    page.get_by_label(
                        "Expected duration (minutes; custom multi-day estimates allowed)", exact=True
                    ).fill(str(minutes))
                    page.get_by_label("Purpose (optional)", exact=True).fill(purpose)
                    page.get_by_role("button", name="Start using", exact=True).click()

                def join_ui(page):
                    page.get_by_label("Requested duration (minutes)", exact=True).fill("30")
                    page.get_by_role("button", name="Join Queue", exact=True).click()

                visit(admin)
                claim_ui(admin, 60, "Browser root usage")
                visit(rd)
                join_ui(rd)
                visit(lab)
                join_ui(lab)
                admin.get_by_role("button", name="Release", exact=True).click()
                assert api["demo"].get("/api/v1/suts/1/coordination").json()["usage"] is None
                visit(rd)
                claim_ui(rd, 30, "Browser RD usage")
                original = api["rd"].get("/api/v1/suts/1/coordination").json()["usage"]
                rd.get_by_label("Expected end", exact=True).fill(
                    (datetime.now(TAIPEI) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
                )
                rd.get_by_role("button", name="Update expected end", exact=True).click()
                assert (
                    api["rd"].get("/api/v1/suts/1/coordination").json()["usage"]["usage_key"]
                    == original["usage_key"]
                )
                rd.get_by_role("button", name="Release", exact=True).click()
                visit(lab)
                claim_ui(lab, 30, "Browser Lab usage")
                visit(admin)
                admin.get_by_label("Release note (required for force-release)", exact=True).fill(
                    "Browser reviewed cleanup"
                )
                admin.get_by_role("button", name="Force Release", exact=True).click()
                history = api["demo"].get("/api/v1/history").json()
                assert history["total"] == 3 and history["items"][0]["release_reason"] == "admin"
                admin.goto(base + "/history")
                expect(admin.get_by_role("heading", name="Usage History", exact=True)).to_be_visible()
                assert "Browser RD usage" in admin.content()

                def reserve_ui(page, sut, purpose):
                    page.goto(base + f"/reservations/new?sut_id={sut}")
                    start = datetime.now(TAIPEI) + timedelta(hours=1)
                    page.get_by_label("Start", exact=True).fill(start.strftime("%Y-%m-%dT%H:%M"))
                    page.get_by_label("End", exact=True).fill(
                        (start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
                    )
                    page.get_by_label("Purpose", exact=True).fill(purpose)
                    page.get_by_role("button", name="Save reservation", exact=True).click()
                    page.wait_for_url("**/reservations/*")
                    return int(page.url.rsplit("/", 1)[1])

                booking_id = reserve_ui(rd, 1, "Browser reservation")
                rd.get_by_role("link", name="Edit reservation", exact=True).click()
                rd.get_by_label("Purpose", exact=True).fill("Edited browser reservation")
                rd.get_by_role("button", name="Save reservation", exact=True).click()
                expect(rd.get_by_text("Edited browser reservation", exact=True)).to_be_visible()
                rd.goto(base + "/calendar?view=week")
                expect(rd.get_by_text("Edited browser reservation", exact=True)).to_be_visible()
                rd.goto(base + f"/reservations/{booking_id}")
                rd.get_by_role("button", name="Cancel reservation", exact=True).click()
                assert api["rd"].get(f"/api/v1/reservations/{booking_id}").json()["status"] == "cancelled"
                reserve_ui(rd, 2, "Browser overlap booking")
                visit(admin, 2)
                claim_ui(admin, 180, "Browser acknowledged overlap")
                expect(
                    admin.get_by_role(
                        "heading", name="Reservation overlap — confirmation required", exact=True
                    )
                ).to_be_visible()
                admin.get_by_role("checkbox").check()
                admin.get_by_role("button", name="Confirm scheduling conflict", exact=True).click()
                held = api["demo"].get("/api/v1/suts/2/coordination").json()["usage"]
                assert (
                    datetime.fromisoformat(held["expected_end_time"])
                    - datetime.fromisoformat(held["start_time"])
                ) == timedelta(hours=3)
                admin.get_by_role("button", name="Release", exact=True).click()
                # Attendance under an existing holder. Only this disposable database is shifted to a near-start timeline.
                visit(admin)
                claim_ui(admin, 60, "Browser temporary holder")
                visit(lab)
                join_ui(lab)
                attended = reserve_ui(rd, 1, "Browser check-in booking")
                now = datetime.now(UTC)
                with sqlite3.connect(database) as db:
                    db.execute(
                        "UPDATE reservations SET start_time=?,end_time=? WHERE id=?",
                        (
                            (now - timedelta(minutes=1)).replace(tzinfo=None).isoformat(" "),
                            (now + timedelta(minutes=59)).replace(tzinfo=None).isoformat(" "),
                            attended,
                        ),
                    )
                rd.goto(base + f"/reservations/{attended}")
                rd.wait_for_timeout(1500)
                rd.reload()
                expect(rd.locator("main")).to_contain_text("Waiting for release")
                expect(rd.locator('form[action$="/check-in"]')).to_have_count(0)
                assert (
                    api["rd"].get(f"/api/v1/reservations/{attended}").json()["status"]
                    == "waiting_for_release"
                )
                visit(admin)
                admin.get_by_role("button", name="Release", exact=True).click()
                assert api["demo"].get("/api/v1/suts/1/coordination").json()["usage"] is None
                visit(lab)
                claim_ui(lab, 1, "Must not bypass priority")
                expect(
                    lab.get_by_text(
                        "Another reservation holder has priority until release of reservation protection",
                        exact=True,
                    )
                ).to_be_visible()
                visit(rd)
                claim_ui(rd, 1, "Browser reservation Claim")
                assert (
                    api["rd"].get("/api/v1/suts/1/coordination").json()["usage"]["reservation_id"] == attended
                )
                rd.get_by_role("button", name="Release", exact=True).click()
                # Real 30s Detail polling must retain unsaved Claim controls and reflect external maintenance.
                visit(lab)
                lab.get_by_label("Purpose (optional)", exact=True).fill("Keep unsaved purpose")
                lab.get_by_label(
                    "Expected duration (minutes; custom multi-day estimates allowed)", exact=True
                ).fill("720")
                assert (
                    mutate(
                        api["demo"],
                        "PATCH",
                        "/api/v1/suts/1/operational-state",
                        {
                            "state": "maintenance",
                            "reason": "Browser Day 2 repair",
                            "acknowledge_activity": True,
                        },
                    ).status_code
                    == 200
                )
                lab.get_by_text("Browser Day 2 repair", exact=False).wait_for(timeout=35000)
                assert (
                    lab.get_by_label("Purpose (optional)", exact=True).input_value() == "Keep unsaved purpose"
                )
                assert (
                    lab.get_by_label(
                        "Expected duration (minutes; custom multi-day estimates allowed)", exact=True
                    ).input_value()
                    == "720"
                )
                expect(lab.get_by_role("button", name="Start using", exact=True)).to_be_disabled()
                assert (
                    mutate(
                        api["demo"], "PATCH", "/api/v1/suts/1/operational-state", {"state": "normal"}
                    ).status_code
                    == 200
                )
                rd.goto(base + "/notifications")
                assert rd.locator("[data-notification-id]").count() > 0
                assert errors == [], errors
                browser.close()
            print(
                "PASS: Chromium multi-user Claim/Release/FIFO, force-release, estimate update, reservation create/edit/cancel/calendar, explicit overlap acknowledgement, availability-based priority/manual start, history/inbox and real 30s Detail polling preserving input"
            )
        finally:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    main()
