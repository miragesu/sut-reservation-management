"""Fresh disposable volumes only; never used by operator deployment."""

import base64
import json
import os
from pathlib import Path

for directory, uid, gid, mode in (
    ("/ipc", 10002, 10001, 0o2750),
    ("/keys", 10002, 10002, 0o700),
    ("/db", 10001, 10001, 0o700),
):
    os.chown(directory, uid, gid)
    os.chmod(directory, mode)
Path("/ipc/auth").write_bytes(os.urandom(32))
os.chown("/ipc/auth", 10002, 10001)
os.chmod("/ipc/auth", 0o640)
Path("/keys/keyring").write_text(
    json.dumps({"active_key_id": "fixture", "keys": {"fixture": base64.b64encode(os.urandom(32)).decode()}})
)
os.chown("/keys/keyring", 10002, 10002)
os.chmod("/keys/keyring", 0o600)
Path("/db/marker").write_bytes(b"synthetic database mount custody marker")
os.chown("/db/marker", 10001, 10001)
os.chmod("/db/marker", 0o600)
