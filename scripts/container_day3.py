"""Cold backup/restore rehearsal using only the smoke project's disposable volumes."""

import json
import subprocess
from pathlib import Path


def check_restore(client, run, ready, compose, environment, cwd, temp, project):
    image = run("images", "-q", "sut-management", capture=True).stdout.strip()
    container = run("ps", "-q", "sut-management", capture=True).stdout.strip()
    mounts = json.loads(
        subprocess.check_output(["docker", "inspect", container, "--format", "{{json .Mounts}}"], text=True)
    )
    mount = next(item for item in mounts if item["Destination"] == "/app/data")
    source = mount["Name"] if mount["Type"] == "volume" else mount["Source"]
    restored = project + "-restored"
    before = client.get("/api/v1/history").json()
    notices = client.get("/api/v1/notifications").json()
    run("stop")
    # Cold tar backup includes SQLite WAL/SHM if present and preserves UID/GID.
    archive = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--user",
            "0",
            "--entrypoint",
            "tar",
            "-v",
            f"{source}:/app/data:ro",
            image,
            "-C",
            "/app/data",
            "-czf",
            "-",
            ".",
        ],
        capture_output=True,
        check=True,
    ).stdout
    assert len(archive) > 0
    subprocess.run(["docker", "volume", "create", restored], check=True, capture_output=True)
    override = Path(temp) / "restore.json"
    override.write_text(
        json.dumps(
            {
                "services": {"sut-management": {"volumes": ["restored-data:/app/data"]}},
                "volumes": {"restored-data": {"external": True, "name": restored}},
            }
        )
    )
    command = [*compose, "-f", str(override)]
    try:
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-i",
                "--user",
                "0",
                "--entrypoint",
                "tar",
                "-v",
                f"{restored}:/app/data",
                image,
                "-C",
                "/app/data",
                "-xzf",
                "-",
            ],
            input=archive,
            check=True,
        )
        subprocess.run(
            [*command, "up", "-d", "--no-build", "--force-recreate"], cwd=cwd, env=environment, check=True
        )
        ready()
        assert client.get("/api/v1/history").json() == before
        assert client.get("/api/v1/notifications").json() == notices
        run(
            "exec",
            "-T",
            "sut-management",
            "python",
            "-c",
            "import os,sqlite3; assert os.getuid()==10001; db=sqlite3.connect('/app/data/sut.db'); assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'; assert not db.execute('PRAGMA foreign_key_check').fetchall(); print('Restored SQLite integrity and foreign keys: OK')",
        )
        run("exec", "-T", "sut-management", "alembic", "check")
        print(
            "PASS: cold tar backup restored into a separate empty disposable volume; sessions, history, notices, ownership, schema and SQLite integrity preserved"
        )
    finally:
        subprocess.run([*command, "down"], cwd=cwd, env=environment, check=False, stdout=subprocess.DEVNULL)
        subprocess.run(["docker", "volume", "rm", restored], check=True, capture_output=True)


def check_image_contract(image):
    exposed = json.loads(
        subprocess.check_output(
            ["docker", "image", "inspect", image, "--format", "{{json .Config.ExposedPorts}}"], text=True
        )
    )
    health = json.loads(
        subprocess.check_output(
            ["docker", "image", "inspect", image, "--format", "{{json .Config.Healthcheck.Test}}"], text=True
        )
    )
    assert exposed == {"80/tcp": {}}
    assert health[0] == "CMD" and "http://127.0.0.1:80/health" in health[-1]
    print("DEP-006 image metadata: EXPOSE 80 and healthcheck :80 verified")
    return health[1:]


def check_port_contract(run):
    """Assert actual publishing, PID 1 privileges, namespace setting and listener."""
    image = run("images", "-q", "sut-management", capture=True).stdout.strip()
    health = check_image_contract(image)
    run("exec", "-T", "sut-management", *health)
    assert run("port", "sut-management", "80", capture=True).stdout.strip() == "127.0.0.1:5088"
    result = run(
        "exec",
        "-T",
        "sut-management",
        "python",
        "-c",
        """
from pathlib import Path
import socket
import urllib.request
status = dict(line.split(':', 1) for line in Path('/proc/1/status').read_text().splitlines() if ':' in line)
assert status['Uid'].split() == ['10001'] * 4
for key in ('CapEff', 'CapPrm', 'CapBnd'):
    assert int(status[key].strip(), 16) == 0, key
assert status['NoNewPrivs'].strip() == '1'
assert Path('/proc/sys/net/ipv4/ip_unprivileged_port_start').read_text().strip() == '80'
listeners = [line.split() for line in Path('/proc/net/tcp').read_text().splitlines()[1:]]
assert any(row[1] == '00000000:0050' and row[3] == '0A' for row in listeners)
assert not any(row[1].endswith(':1F40') and row[3] == '0A' for row in listeners)
assert urllib.request.urlopen('http://127.0.0.1:80/health', timeout=3).status == 200
with socket.socket() as probe:
    try:
        probe.bind(('127.0.0.1', 79))
    except PermissionError:
        pass
    else:
        raise AssertionError('Port 79 must remain privileged for the non-root process')
print('DEP-006: PID 1 UID 10001, zero capabilities, NoNewPrivs=1, namespace threshold 80, 0.0.0.0:80 listener/health, port 79 denied')
""",
        capture=True,
    )
    print(result.stdout.strip())
    print("PASS: actual Host 5088 -> Container 80 publishing and least-privilege binding")


def check_published_browser(password):
    """Actual Chromium login/UI through host 5088 into the container's port 80."""
    import os
    import shutil
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        executable = os.environ.get("CHROMIUM_PATH") or shutil.which("chromium")
        browser = playwright.chromium.launch(**({"executable_path": executable} if executable else {}))
        try:
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto("http://127.0.0.1:5088/login")
            page.get_by_label("Username", exact=True).fill("demo")
            page.get_by_label("Password", exact=True).fill(password)
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(page.get_by_role("heading", name="Your SUTs, at a glance.", exact=True)).to_be_visible()
            page.get_by_role("button", name="Table", exact=True).click()
            page.locator('.table-layout [data-quick-action="detail"]').first.click()
            expect(page.locator("#quick-modal")).to_be_visible()
            expect(page.locator("#quick-detail")).to_contain_text("Queue")
            page.keyboard.press("Escape")
            expect(page.locator("#quick-modal")).not_to_be_visible()
            page.get_by_role("link", name="My SUTs", exact=True).click()
            expect(page.get_by_role("heading", name="My SUTs", exact=True)).to_be_visible()
            assert errors == [], errors
        finally:
            browser.close()
    print("PASS: Chromium login, Dashboard/Table/Detail modal and My SUTs via Host 5088 -> Container 80")
