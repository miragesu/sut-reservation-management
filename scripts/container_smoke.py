"""Disposable Compose integration check. Deletes only its own synthetic test volume."""

import json
import os
import re
import shutil
import secrets
import socket
from urllib.parse import urlsplit
import subprocess
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    project = "sut-smoke-" + secrets.token_hex(5)
    password = secrets.token_urlsafe(24)
    replacement = secrets.token_urlsafe(24)
    environment = {
        **os.environ,
        "SECRET_KEY": secrets.token_urlsafe(48),
        "COOKIE_SECURE": "false",
        "APP_BIND": "127.0.0.1",
        "APP_PORT": "5088",
        "SUT_GIT_REF": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "BOOTSTRAP_USERNAME": "demo",
        "BOOTSTRAP_DISPLAY_NAME": "Synthetic Admin",
        "BOOTSTRAP_TEAM": "Demo",
        "BOOTSTRAP_EMAIL": "demo@example.com",
        "BOOTSTRAP_PASSWORD": password,
    }
    remote_ref = os.environ.get("SUT_SMOKE_REMOTE_REF")
    if remote_ref:
        if not re.fullmatch(r"[0-9a-f]{40}", remote_ref):
            raise ValueError("SUT_SMOKE_REMOTE_REF must be a full commit SHA")
        environment["SUT_GIT_REF"] = remote_ref
    with tempfile.TemporaryDirectory(prefix="sut-compose-") as temp:
        working_directory = Path(temp) if remote_ref else ROOT
        if remote_ref:
            # Only Compose and host-managed build settings exist here; no source checkout.
            shutil.copyfile(ROOT / "compose.yaml", working_directory / "compose.yaml")
        overrides = Path(temp) / "build.json"
        build = {"args": ["HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"]}
        if os.environ.get("SUT_BUILD_NETWORK"):
            build["network"] = os.environ["SUT_BUILD_NETWORK"]
        config = {"services": {"sut-management": {"build": build}}}
        if os.environ.get("SUT_BUILD_CA"):
            build["secrets"] = ["build_ca"]
            config["secrets"] = {"build_ca": {"file": os.environ["SUT_BUILD_CA"]}}
        proxy = os.environ.get("HTTPS_PROXY")
        if proxy:
            host = urlsplit(proxy).hostname
            build["extra_hosts"] = [f"{host}:{socket.gethostbyname(host)}"]
        overrides.write_text(json.dumps(config))
        compose = [
            "docker",
            "compose",
            "-p",
            project,
            "-f",
            str(working_directory / "compose.yaml"),
            *([] if remote_ref else ["-f", str(ROOT / "compose.local.yaml")]),
            "-f",
            str(overrides),
        ]

        def run(*args, capture=False):
            return subprocess.run(
                [*compose, *args],
                cwd=working_directory,
                env=environment,
                text=True,
                capture_output=capture,
                check=True,
            )

        def ready():
            for _ in range(100):
                try:
                    response = httpx.get("http://127.0.0.1:5088/health", timeout=2, trust_env=False)
                    if response.status_code == 200 and response.json() == {"status": "ok"}:
                        return
                except (httpx.HTTPError, ValueError):
                    pass
                time.sleep(0.2)
            raise RuntimeError("Published port readiness timeout")

        def mutation(client, method, path, data):
            token = client.get("/api/v1/auth/csrf").json()["csrf_token"]
            return client.request(method, path, json=data, headers={"X-CSRF-Token": token})

        try:
            run("config", "--quiet")
            run("up", "-d", "--build")
            ready()
            from container_day3 import check_port_contract, check_published_browser

            check_port_contract(run)
            broken = subprocess.run(
                [
                    *compose,
                    "run",
                    "--rm",
                    "--no-deps",
                    "-e",
                    "DATABASE_URL=sqlite:////app/missing/sut.db",
                    "sut-management",
                ],
                cwd=working_directory,
                env=environment,
                text=True,
                capture_output=True,
            )
            assert broken.returncode != 0, "Broken migration must prevent startup"
            assert "Uvicorn running" not in broken.stdout + broken.stderr
            run(
                "exec",
                "-T",
                "-e",
                "BOOTSTRAP_USERNAME",
                "-e",
                "BOOTSTRAP_DISPLAY_NAME",
                "-e",
                "BOOTSTRAP_TEAM",
                "-e",
                "BOOTSTRAP_EMAIL",
                "-e",
                "BOOTSTRAP_PASSWORD",
                "sut-management",
                "python",
                "-m",
                "app.scripts.bootstrap_admin",
            )
            with httpx.Client(base_url="http://127.0.0.1:5088", trust_env=False) as client:
                assert (
                    mutation(
                        client, "POST", "/api/v1/auth/login", {"username": "demo", "password": password}
                    ).status_code
                    == 200
                )
                assert client.get("/api/v1/labs").status_code == 403
                assert (
                    mutation(
                        client,
                        "POST",
                        "/api/v1/auth/change-password",
                        {"current_password": password, "new_password": replacement},
                    ).status_code
                    == 204
                )
                assert (
                    mutation(
                        client, "POST", "/api/v1/auth/login", {"username": "demo", "password": replacement}
                    ).status_code
                    == 200
                )
                lab = mutation(
                    client, "POST", "/api/v1/labs", {"name": "Persistent Demo Lab", "location": "Synthetic"}
                ).json()["id"]
                sut = mutation(
                    client,
                    "POST",
                    "/api/v1/suts",
                    {"lab_id": lab, "name": "Persistent Demo SUT", "platform": "Demo", "owner_team": "Demo"},
                ).json()["id"]
                assert client.get("/").status_code == 200
                assert (
                    mutation(
                        client,
                        "PATCH",
                        f"/api/v1/suts/{sut}/operational-state",
                        {"state": "maintenance", "reason": "Synthetic persistence check"},
                    ).status_code
                    == 200
                )
                run("down")  # Deliberately retain the volume across rebuild/recreation.
                run("up", "-d", "--build", "--force-recreate")
                ready()
                response = client.get(f"/api/v1/suts/{sut}")
                assert response.status_code == 200, response.text
                assert response.json()["operational_reason"] == "Synthetic persistence check"
                assert "Persistent Demo SUT" in client.get("/").text
                run("exec", "-T", "sut-management", "alembic", "upgrade", "head")
                run("exec", "-T", "sut-management", "alembic", "check")
                check = run(
                    "exec",
                    "-T",
                    "sut-management",
                    "python",
                    "-c",
                    "import os,sqlite3; assert os.getuid()==10001; c=sqlite3.connect('/app/data/sut.db'); assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'; print('Non-root runtime and database integrity: OK')",
                    capture=True,
                )
                print(check.stdout.strip())
                from container_day2 import check_coordination

                check_coordination(client, mutation, run, ready, lab)
                check_published_browser(replacement)
                from container_day3 import check_restore

                check_restore(client, run, ready, compose, environment, working_directory, temp, project)
            if remote_ref:
                print(
                    f"Remote-context deployment verified at {remote_ref} with only Compose/settings in working directory"
                )
            print(
                "PASS: Compose build, migrations, Host 5088 -> Container 80 health/login, authenticated inventory, named-volume and session persistence across down/rebuild/recreate"
            )
        finally:
            # Only the random isolated test project is removed, never deployment volumes.
            subprocess.run(
                [*compose, "down", "-v"],
                cwd=working_directory,
                env=environment,
                check=False,
                stdout=subprocess.DEVNULL,
            )


if __name__ == "__main__":
    main()
