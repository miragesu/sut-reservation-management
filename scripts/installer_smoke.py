"""Exercise installer lifecycle with a locally tested image and disposable host paths.

Mount preflight, registry selection and network download are simulated here; their
failure/confirmation/checksum contracts are covered by test_installer.py. No /data,
real registry tag, production project or persistent user configuration is touched.
"""

import os
from pathlib import Path
import secrets
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    image = os.environ["SUT_INSTALLER_TEST_IMAGE"]
    project = "sut-installer-" + secrets.token_hex(5)
    with tempfile.TemporaryDirectory(prefix="sut-installer-") as directory:
        base = Path(directory)
        install = base / "installation"
        install.mkdir(mode=0o700)
        data = base / "data"
        data.mkdir()
        harness = base / "harness.sh"
        harness.write_text("""source "$TEST_ROOT/setup.sh"
INSTALL_DIR="$TEST_INSTALL"
DATA_ROOT="$TEST_DATA"
DATA_DIR="$TEST_DATA/db"
PROJECT_NAME="$TEST_PROJECT"
preflight() { :; }
probe_tag() { return 0; }
resolve_image() { TARGET_IMAGE="$TEST_IMAGE"; IMAGE_VERSION=1.0.1; }
as_root() {
    docker run --rm --user 0 --entrypoint "$1" \\
        --mount "type=bind,src=$TEST_BASE,dst=$TEST_BASE" "$TEST_IMAGE" "${@:2}"
}
# Cloud's sandbox sees daemon-owned UID10001 as overflow UID65534. Read only
# test-data metadata in daemon namespace, simulating an ordinary rootful host.
stat() {
    if [[ "${@: -1}" == "$DATA_DIR" ]]; then
        docker run --rm --user 0 --entrypoint stat --mount "type=bind,src=$TEST_BASE,dst=$TEST_BASE" "$TEST_IMAGE" "$@"
    else
        command stat "$@"
    fi
}
# Keep real checksum verification; stand in only for network transport.
curl() { cp "$TEST_ROOT/compose.deploy.yaml" "${@: -1}"; }
eval "$(declare -f download_compose | sed '1s/download_compose/download_original/')"
download_compose() {
    download_original
    sed -i "s|/data/sut-reservation-data|$DATA_DIR|" "$INSTALL_DIR/compose.deploy.yaml"
}
eval "$(declare -f compose | sed '1s/compose/compose_original/')"
compose() {
    if [[ "$*" == *app.scripts.bootstrap_admin* ]]; then
        shift
        compose_original exec -T -e BOOTSTRAP_USERNAME -e BOOTSTRAP_DISPLAY_NAME -e BOOTSTRAP_TEAM -e BOOTSTRAP_EMAIL -e BOOTSTRAP_PASSWORD "$@"
    else
        compose_original "$@"
    fi
}
main "$@"
""")
        env = {
            **os.environ,
            "TEST_ROOT": str(ROOT),
            "TEST_INSTALL": str(install),
            "TEST_DATA": str(data),
            "TEST_BASE": directory,
            "TEST_PROJECT": project,
            "TEST_IMAGE": image,
            "BOOTSTRAP_USERNAME": "synthetic",
            "BOOTSTRAP_DISPLAY_NAME": "Synthetic Admin",
            "BOOTSTRAP_TEAM": "Demo",
            "BOOTSTRAP_EMAIL": "synthetic@example.com",
            "BOOTSTRAP_PASSWORD": "甲",
        }
        command = [
            "docker",
            "compose",
            "--env-file",
            str(install / ".env"),
            "-p",
            project,
            "-f",
            str(install / "compose.deploy.yaml"),
            "-f",
            str(install / "image.lock.yaml"),
        ]
        output = ""

        def run(args, answers):
            nonlocal output
            result = subprocess.run(
                ["bash", str(harness), *args], input=answers, env=env, text=True, capture_output=True
            )
            output += result.stdout + result.stderr
            if result.returncode:
                raise RuntimeError("Isolated installer lifecycle failed; see private failure log")
            print("Installer lifecycle stage passed:", args or "fresh/rerun")

        try:
            run([], "1.0.1\n127.0.0.1\ny\ny\ny\ny\n")
            config = (install / ".env").read_bytes()
            assert b"LOW_SECURITY_PASSWD=true" in config
            assert (install / ".env").stat().st_mode & 0o777 == 0o600
            secret = next(
                line.split(b"=", 1)[1] for line in config.splitlines() if line.startswith(b"SECRET_KEY=")
            )
            assert secret.decode() not in output
            # Add deterministic retained records without production data.
            subprocess.run(
                [
                    *command,
                    "exec",
                    "-T",
                    "sut-management",
                    "python",
                    "-c",
                    'import sqlite3; d=sqlite3.connect("/app/data/sut.db"); d.execute("insert into labs(name,location,description,created_at) values (?,?,?,?)",("Synthetic Taiwan","Demo", "Synthetic fixture", "2026-10-15 00:00:00.000000")); d.commit()',
                ],
                env=env,
                check=True,
            )
            run([], "y\ny\n")  # Rerun confirms same image and matching reviewed file.
            assert (install / ".env").read_bytes() == config
            run(["--upgrade", "1.0.1"], "y\ny\n")
            assert (install / ".env").read_bytes() == config
            assert (install / ".env.previous").read_bytes() == config
            assert "Super Admin already exists" in output
            assert "Users, Labs, SUTs, Reservations and Usage History preserved" in output
            assert secret.decode() not in output
            assert "甲" not in output
            assert "Database integrity: OK" in output
            subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--user",
                    "0",
                    "--entrypoint",
                    "sh",
                    "--mount",
                    f"type=bind,src={data},dst=/check",
                    image,
                    "-c",
                    'set -- /check/sut-backups/pre-upgrade-*.tar; test -f "$1"; tar -tf "$1" >/dev/null',
                ],
                check=True,
            )
            print(
                "PASS: actual installer fresh deployment, low-mode bootstrap, rerun, cold-backup upgrade, "
                "config/secret/admin/Lab preservation, image-only startup, health/migrations/5088:80/bind integrity; no secret output"
            )
        except BaseException:
            # Private log stays outside Git; it should never contain config values.
            log = Path("/tmp/dep009-installer-failure.log")
            log.write_text(output)
            log.chmod(0o600)
            raise
        finally:
            if (install / "image.lock.yaml").exists():
                subprocess.run([*command, "down"], env=env, capture_output=True, check=False)
            subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--user",
                    "0",
                    "--entrypoint",
                    "sh",
                    "--mount",
                    f"type=bind,src={data},dst=/cleanup",
                    image,
                    "-c",
                    "rm -rf /cleanup/* /cleanup/.[!.]* /cleanup/..?*; chmod 777 /cleanup",
                ],
                check=True,
            )


if __name__ == "__main__":
    main()
