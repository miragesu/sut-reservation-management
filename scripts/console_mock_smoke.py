"""Disposable internal-network OpenSSH/tmux verification. No published ports/images.

Build app first as sut-console001-c:local; supply SUT_BUILD_CA for proxy TLS.
Only resources created by this invocation are removed, including fixture keys.
"""

import json
import os
from pathlib import Path
import secrets
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def docker(*args, data=None):
    result = subprocess.run(
        ["docker", "--host=unix:///var/run/docker.sock", *args],
        input=data,
        text=True,
        capture_output=True,
        cwd=ROOT,
    )
    if result.returncode:
        # Docker diagnostics might contain fixture input. Never echo stdin or environment.
        raise RuntimeError(f"docker {args[0]} failed ({result.returncode}): {result.stderr[-2000:]}")
    return result.stdout


def main():
    name = "console-c-" + secrets.token_hex(5)
    containers = []
    volumes = []
    try:
        build = ["build", "-f", "tests/console_mock/Dockerfile", "-t", "sut-console001-c-mock:local"]
        if os.getenv("SUT_BUILD_CA"):
            build += ["--secret", "id=build_ca,src=" + os.environ["SUT_BUILD_CA"]]
        docker(*build, ".")
        docker("network", "create", "--internal", name)
        mock = name + "-ssh"
        containers.append(mock)
        docker("run", "-d", "--name", mock, "--network", name, "sut-console001-c-mock:local")
        for _ in range(100):
            ready = subprocess.run(
                [
                    "docker",
                    "--host=unix:///var/run/docker.sock",
                    "exec",
                    mock,
                    "test",
                    "-f",
                    "/run/mock-ready",
                ],
                capture_output=True,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("disposable mock did not become ready")
        fixture = json.loads(docker("exec", mock, "cat", "/run/mock.json"))
        fixture["host"] = docker(
            "inspect", "--format", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", mock
        ).strip()
        client = name + "-probe"
        containers.append(client)
        output = docker(
            "run",
            "--rm",
            "-i",
            "--name",
            client,
            "--network",
            name,
            "--user",
            "10002:10002",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "-e",
            "PYTHONPATH=/app",
            "--entrypoint",
            "python",
            "sut-console001-c-mock:local",
            "/mock/transport_check.py",
            data=json.dumps(fixture),
        )
        print(output, end="")
        # Separate custody: Broker never receives the DB mount; Gateway never receives KEK.
        for kind in ("ipc", "keys", "db"):
            volumes.append(name + "-" + kind)
            docker("volume", "create", volumes[-1])
        mounts = [
            "--mount",
            "type=volume,src=" + volumes[0] + ",dst=/ipc",
            "--mount",
            "type=volume,src=" + volumes[1] + ",dst=/keys",
            "--mount",
            "type=volume,src=" + volumes[2] + ",dst=/db",
        ]
        docker(
            "run",
            "--rm",
            "--user",
            "0:0",
            *mounts,
            "--entrypoint",
            "python",
            "sut-console001-c-mock:local",
            "/mock/provision.py",
        )
        broker = name + "-broker"
        containers.append(broker)
        broker_mounts = mounts[:4]
        docker(
            "run",
            "-d",
            "--name",
            broker,
            "--network",
            name,
            "--user",
            "10002:10002",
            "--group-add",
            "10001",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            *broker_mounts,
            "--entrypoint",
            "python",
            "sut-console001-c-mock:local",
            "-m",
            "app.console_broker",
            "--socket",
            "/ipc/broker.sock",
            "--ipc-key",
            "/ipc/auth",
            "--keyring",
            "/keys/keyring",
        )
        for _ in range(50):
            result = subprocess.run(
                [
                    "docker",
                    "--host=unix:///var/run/docker.sock",
                    "exec",
                    broker,
                    "test",
                    "-S",
                    "/ipc/broker.sock",
                ],
                capture_output=True,
            )
            if result.returncode == 0:
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("non-root private Broker did not start")
        assert (
            docker(
                "exec", broker, "python", "-c", "from pathlib import Path; print(Path('/db/marker').exists())"
            ).strip()
            == "False"
        )
        web_mounts = [
            "--mount",
            "type=volume,src=" + volumes[0] + ",dst=/ipc,readonly",
            "--mount",
            "type=volume,src=" + volumes[2] + ",dst=/db",
        ]
        print(
            docker(
                "run",
                "--rm",
                "-i",
                "--network",
                name,
                "--user",
                "10001:10001",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
                *web_mounts,
                "-e",
                "PYTHONPATH=/app",
                "--entrypoint",
                "python",
                "sut-console001-c-mock:local",
                "/mock/broker_check.py",
                data=json.dumps(fixture),
            ),
            end="",
        )
        print(
            docker(
                "run",
                "--rm",
                "-i",
                "--network",
                name,
                "--user",
                "10001:10001",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
                *web_mounts,
                "-e",
                "PYTHONPATH=/app",
                "--entrypoint",
                "python",
                "sut-console001-c-mock:local",
                "/mock/gateway_check.py",
                data=json.dumps(fixture),
            ),
            end="",
        )
        docker("kill", "--signal=KILL", broker)
        docker("start", broker)
        time.sleep(0.5)
        print(
            docker(
                "run",
                "--rm",
                "-i",
                "--network",
                name,
                "--user",
                "10001:10001",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
                *web_mounts,
                "-e",
                "PYTHONPATH=/app",
                "--entrypoint",
                "python",
                "sut-console001-c-mock:local",
                "/mock/broker_check.py",
                data=json.dumps(fixture),
            ),
            end="",
        )
        print("PASS: SIGKILL/restart recovers owned stale socket; fresh explicit IPC/SSH succeeds")
        sessions = docker(
            "exec",
            mock,
            "runuser",
            "-u",
            "mockconsole",
            "--",
            "tmux",
            "list-sessions",
            "-F",
            "#{session_name}",
        )
        assert set(sessions.split()) == {"existing", "other"}
        print("PASS: original mock tmux sessions remain; no missing session created")
        print(
            "Versions:",
            docker("exec", mock, "tmux", "-V").strip(),
            docker(
                "exec", mock, "python", "-c", "import asyncssh; print('AsyncSSH', asyncssh.__version__)"
            ).strip(),
        )
        # sshd -V prints to stderr; capture only its known version string.
        version = subprocess.run(
            ["docker", "--host=unix:///var/run/docker.sock", "exec", mock, "/usr/sbin/sshd", "-V"],
            capture_output=True,
            text=True,
        )
        print(version.stderr.strip())
    finally:
        for container in reversed(containers):
            subprocess.run(
                ["docker", "--host=unix:///var/run/docker.sock", "rm", "-f", container], capture_output=True
            )
        for volume in volumes:
            subprocess.run(
                ["docker", "--host=unix:///var/run/docker.sock", "volume", "rm", volume], capture_output=True
            )
        subprocess.run(
            ["docker", "--host=unix:///var/run/docker.sock", "network", "rm", name], capture_output=True
        )


if __name__ == "__main__":
    main()
