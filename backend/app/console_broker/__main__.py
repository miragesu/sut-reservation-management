"""Explicitly launched private Broker, never auto-started as root by the web app."""

import argparse
import asyncio
import os
from pathlib import Path
import signal

from app.console_broker.executor import Executor
from app.console_broker.ipc import BrokerServer, private_key_file
from app.console_broker.ssh import SSHTransport
from app.services.console.crypto import EnvelopeCipher


async def main(args):
    if os.geteuid() == 0 or os.geteuid() == args.web_uid:
        raise SystemExit("Console Broker requires a separately provisioned non-root UID")
    if policy := os.environ.get("CONSOLE_NETWORK_POLICY_FILE"):
        from app.console_deployment import policy_file

        policy_file(policy)
    cipher = EnvelopeCipher.from_file(args.keyring, login_secret=b"")
    server = BrokerServer(
        args.socket,
        private_key_file(args.ipc_key),
        Executor(cipher, transport=SSHTransport(sensitive=args.deny_ipv4)),
        allowed_uid=args.web_uid,
    )
    await server.start()
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stopped.set)
    try:
        await stopped.wait()
    finally:
        await server.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Private Console SSH Broker; no public listener")
    parser.add_argument("--socket", required=True, type=Path)
    parser.add_argument("--ipc-key", required=True, type=Path)
    parser.add_argument("--keyring", required=True, type=Path)
    parser.add_argument("--web-uid", type=int, default=10001)
    parser.add_argument("--deny-ipv4", action="append", default=[])
    asyncio.run(main(parser.parse_args()))
