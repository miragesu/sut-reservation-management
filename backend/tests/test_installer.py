"""Execute the real Bash functions with isolated files and external-command doubles."""

import hashlib
import os
from pathlib import Path
import re
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "setup.sh"


def bash(tmp_path, code, stdin="", success=True):
    prolog = f'source "{SCRIPT}"\nINSTALL_DIR="{tmp_path}"\nDATA_ROOT="{tmp_path}/data-root"\nDATA_DIR="$DATA_ROOT/db"\n'
    result = subprocess.run(
        ["bash", "-c", prolog + code],
        input=stdin,
        text=True,
        capture_output=True,
        env={**os.environ, "SHELLOPTS": ""},
    )
    if success:
        assert result.returncode == 0, result.stderr + result.stdout
    else:
        assert result.returncode != 0, result.stdout
    return result


@pytest.mark.parametrize("version", ["stable", "latest", "1.0.0", "1.0.1"])
def test_versions_available(tmp_path, version):
    bash(
        tmp_path,
        f'SELECTED_VERSION={version}; probe_tag() {{ return 0; }}; select_version; [[ "$SELECTED_VERSION" == {version} ]]',
    )


@pytest.mark.parametrize("version", ["../main", "1.0", "v1.0.1", "$(id)", "1.0.01", "1.0.1;echo unsafe"])
def test_invalid_version(tmp_path, version):
    import shlex

    bash(tmp_path, f"SELECTED_VERSION={shlex.quote(version)}; select_version", success=False)


@pytest.mark.parametrize("preferred", ["stable", "latest"])
@pytest.mark.parametrize("answer,accepted", [("y\n", True), ("\n", False), ("no\n", False)])
def test_missing_alias_requires_explicit_fallback_confirmation(tmp_path, preferred, answer, accepted):
    result = bash(
        tmp_path,
        f"""SELECTED_VERSION={preferred}
probe_tag() {{ if [[ "$1" == 1.0.0 ]]; then return 0; else return 10; fi; }}
select_version
[[ "$SELECTED_VERSION" == 1.0.0 ]]
""",
        answer,
        success=accepted,
    )
    assert "Available verified fallback: 1.0.0" in result.stdout


def test_no_fallback_for_explicit_or_network_failure(tmp_path):
    for version, error in [("1.0.1", 10), ("stable", 1)]:
        r = bash(
            tmp_path,
            f"SELECTED_VERSION={version}; probe_tag() {{ return {error}; }}; select_version",
            "y\n",
            success=False,
        )
        assert "Available verified fallback" not in r.stdout


@pytest.mark.parametrize(
    "message,status",
    [
        ("manifest unknown", 10),
        ("no such manifest", 10),
        ("TLS error", 1),
        ("unauthorized", 1),
        ("toomanyrequests", 1),
    ],
)
def test_registry_probe_distinguishes_missing_from_errors(tmp_path, message, status):
    r = bash(
        tmp_path,
        f"""docker() {{ echo '{message}' >&2; return 1; }}
set +e
probe_tag stable
result=$?
[[ "$result" == {status} ]]
""",
    )
    assert "TLS error" not in r.stdout


@pytest.mark.parametrize(
    "failure", ["os", "arch", "daemon", "compose", "missing-data", "unmounted", "disk", "port"]
)
def test_preflight_failures_stop(tmp_path, failure):
    (tmp_path / "data-root").mkdir()
    mocks = """
uname() { if [[ "$1" == -s ]]; then echo Linux; else echo x86_64; fi; }
docker() { if [[ "$1" == info && $# == 1 ]]; then return 0; elif [[ "$1" == info ]]; then echo linux/amd64; else echo 2.40.3; fi; }
findmnt() { if [[ "$*" == *'-o TARGET'* ]]; then echo "$DATA_ROOT"; fi; }
df() { printf 'Filesystem 1024-blocks Used Available Capacity Mounted on\ntest 9000000 1 8000000 1%% /data\n'; }
ss() { :; }
confirm() { return 0; }
command() { if [[ "$1" == -v ]]; then return 0; else builtin command "$@"; fi; }
"""
    overrides = {
        "os": "uname() { echo Darwin; }",
        "arch": 'uname() { if [[ "$1" == -s ]]; then echo Linux; else echo aarch64; fi; }',
        "daemon": "docker() { return 1; }",
        "compose": 'docker() { if [[ "$1" == info ]]; then [[ $# == 1 ]] || echo linux/amd64; else echo 1.29.0; fi; }',
        "missing-data": 'rmdir "$DATA_ROOT"',
        "unmounted": "findmnt() { return 1; }",
        "disk": "df() { printf 'header\\ntest 10 9 1 99%% /data\\n'; }",
        "port": "ss() { echo 'LISTEN 5088'; }",
    }
    bash(tmp_path, mocks + overrides[failure] + "\npreflight\necho SHOULD_NOT_REACH", success=False)


def test_private_configuration_generation_and_preservation(tmp_path):
    bash(
        tmp_path,
        """SELECTED_VERSION=1.0.1; IMAGE_VERSION=1.0.1
ip() { echo '1: eth0 inet 127.0.0.1/8'; }
initialize_config
""",
        "127.0.0.1\n\ny\n",
    )
    config = (tmp_path / ".env").read_bytes()
    assert b"LOW_SECURITY_PASSWD=false" in config
    assert len(re.search(rb"SECRET_KEY=(\w+)", config)[1]) == 96
    assert (tmp_path / ".env").stat().st_mode & 0o777 == 0o600
    r = bash(tmp_path, 'ip() { echo "1: eth0 inet 127.0.0.1/8"; }; load_config; echo loaded')
    assert r.stdout == "loaded\n" and "SECRET_KEY" not in r.stdout + r.stderr
    assert (tmp_path / ".env").read_bytes() == config
    bash(
        tmp_path,
        """SELECTED_VERSION=1.0.1; IMAGE_VERSION=1.0.1
ip() { :; }; initialize_config
""",
        "127.0.0.1\n\ny\n",
        success=False,
    )
    assert (tmp_path / ".env").read_bytes() == config


def test_low_mode_requires_warning_and_second_confirmation(tmp_path):
    for answers in ["127.0.0.1\ny\n\n", "127.0.0.1\ny\ny\n"]:
        r = bash(
            tmp_path,
            """SELECTED_VERSION=1.0.0; IMAGE_VERSION=1.0.0
ip() { :; }; initialize_config
""",
            answers,
            success=False,
        )
        assert "substantially increase" in r.stdout
        assert not (tmp_path / ".env").exists()


def test_existing_data_is_never_chowned_or_recreated(tmp_path):
    d = tmp_path / "data-root" / "db"
    d.mkdir(parents=True)
    (d / "sut.db").write_bytes(b"synthetic unchanged database")
    bash(tmp_path, "as_root() { echo MUTATION >&2; exit 90; }; prepare_data", success=False)
    assert (d / "sut.db").read_bytes() == b"synthetic unchanged database"
    (tmp_path / ".env").write_text("existing")
    d.rename(d.with_name("retained"))
    bash(tmp_path, "as_root() { exit 90; }; prepare_data", success=False)
    assert not d.exists()


def test_compose_download_requires_pinned_content_and_preserves_on_failure(tmp_path):
    content = (ROOT / "compose.deploy.yaml").read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    r = bash(
        tmp_path,
        f'''curl() {{ [[ "$*" == *"$COMPOSE_REF/compose.deploy.yaml"* ]]; cp "{ROOT}/compose.deploy.yaml" "${{@: -1}}"; }}
COMPOSE_SHA256={digest}
download_compose
''',
    )
    assert (tmp_path / "compose.deploy.yaml").read_bytes() == content
    bash(tmp_path, """curl() { printf 'tampered' > "${@: -1}"; }; download_compose""", success=False)
    assert (tmp_path / "compose.deploy.yaml").read_bytes() == content
    assert "SECRET_KEY" not in r.stdout + r.stderr


def test_rerun_uses_lock_without_new_version_resolution_or_bootstrap_reset(tmp_path):
    (tmp_path / ".env").write_text("retained secret sentinel\n")
    (tmp_path / "image.lock.yaml").write_text("retained immutable image\n")
    (tmp_path / "sut.db").write_text("retained data\n")
    tmp_path.chmod(0o700)
    r = bash(
        tmp_path,
        """preflight() { :; }; load_config() { APP_BIND=127.0.0.1; }
confirm() { return 0; }; prepare_data() { :; }; download_compose() { :; }
resolve_image() { exit 90; }; select_version() { exit 91; }
compose() { printf '%s\\n' "$*"; }; verify_deployment() { :; }
bootstrap_if_needed() { echo 'existing admin retained'; }
main
""",
    )
    assert "--no-build --pull never" in r.stdout
    assert (tmp_path / ".env").read_text() == "retained secret sentinel\n"
    assert (tmp_path / "image.lock.yaml").read_text() == "retained immutable image\n"
    assert (tmp_path / "sut.db").read_text() == "retained data\n"


@pytest.mark.parametrize("count,bootstraps", [("1", False), ("0", True)])
def test_bootstrap_only_if_no_super_admin(tmp_path, count, bootstraps):
    r = bash(
        tmp_path,
        f"""compose() {{ if [[ "$*" == *'select count'* ]]; then echo {count}; else echo BOOTSTRAP; fi; }}
bootstrap_if_needed
""",
    )
    assert ("BOOTSTRAP" in r.stdout) is bootstraps


def test_upgrade_orders_backup_before_replacement_and_keeps_secret(tmp_path):
    (tmp_path / ".env").write_text(
        "SECRET_KEY=synthetic-preserved-secret-value-123456789\nSUT_VERSION=1.0.0\n"
    )
    (tmp_path / "image.lock.yaml").write_text("old image")
    tmp_path.chmod(0o700)
    r = bash(
        tmp_path,
        """preflight() { :; }; load_config() { APP_BIND=127.0.0.1; LOW_SECURITY_PASSWD=false; }
confirm() { return 0; }; select_version() { :; }
resolve_image() { TARGET_IMAGE=synthetic-new-image; IMAGE_VERSION=1.0.1; }
prepare_data() { :; }; download_compose() { echo DOWNLOAD; }
backup_existing() { echo BACKUP; printf '{}' > "$INSTALL_DIR/.records-before.json"; }; verify_deployment() { echo VERIFY; }
bootstrap_if_needed() { :; }; compose() { echo "COMPOSE $*"; }; docker() { :; }
main --upgrade 1.0.1
""",
    )
    assert (
        r.stdout.index("BACKUP")
        < r.stdout.index("DOWNLOAD")
        < r.stdout.index("COMPOSE up")
        < r.stdout.index("VERIFY")
    )
    assert "SECRET_KEY=synthetic-preserved-secret-value-123456789" in (tmp_path / ".env").read_text()
    assert "SUT_VERSION=1.0.1" in (tmp_path / ".env").read_text()
    assert "synthetic-preserved-secret" not in r.stdout + r.stderr


def test_bash_syntax_and_pinned_contract():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
    text = SCRIPT.read_text()
    ref = re.search(r"^COMPOSE_REF=(\w+)$", text, re.M)[1]
    assert re.fullmatch("[0-9a-f]{40}", ref)
    data = (ROOT / "compose.deploy.yaml").read_bytes()
    assert hashlib.sha256(data).hexdigest() == re.search(r"^COMPOSE_SHA256=(\w+)$", text, re.M)[1]


def test_backup_snapshot_cannot_consume_next_operator_confirmation(tmp_path):
    data = tmp_path / "data-root" / "db"
    data.mkdir(parents=True)
    (data / "sut.db").write_text("synthetic fixture")
    (tmp_path / ".env").write_text("private config")
    (tmp_path / "image.lock.yaml").write_text("previous immutable image")
    bash(
        tmp_path,
        """as_root() { "$@"; }
compose() {
    if [[ "$1" == run ]]; then
        cat > "$INSTALL_DIR/consumed-input"
        printf '{}'
    fi
}
backup_existing
read -r answer
[[ "$answer" == yes ]]
[[ ! -s "$INSTALL_DIR/consumed-input" ]]
""",
        "yes\n",
    )
