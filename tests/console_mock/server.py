"""Disposable server ONLY. Never point this fixture at a production host."""

import json
import os
from pathlib import Path
import secrets
import subprocess
import socket
import threading
import time

import asyncssh

password = secrets.token_urlsafe(32)
key = asyncssh.generate_private_key("ssh-ed25519")
passphrase = secrets.token_urlsafe(24)
subprocess.run(["chpasswd"], input=f"mockconsole:{password}\n", text=True, check=True)
sshdir = Path("/home/mockconsole/.ssh")
sshdir.mkdir(mode=0o700)
(sshdir / "authorized_keys").write_bytes(key.export_public_key())
os.chown(sshdir, 11000, 11000)
os.chown(sshdir / "authorized_keys", 11000, 11000)
(sshdir / "authorized_keys").chmod(0o600)
Path("/run/sshd").mkdir(exist_ok=True)
subprocess.run(["ssh-keygen", "-A"], check=True, stdout=subprocess.DEVNULL)
config = """Port 22
ListenAddress 0.0.0.0
HostKey /etc/ssh/ssh_host_ed25519_key
PasswordAuthentication yes
PubkeyAuthentication yes
PermitRootLogin no
KbdInteractiveAuthentication no
UsePAM no
AllowUsers mockconsole
DisableForwarding yes
X11Forwarding no
PermitUserEnvironment no
PrintMotd no
LogLevel ERROR
PidFile /run/mock-sshd.pid
"""
Path("/run/sshd_config").write_text(config)
for name in ("existing", "other"):
    subprocess.run(
        [
            "runuser",
            "-u",
            "mockconsole",
            "--",
            "tmux",
            "new-session",
            "-d",
            "-s",
            name,
            "python /mock/uart.py",
        ],
        check=True,
    )
record = {
    "username": "mockconsole",
    "password": password,
    "private_key": key.export_private_key("openssh", passphrase=passphrase).decode(),
    "passphrase": passphrase,
    "public_key": Path("/etc/ssh/ssh_host_ed25519_key.pub").read_text().strip(),
}
Path("/run/mock.json").write_text(json.dumps(record))
Path("/run/mock.json").chmod(0o600)


def blackhole():
    listener = socket.socket()
    listener.bind(("0.0.0.0", 2224))
    listener.listen()
    held = []
    while True:
        held.append(listener.accept()[0])


threading.Thread(target=blackhole, daemon=True).start()
sshd = subprocess.Popen(["/usr/sbin/sshd", "-D", "-e", "-f", "/run/sshd_config"])
Path("/run/mock-ready").touch()
while sshd.poll() is None:
    time.sleep(0.1)
raise SystemExit(sshd.returncode)
