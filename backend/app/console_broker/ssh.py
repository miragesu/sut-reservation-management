"""Pinned SSH primitives and fixed UART startup; no arbitrary command API."""

import asyncio
import hmac
import logging
import re
import secrets
import shlex
import socket

import asyncssh

from app.console_broker.ipc import BrokerError
from app.services.console.targets import validate_ipv4

# Prevent third-party SSH debug/auth/banner logging, even when root logging is DEBUG.
logging.getLogger("asyncssh").setLevel(logging.CRITICAL)
logging.getLogger("asyncssh").propagate = False
KEX = [
    "curve25519-sha256",
    "curve25519-sha256@libssh.org",
    "ecdh-sha2-nistp256",
    "diffie-hellman-group16-sha512",
    "diffie-hellman-group14-sha256",
]
HOST_KEYS = ["ssh-ed25519", "ecdsa-sha2-nistp256", "rsa-sha2-512", "rsa-sha2-256"]


class Pin(asyncssh.SSHClient):
    def __init__(self, host, port, expected):
        self.host, self.port, self.expected = host, port, expected
        self.observed = None
        self.verified = False

    def validate_host_public_key(self, host, addr, port, key):
        self.observed = key.export_public_key("openssh").decode().strip()
        self.verified = bool(
            self.expected
            and addr == self.host
            and port == self.port
            and hmac.compare_digest(self.observed, self.expected)
        )
        return self.verified  # discovery ALWAYS rejects before user authentication


def fixed_uart_command(name, readonly=False):
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_-]{0,63}", name):
        raise BrokerError("input_invalid")
    target = "=" + name
    marker = "__CONSOLE_READY_" + secrets.token_hex(16) + "__"
    lookup = shlex.join(["tmux", "-N", "has-session", "-t", target])
    attach = ["tmux", "-N", "attach-session"] + (["-r"] if readonly else []) + ["-t", target]
    # No dotfile/server/session/window changes. Lookup and exact attach only.
    command = (
        f'{lookup} || exit 44; printf "{marker}"; '
        f'if {shlex.join(attach)}; then exec "$SHELL" -i; else exit 44; fi'
    )
    return command, marker.encode()


class SSHTransport:
    def __init__(self, *, sensitive=()):
        self.sensitive = tuple(sensitive)

    def target(self, host, port, transport):
        try:
            validate_ipv4(host, bmc=transport == "bmc", sensitive=self.sensitive)
            if type(port) is not int or not 1 <= port <= 65535 or transport == "bmc" and port != 22:
                raise ValueError()
        except Exception:
            raise BrokerError("target_denied") from None

    @staticmethod
    def options():
        return dict(
            config=None,
            known_hosts=([], [], []),
            family=socket.AF_INET,
            tunnel=None,
            proxy_command=None,
            agent_path=None,
            agent_forwarding=False,
            gss_auth=False,
            gss_kex=False,
            host_based_auth=False,
            kbdint_auth=False,
            x509_trusted_certs=[],
            x509_trusted_cert_paths=[],
            kex_algs=KEX,
            server_host_key_algs=HOST_KEYS,
            encryption_algs=[
                "chacha20-poly1305@openssh.com",
                "aes256-gcm@openssh.com",
                "aes128-gcm@openssh.com",
                "aes256-ctr",
                "aes128-ctr",
            ],
            mac_algs=["hmac-sha2-512-etm@openssh.com", "hmac-sha2-256-etm@openssh.com"],
        )

    async def probe(self, host, port, transport):
        self.target(host, port, transport)
        pin = Pin(host, port, None)
        connection = None
        try:
            async with asyncio.timeout(10):
                connection = await asyncssh.connect(
                    host,
                    port,
                    client_factory=lambda: pin,
                    username="",
                    password=None,
                    client_keys=[],
                    public_key_auth=False,
                    password_auth=False,
                    preferred_auth=[],
                    **self.options(),
                )
        except asyncssh.HostKeyNotVerifiable:
            if pin.observed:
                key = asyncssh.import_public_key(pin.observed)
                return {
                    "public_key": pin.observed,
                    "algorithm": key.get_algorithm(),
                    "fingerprint": key.get_fingerprint("sha256"),
                }
            raise BrokerError("host_key_unknown") from None
        except TimeoutError:
            raise BrokerError("ssh_timeout") from None
        except (asyncssh.Error, OSError):
            raise BrokerError("ssh_unavailable") from None
        finally:
            if connection:
                connection.close()
                await connection.wait_closed()
        raise BrokerError("host_key_unknown")

    async def authenticate(self, target, credential):
        host, port, transport = target["host"], target["port"], target["transport"]
        self.target(host, port, transport)
        pin_value = target.get("public_key")
        if not pin_value:
            raise BrokerError("host_key_unknown")
        pin = Pin(host, port, pin_value)
        method = credential.get("method", "password")
        username, secret = credential.get("username", ""), credential.get("secret", "")
        if (
            not isinstance(username, str)
            or not 1 <= len(username.encode()) <= 256
            or not isinstance(secret, str)
            or not secret
            or len(secret.encode()) > (1024 if method == "password" else 65536)
        ):
            raise BrokerError("credential_invalid")
        try:
            keys = (
                [asyncssh.import_private_key(secret, passphrase=credential.get("passphrase"))]
                if method == "private_key"
                else []
            )
            connection = await asyncssh.connect(
                host,
                port,
                client_factory=lambda: pin,
                username=username,
                password=secret if method == "password" else None,
                client_keys=keys,
                public_key_auth=method == "private_key",
                password_auth=method == "password",
                preferred_auth=["publickey"] if method == "private_key" else ["password"],
                **self.options(),
            )
            if not pin.verified or connection.get_extra_info("peername")[0] != host:
                connection.close()
                await connection.wait_closed()
                raise BrokerError("host_key_changed")
            return connection
        except asyncssh.HostKeyNotVerifiable:
            raise BrokerError("host_key_changed") from None
        except asyncssh.PermissionDenied:
            raise BrokerError("credential_auth_failed") from None
        except (asyncssh.KeyImportError, ValueError, TypeError):
            raise BrokerError("credential_invalid") from None
        except (asyncssh.Error, OSError):
            raise BrokerError("ssh_unavailable") from None
        finally:
            credential.clear()  # no password retained for automatic retry
            secret, username = None, None

    async def open(self, target, credential, *, cols, rows, readonly=False):
        connection = None
        try:
            async with asyncio.timeout(10):
                connection = await self.authenticate(target, credential)
                arguments = dict(
                    term_type="xterm-256color",
                    term_size=(cols, rows),
                    encoding=None,
                    x11_forwarding=False,
                    stderr=asyncssh.STDOUT,
                )
                marker = None
                if target["transport"] == "uart":
                    command, marker = fixed_uart_command(target["tmux_session"], readonly)
                    arguments["command"] = command
                process = await connection.create_process(**arguments)
                initial = b""
                if marker:
                    while marker not in initial and len(initial) <= 65536:
                        chunk = await process.stdout.read(8192)
                        if not chunk:
                            await process.wait_closed()
                            raise BrokerError(
                                "tmux_not_found" if process.exit_status == 44 else "ssh_unavailable"
                            )
                        initial += chunk
                    if marker not in initial:
                        raise BrokerError("ssh_unavailable")
                    initial = initial.split(marker, 1)[1]
                return connection, process, initial
        except TimeoutError:
            if connection:
                connection.close()
            raise BrokerError("ssh_timeout") from None
        except BaseException:
            if connection:
                connection.close()
            raise
        finally:
            credential.clear()
