"""Offline provisioning, namespace firewall and authenticated deployment preflight.

Never log key material, envelopes or terminal payloads. No production auto-discovery.
"""

import argparse
import asyncio
import base64
from ipaddress import IPv4Address, IPv4Network
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import time

from app.console_broker.ipc import BrokerClient, private_key_file
from app.services.console.crypto import EnvelopeCipher
from app.services.console.targets import local_denials


class DeploymentError(ValueError):
    pass


def policy_file(path):
    try:
        p = Path(path)
        if p.is_symlink() or not p.is_file() or p.stat().st_size > 65536:
            raise ValueError()
        value = json.loads(p.read_text())
        if (
            set(value) != {"version", "host_ipv4", "deny_cidrs", "ssh_ports"}
            or type(value["version"]) is not int
            or value["version"] != 1
        ):
            raise ValueError()
        hosts = value["host_ipv4"]
        denies = value["deny_cidrs"]
        ports = value["ssh_ports"]
        if (
            any(not isinstance(v, list) for v in (hosts, denies, ports))
            or not hosts
            or not denies
            or not ports
            or len(hosts) > 256
            or len(denies) > 256
        ):
            raise ValueError()
        if any(str(IPv4Address(h)) != h for h in hosts):
            raise ValueError()
        if any(str(IPv4Network(n)) != n for n in denies):
            raise ValueError()
        if len(ports) > 64 or any(type(p) is not int or not 1 <= p <= 65535 for p in ports):
            raise ValueError()
        return value
    except (OSError, ValueError, KeyError, TypeError):
        raise DeploymentError("Console network policy missing or invalid") from None


def denies_target(path, address, port=None):
    policy = policy_file(path)
    return (
        address in policy["host_ipv4"]
        or any(IPv4Address(address) in IPv4Network(n) for n in policy["deny_cidrs"])
        or port is not None
        and port not in policy["ssh_ports"]
    )


def provision(root):
    """Explicit one-time action on an empty operator-created bind directory only."""
    root = Path(root)
    if (
        os.geteuid() != 0
        or root.is_symlink()
        or not root.is_dir()
        or root.stat().st_mode & 0o077
        or any(root.iterdir())
    ):
        raise DeploymentError("Provision requires root and an existing empty private directory")
    os.umask(0o077)
    for name, uid, gid, mode in (("ipc", 10002, 10001, 0o2750), ("keys", 10002, 10002, 0o700)):
        path = root / name
        path.mkdir(mode=mode)
        os.chown(path, uid, gid)
        os.chmod(path, mode)
    # IPC capability is separate from the socket directory: Web can read but not replace it.
    auth = root / "ipc-auth"
    auth.write_bytes(os.urandom(32))
    os.chown(auth, 10002, 10001)
    os.chmod(auth, 0o640)
    keyring = root / "keys" / "keyring"
    keyring.write_text(
        json.dumps(
            {"active_key_id": "initial", "keys": {"initial": base64.b64encode(os.urandom(32)).decode()}}
        )
    )
    os.chown(keyring, 10002, 10002)
    os.chmod(keyring, 0o600)
    print("Console custody initialized; back up keyring independently before activation")


def firewall(policy, run=subprocess.run):
    """Only affects this service's private network namespace; never host chains."""
    rules = policy_file(policy)
    # Set default DROP before doing anything fallible; no flush/open-policy interval.
    for family in ("iptables", "ip6tables"):
        run([family, "-w", "-P", "OUTPUT", "DROP"], check=True, capture_output=True)
        run([family, "-w", "-P", "INPUT", "DROP"], check=True, capture_output=True)
        for chain in ("OUTPUT", "INPUT"):
            run([family, "-w", "-F", chain], check=True, capture_output=True)
    commands = [
        ["-A", "INPUT", "-m", "conntrack", "--ctstate", "ESTABLISHED,RELATED", "-j", "ACCEPT"],
        ["-A", "OUTPUT", "-m", "addrtype", "--dst-type", "LOCAL", "-j", "REJECT"],
    ]
    denied = sorted(set(rules["host_ipv4"]) | local_denials())
    denied += rules["deny_cidrs"] + [
        "0.0.0.0/8",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "100.64.0.0/10",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
    ]
    for destination in denied:
        commands.append(["-A", "OUTPUT", "-d", destination, "-j", "REJECT"])
    for port in rules["ssh_ports"]:
        commands.append(["-A", "OUTPUT", "-p", "tcp", "--dport", str(port), "-j", "ACCEPT"])
    for args in commands:
        run(["iptables", "-w", *args], check=True, capture_output=True)


def hold_namespace(policy):
    if os.geteuid() != 0:
        raise DeploymentError("Network initialization requires its isolated NET_ADMIN service")
    firewall(policy)
    os.setgroups([])
    os.setgid(10003)
    os.setuid(10003)  # Linux clears permitted/effective capabilities on this transition.
    Path("/tmp/network-ready").write_text("ready")
    stopped = False

    def stop(*_):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not stopped:
        time.sleep(0.2)


async def preflight():
    if os.environ.get("CONSOLE_ENABLED", "false").lower() == "false":
        return
    from app.core.config import Settings

    settings = Settings()
    if not settings.console_broker_socket or settings.console_keyring_file:
        raise DeploymentError("Deployment requires Broker-only key custody")
    policy_file(os.environ["CONSOLE_NETWORK_POLICY_FILE"])
    if not settings.console_allowed_origins:
        raise DeploymentError("Deployment requires exact allowed origins")
    from app.services.console.foundation import normalize_origin

    for origin in settings.console_allowed_origins:
        normalize_origin(origin, settings)
    bind = IPv4Address(os.environ.get("CONSOLE_DEPLOY_BIND", "127.0.0.1"))
    from app.services.console.targets import PRIVATE

    if not bind.is_loopback and not any(bind in network for network in PRIVATE):
        raise DeploymentError("Console deployment requires a restricted private interface bind")
    if (
        settings.console_allow_insecure_http
        and os.environ.get("CONSOLE_HTTP_RISK_ACK") != "I_ACCEPT_PLAINTEXT_CONSOLE"
    ):
        raise DeploymentError(
            "Explicit plaintext cookie/credential/shell-stream risk acknowledgement required"
        )
    import hashlib

    client = BrokerClient(
        settings.console_broker_socket, private_key_file(settings.console_broker_ipc_key_file)
    )
    await client.call(
        "status", login_key_digest=hashlib.sha256(settings.secret_key.get_secret_value().encode()).hexdigest()
    )

    # Broker never mounts DB. Authorizer passes encrypted envelopes only, before
    # serving traffic; a syntactically valid but wrong/missing retained KEK fails.
    from sqlalchemy.engine import make_url

    database = Path(make_url(settings.database_url).database)
    if database.exists():
        with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            if db.execute(
                "select 1 from sqlite_master where type='table' and name='console_credentials'"
            ).fetchone():
                for row in db.execute("select * from console_credentials"):
                    envelope = {
                        k: row[k]
                        for k in (
                            "ciphertext",
                            "nonce",
                            "wrapped_data_key",
                            "wrap_nonce",
                            "key_id",
                            "algorithm",
                            "crypto_revision",
                        )
                    }
                    for key in ("ciphertext", "nonce", "wrapped_data_key", "wrap_nonce"):
                        envelope[key] = base64.b64encode(envelope[key]).decode()
                    await client.call(
                        "verify_credential",
                        envelope=envelope,
                        aad=[row["client_security_id"], row["security_id"], row["method"], row["generation"]],
                    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("provision", "network", "preflight", "check-keyring"))
    parser.add_argument("--path")
    args = parser.parse_args()
    try:
        if args.operation == "provision":
            provision(args.path)
        elif args.operation == "network":
            hold_namespace(args.path)
        elif args.operation == "check-keyring":
            EnvelopeCipher.from_file(args.path, login_secret=b"")
            print("Keyring syntax and private permissions valid; database compatibility not implied")
        else:
            asyncio.run(preflight())
    except Exception:
        raise SystemExit(
            "Console deployment preflight failed; review private custody/network/approval configuration"
        ) from None


if __name__ == "__main__":
    main()
