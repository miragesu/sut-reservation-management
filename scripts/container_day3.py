"""Cold backup/restore rehearsal using only the smoke project's disposable volumes."""

import json
import subprocess
from pathlib import Path


def check_restore(client, run, ready, compose, environment, cwd, temp, project):
    image = run("images", "-q", "sut-management", capture=True).stdout.strip()
    source = project + "_sut-data"
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
