"""Real multi-user Chromium coordination workflow against disposable migrated SQLite."""

import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
TAIPEI = ZoneInfo("Asia/Taipei")


def main():
    with tempfile.TemporaryDirectory(prefix="sut-day3-browser-") as temp, ExitStack() as stack:
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
                    if name == "demo":
                        page.clock.install()
                    page.goto(base + "/login")
                    page.get_by_label("Username", exact=True).fill(name)
                    page.get_by_label("Password", exact=True).fill(passwords[name])
                    page.get_by_role("button", name="Sign in", exact=True).click()
                    page.wait_for_url(base + "/")
                    pages[name] = page
                admin, rd, lab = (pages[n] for n in ("demo", "rd", "lab"))

                def open_action(page, action, sut=1, table=False):
                    layout = ".table-layout" if table else ".card-layout"
                    page.locator(f'{layout} [data-sut-id="{sut}"] [data-quick-action="{action}"]').click()
                    expect(page.locator("#quick-modal")).to_be_visible()
                    expect(page.locator("#quick-submit")).to_be_enabled()

                def close_modal(page):
                    page.locator("#quick-modal").get_by_role("button", name="Close", exact=True).last.click()
                    expect(page.locator("#quick-modal")).not_to_be_visible()

                expect(admin.locator("#notification-status")).to_contain_text("Inbox")
                open_action(admin, "claim")
                admin.get_by_label("Estimated duration (minutes)", exact=True).fill("4320")
                admin.get_by_label("Purpose", exact=True).fill("Day 3 modal input retained")
                # Actual 30-second Dashboard polling must not replace this form.
                admin.wait_for_timeout(31000)
                expect(admin.get_by_label("Purpose", exact=True)).to_have_value("Day 3 modal input retained")
                admin.locator("#quick-submit").click()
                expect(admin.locator("#quick-modal")).not_to_be_visible()
                expect(admin.locator('.card-layout [data-sut-id="1"]')).to_contain_text("In Use")
                rd.get_by_role("button", name="Table", exact=True).click()
                open_action(rd, "queue", table=True)
                rd.get_by_label("Estimated duration (minutes)", exact=True).fill("30")
                rd.locator("#quick-submit").click()
                expect(rd.locator("#quick-modal")).not_to_be_visible()
                assert len(api["rd"].get("/api/v1/suts/1/queue").json()["items"]) == 1
                # A competing claim produces a visible error and preserves input.
                open_action(lab, "claim")
                lab.get_by_label("Purpose", exact=True).fill("Preserve on conflict")
                lab.locator("#quick-submit").click()
                expect(lab.locator("#quick-feedback")).not_to_contain_text("Submitting")
                expect(lab.get_by_label("Purpose", exact=True)).to_have_value("Preserve on conflict")
                close_modal(lab)
                usage = api["demo"].get("/api/v1/suts/1/coordination").json()["usage"]
                assert (
                    mutate(
                        api["demo"], "POST", "/api/v1/suts/1/release", {"usage_key": usage["usage_key"]}
                    ).status_code
                    == 200
                )
                open_action(rd, "claim", table=True)
                rd.locator("#quick-submit").click()
                expect(rd.locator("#quick-modal")).not_to_be_visible()
                assert api["rd"].get("/api/v1/suts/1/coordination").json()["usage"]["user"]["display_name"]
                # Table reservation, card reservation conflict acknowledgement.
                open_action(rd, "reserve", sut=2, table=True)
                start = datetime.now(TAIPEI) + timedelta(hours=1)
                rd.get_by_label("Start (Asia/Taipei)", exact=True).fill(start.strftime("%Y-%m-%dT%H:%M:%S"))
                rd.get_by_label("End (Asia/Taipei)", exact=True).fill(
                    (start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
                )
                rd.get_by_label("Purpose", exact=True).fill("Day 3 booking")
                rd.locator("#quick-submit").click()
                expect(rd.locator("#quick-modal")).not_to_be_visible()
                open_action(admin, "claim", sut=2)
                admin.get_by_label("Estimated duration (minutes)", exact=True).fill("180")
                admin.locator("#quick-submit").click()
                expect(admin.locator("#quick-conflict")).to_be_visible()
                assert api["demo"].get("/api/v1/suts/2/coordination").json()["usage"] is None
                admin.locator("#quick-ack").check()
                admin.locator("#quick-submit").click()
                expect(admin.locator("#quick-modal")).not_to_be_visible()
                open_action(admin, "detail", sut=2)
                expect(admin.locator("#quick-detail")).to_contain_text("Day 3 booking")
                admin.keyboard.press("Escape")
                expect(admin.locator("#quick-modal")).not_to_be_visible()
                # Remaining action/layout combinations share the same modal/service.
                open_action(lab, "queue", sut=4)
                lab.locator("#quick-submit").click()
                expect(lab.locator("#quick-feedback")).to_contain_text("Claim")
                close_modal(lab)
                open_action(lab, "reserve", sut=3)
                lab.get_by_label("Start (Asia/Taipei)", exact=True).fill(start.strftime("%Y-%m-%dT%H:%M:%S"))
                lab.get_by_label("End (Asia/Taipei)", exact=True).fill(
                    (start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
                )
                lab.get_by_label("Purpose", exact=True).fill("Card booking")
                lab.locator("#quick-submit").click()
                expect(lab.locator("#quick-modal")).not_to_be_visible()
                lab.get_by_role("button", name="Table", exact=True).click()
                open_action(lab, "claim", sut=4, table=True)
                lab.locator("#quick-submit").dblclick()
                expect(lab.locator("#quick-modal")).not_to_be_visible()
                assert (
                    len([u for u in api["lab"].get("/api/v1/usages/me").json()["items"] if u["sut_id"] == 4])
                    == 1
                )
                open_action(lab, "detail", sut=4, table=True)
                close_modal(lab)
                # Other-user maintenance arrives through read-only modal polling.
                open_action(admin, "claim", sut=5)
                admin.get_by_label("Purpose", exact=True).fill("Retain while unavailable")
                assert (
                    mutate(
                        api["demo"],
                        "PATCH",
                        "/api/v1/suts/5/operational-state",
                        {"state": "maintenance", "reason": "Synthetic browser maintenance"},
                    ).status_code
                    == 200
                )
                admin.clock.fast_forward(30000)
                expect(admin.locator("#quick-submit")).to_be_disabled()
                expect(admin.get_by_label("Purpose", exact=True)).to_have_value("Retain while unavailable")
                assert (
                    mutate(
                        api["demo"], "PATCH", "/api/v1/suts/5/operational-state", {"state": "normal"}
                    ).status_code
                    == 200
                )
                admin.clock.fast_forward(30000)
                expect(admin.locator("#quick-submit")).to_be_enabled()
                close_modal(admin)
                # Mobile layouts and recipient-scoped Inbox/mark-read.
                rd.set_viewport_size({"width": 375, "height": 812})
                rd.get_by_role("button", name="Card", exact=True).click()
                open_action(rd, "detail")
                close_modal(rd)
                rd.goto(base + "/notifications")
                expect(rd.locator("[data-notification-id]").first).to_be_visible()
                rd.get_by_role("button", name="Mark read", exact=True).first.click()
                expect(rd.locator("#unread-count")).to_have_text(
                    str(api["rd"].get("/api/v1/notifications").json()["unread_count"])
                )
                # Browser platform fallbacks, no permission request on page load.
                fallback = browser.new_context()
                fallback.add_init_script("Object.defineProperty(window, 'isSecureContext', {value:false});")
                fallback.add_cookies(rd.context.cookies())
                fp = fallback.new_page()
                fp.goto(base + "/")
                expect(fp.locator("#desktop-opt-in")).to_be_disabled()
                expect(fp.locator("#notification-status")).to_contain_text("HTTPS")
                fallback.close()
                denied = browser.new_context()
                denied.add_init_script(
                    "window.Notification = class {static permission='denied'; static requestPermission(){throw Error('Must not request automatically');}};"
                )
                denied.add_cookies(rd.context.cookies())
                dp = denied.new_page()
                dp.goto(base + "/")
                expect(dp.locator("#desktop-opt-in")).to_be_disabled()
                expect(dp.locator("#notification-status")).to_contain_text("blocked")
                denied.close()
                # Deterministic browser-API tests; coordination workflows above use the real server.
                desktop = browser.new_context()
                desktop.add_cookies(rd.context.cookies())
                desktop.add_init_script("""window.Notification = class {
                  static permission = sessionStorage.getItem('synthetic-notification-permission') || 'default';
                  static async requestPermission(){document.body.dataset.permissionRequests='1'; this.permission='granted'; sessionStorage.setItem('synthetic-notification-permission','granted'); return 'granted';}
                  constructor(title, options){document.body.dataset.deliveries=String(Number(document.body.dataset.deliveries||0)+1); document.body.dataset.desktopBody=options.body;}
                };""")
                np = desktop.new_page()
                np.clock.install()
                state = {"new": False, "id": 777, "hold": False}
                held = []

                def notices(route):
                    if state["hold"] and "after_id" not in route.request.url:
                        held.append(route)
                        return
                    route.fulfill(
                        json={
                            "items": (
                                [
                                    {
                                        "id": state["id"],
                                        "sut_id": 1,
                                        "message": "Synthetic private rd@example.com",
                                        "created_at": "2026-10-15T00:00:00Z",
                                        "read_at": None,
                                    }
                                ]
                                if state["new"]
                                else []
                            ),
                            "total": state["id"] - 776 if state["new"] else 0,
                            "unread_count": state["id"] - 776 if state["new"] else 0,
                            "latest_id": state["id"] if state["new"] else 0,
                        }
                    )

                np.route("**/api/v1/notifications*", notices)
                np.goto(base + "/")
                expect(np.locator("#unread-count")).to_have_text("0")
                expect(np.locator("body")).not_to_have_attribute("data-permission-requests", "1")
                np.locator("#desktop-opt-in").click()
                expect(np.locator("body")).to_have_attribute("data-permission-requests", "1")
                state["new"] = True
                np.clock.fast_forward(30000)
                expect(np.locator("body")).to_have_attribute("data-deliveries", "1")
                expect(np.locator("body")).not_to_have_attribute(
                    "data-desktop-body", "Synthetic private rd@example.com"
                )
                np.clock.fast_forward(30000)
                expect(np.locator("body")).to_have_attribute("data-deliveries", "1")
                np.reload()
                expect(np.locator("#unread-count")).to_have_text("1")
                np.clock.fast_forward(30000)
                np.wait_for_timeout(250)
                expect(np.locator("body")).not_to_have_attribute("data-deliveries", "1")
                # A successful action arriving during an old read must queue a fresh read.
                state["hold"] = True
                np.clock.fast_forward(30000)
                np.wait_for_timeout(250)
                assert len(held) == 1
                np.locator("body").dispatch_event("coordination:changed")
                state["hold"] = False
                state["id"] = 778
                held.pop().fulfill(json={"items": [], "total": 1, "unread_count": 1, "latest_id": 777})
                expect(np.locator("#unread-count")).to_have_text("2")
                expect(np.locator("body")).to_have_attribute("data-deliveries", "1")
                desktop.close()
                # A granted permission can still fail at the browser/OS delivery step.
                failed = browser.new_context()
                failed.add_cookies(rd.context.cookies())
                failed.add_init_script(
                    "window.Notification = class {static permission='default'; static async requestPermission(){this.permission='granted';return 'granted';} constructor(){throw Error('Synthetic platform delivery failure');}};"
                )
                ep = failed.new_page()
                ep.clock.install()
                ep.route("**/api/v1/notifications*", notices)
                ep.goto(base + "/")
                expect(ep.locator("#unread-count")).to_have_text("2")
                ep.locator("#desktop-opt-in").click()
                expect(ep.locator("#notification-status")).to_contain_text("enabled")
                state["id"] = 779
                ep.clock.fast_forward(30000)
                expect(ep.locator("#notification-status")).to_contain_text(
                    "Desktop delivery unavailable. Use Inbox."
                )
                failed.close()
                unsupported = browser.new_context()
                unsupported.add_cookies(rd.context.cookies())
                unsupported.add_init_script("delete window.Notification;")
                up = unsupported.new_page()
                up.goto(base + "/")
                expect(up.locator("#desktop-opt-in")).to_be_disabled()
                unsupported.close()
                assert errors == [], errors
                browser.close()
            print(
                "PASS: Day 3 card/table modals, real polling/input retention, FIFO/manual claim, conflict acknowledgement, Taipei booking, keyboard dismissal, mobile detail and notification fallback/read workflow"
            )
        finally:
            process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    main()
