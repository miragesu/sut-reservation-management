"""Real Chromium smoke against a migrated temporary database; synthetic data only."""

import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    from playwright.sync_api import expect, sync_playwright

    with tempfile.TemporaryDirectory(prefix="sut-browser-") as temp:
        secret = secrets.token_urlsafe(48)
        password = secrets.token_urlsafe(24)
        replacement = secrets.token_urlsafe(24)
        environment = {
            **os.environ,
            "PYTHONPATH": str(ROOT / "backend"),
            "SECRET_KEY": secret,
            "DATABASE_URL": f"sqlite:///{temp}/sut.db",
            "APP_ENV": "development",
            "COOKIE_SECURE": "false",
            "BOOTSTRAP_USERNAME": "demo",
            "BOOTSTRAP_DISPLAY_NAME": "Synthetic Admin",
            "BOOTSTRAP_TEAM": "Demo",
            "BOOTSTRAP_EMAIL": "demo@example.com",
            "BOOTSTRAP_PASSWORD": password,
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
        with open(Path(temp) / "server.log", "w") as log:
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
                        if urlopen(base + "/health", timeout=1).status == 200:
                            break
                    except OSError:
                        if process.poll() is not None:
                            raise RuntimeError("Server exited during startup")
                        time.sleep(0.1)
                else:
                    raise RuntimeError("Server readiness timeout")
                with sync_playwright() as p:
                    executable = os.environ.get("CHROMIUM_PATH") or shutil.which("chromium")
                    browser = p.chromium.launch(**({"executable_path": executable} if executable else {}))
                    page = browser.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(base + "/")
                    assert page.url.endswith("/login")
                    page.get_by_label("Username", exact=True).fill("demo")
                    page.get_by_label("Password", exact=True).fill(password)
                    page.get_by_role("button", name="Sign in", exact=True).click()
                    page.wait_for_url("**/change-password")
                    page.get_by_label("Current password", exact=True).fill(password)
                    page.get_by_label("New password (12–128 characters)", exact=True).fill(replacement)
                    page.get_by_role("button", name="Save and sign out all sessions").click()
                    page.wait_for_url("**/login")
                    page.get_by_label("Username", exact=True).fill("demo")
                    page.get_by_label("Password", exact=True).fill(replacement)
                    page.get_by_role("button", name="Sign in", exact=True).click()
                    page.wait_for_url(base + "/")
                    assert page.locator(".card-layout:visible [data-sut-id]").count() == 20
                    page.get_by_role("button", name="Table", exact=True).click()
                    assert page.locator(".table-layout:visible tbody tr").count() == 20
                    page.get_by_label("SUT name", exact=True).fill("Demo-SUT-10")
                    page.get_by_label("Sort", exact=True).select_option("status")
                    with page.expect_response("**/dashboard/fragment?*"):
                        page.get_by_role("button", name="Apply filters").click()
                    expect(page.locator(".table-layout:visible tbody tr")).to_have_count(2)
                    assert (
                        page.get_by_role("button", name="Table", exact=True).get_attribute("aria-pressed")
                        == "true"
                    )
                    page.get_by_role("button", name="Card", exact=True).click()
                    assert page.locator(".card-layout:visible [data-sut-id]").count() == 2
                    # Mutate via an authenticated session and verify real 30-second polling.
                    csrf = page.locator("meta[name=csrf-token]").get_attribute("content")
                    response = page.request.patch(
                        base + "/api/v1/suts/10/operational-state",
                        data={"state": "maintenance", "reason": "Synthetic browser repair"},
                        headers={"X-CSRF-Token": csrf},
                    )
                    assert response.status == 200
                    page.get_by_label("Platform", exact=True).fill("unsaved filter")
                    page.get_by_label("Platform", exact=True).fill("")
                    page.get_by_text("Synthetic browser repair", exact=True).wait_for(timeout=35000)
                    assert page.get_by_label("SUT name", exact=True).input_value() == "Demo-SUT-10"
                    assert page.get_by_label("Sort", exact=True).input_value() == "status"
                    assert (
                        page.get_by_role("button", name="Card", exact=True).get_attribute("aria-pressed")
                        == "true"
                    )
                    # Failure cue retains previous data; restore and refresh.
                    page.route("**/dashboard/fragment?*", lambda route: route.abort())
                    page.get_by_role("button", name="Apply filters").click()
                    page.get_by_text("Data may be stale.", exact=False).wait_for()
                    assert page.locator(".card-layout:visible [data-sut-id]").count() == 2
                    page.unroute("**/dashboard/fragment?*")
                    page.get_by_role("button", name="Apply filters").click()
                    expect(page.locator("#refresh-status")).to_contain_text("Updated")
                    page.goto(base + "/suts/10")
                    assert page.get_by_text("Synthetic browser repair", exact=False).count() >= 1
                    page.goto(base + "/profile")
                    page.get_by_label("Display name", exact=True).fill("Updated Synthetic Admin")
                    page.get_by_role("button", name="Save profile").click()
                    assert (
                        page.get_by_label("Display name", exact=True).input_value()
                        == "Updated Synthetic Admin"
                    )
                    assert errors == [], errors
                    browser.close()
                print(
                    "PASS: Chromium login, mandatory password change, seeded dashboard, layouts, filters, 30s polling, stale/retry, detail and profile"
                )
            finally:
                process.terminate()
                process.wait(timeout=10)


if __name__ == "__main__":
    main()
