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
        "BOOTSTRAP_USERNAME": "demo",
        "BOOTSTRAP_DISPLAY_NAME": "Synthetic Admin",
        "BOOTSTRAP_TEAM": "Demo",
        "BOOTSTRAP_EMAIL": "demo@example.com",
        "BOOTSTRAP_PASSWORD": password,
    }
    image_ref = os.environ.get("SUT_SMOKE_IMAGE")
    export_ref = os.environ.get("SUT_SMOKE_EXPORT_IMAGE")
    remote_ref = os.environ.get("SUT_SMOKE_REMOTE_REF")
    if image_ref and remote_ref:
        raise ValueError("Select image-only or remote-build smoke, not both")
    if image_ref:
        environment["SUT_IMAGE"] = image_ref
    elif not remote_ref:
        environment["SUT_GIT_REF"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    if remote_ref:
        if not re.fullmatch(r"[0-9a-f]{40}", remote_ref):
            raise ValueError("SUT_SMOKE_REMOTE_REF must be a full commit SHA")
        environment["SUT_GIT_REF"] = remote_ref
    with tempfile.TemporaryDirectory(prefix="sut-compose-") as temp:
        working_directory = Path(temp) if remote_ref or image_ref else ROOT
        compose_name = "compose.deploy.yaml" if image_ref else "compose.yaml"
        if remote_ref or image_ref:
            # Operator directory contains only Compose and host settings, no source.
            shutil.copyfile(ROOT / compose_name, working_directory / compose_name)
        compose = ["docker", "compose", "-p", project, "-f", str(working_directory / compose_name)]
        if not image_ref:
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
            if not remote_ref:
                compose += ["-f", str(ROOT / "compose.local.yaml")]
            compose += ["-f", str(overrides)]
        build_flag = "--no-build" if image_ref else "--build"

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
            if image_ref:
                rendered = json.loads(run("config", "--format", "json", capture=True).stdout)
                assert "build" not in rendered["services"]["sut-management"]
                assert not any(
                    (working_directory / name).exists() for name in ("backend", ".git", "Dockerfile")
                )
                if os.environ.get("SUT_SMOKE_PULL") == "1":
                    run("pull")
            run("up", "-d", build_flag)
            image_id = run("images", "-q", "sut-management", capture=True).stdout.strip()
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
                run("up", "-d", build_flag, "--force-recreate")
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
            if export_ref:
                subprocess.run(["docker", "tag", image_id, export_ref], check=True)
            if image_ref:
                print(
                    f"PASS: image-only deployment of {image_ref}, Compose-only directory, no build/source checkout (registry pull {'verified' if os.environ.get('SUT_SMOKE_PULL') == '1' else 'NOT exercised; locally loaded image'})"
                )
            if remote_ref:
                print(
                    f"Remote-context deployment verified at {remote_ref} with only Compose/settings in working directory"
                )
            print(
                "PASS: Compose deployment, migrations, Host 5088 -> Container 80 health/login, authenticated inventory, named-volume and session persistence across down/recreate"
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
