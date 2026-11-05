"""Versioned envelope encryption; key custody is independent of SQLite/login keys.

No HTTP decrypt/reveal API. Future broker owns this abstraction in Phase C.
"""

import base64
from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import stat

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SecretUnavailable(ValueError):
    def __init__(self):
        super().__init__("Console credential/keyring unavailable")


@dataclass(frozen=True, repr=False)
class Envelope:
    ciphertext: bytes
    nonce: bytes
    wrapped_data_key: bytes
    wrap_nonce: bytes
    key_id: str
    algorithm: str = "AES-256-GCM/v1"
    crypto_revision: int = 1


class EnvelopeCipher:
    def __init__(self, keys, active_id, *, login_secret=None):
        if (
            not keys
            or active_id not in keys
            or any(
                not isinstance(k, str)
                or not k
                or len(k) > 64
                or not isinstance(v, bytes)
                or len(v) != 32
                or v == login_secret
                for k, v in keys.items()
            )
        ):
            raise SecretUnavailable()
        self._keys = dict(keys)
        self.active_id = active_id

    @classmethod
    def from_file(cls, path, *, login_secret):
        try:
            # Reject links, group/world access and nonregular files. Never echo contents.
            fd = os.open(Path(path), os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd) as file:
                info = os.fstat(file.fileno())
                if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
                    raise SecretUnavailable()
                raw = file.read(65537)
            if len(raw) > 65536:
                raise SecretUnavailable()
            data = json.loads(raw)
            keys = {key: base64.b64decode(value, validate=True) for key, value in data["keys"].items()}
            return cls(keys, data["active_key_id"], login_secret=login_secret)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            raise SecretUnavailable() from None

    @staticmethod
    def aad(client_security_id, credential_security_id, method, generation):
        if method not in ("password", "private_key") or generation < 1:
            raise SecretUnavailable()
        return json.dumps(
            [1, client_security_id, credential_security_id, method, generation], separators=(",", ":")
        ).encode()

    def encrypt(self, secret, aad):
        if not isinstance(secret, bytes) or not 1 <= len(secret) <= 131072:
            raise SecretUnavailable()
        data_key, nonce, wrap_nonce = os.urandom(32), os.urandom(12), os.urandom(12)
        return Envelope(
            AESGCM(data_key).encrypt(nonce, secret, aad),
            nonce,
            AESGCM(self._keys[self.active_id]).encrypt(wrap_nonce, data_key, aad),
            wrap_nonce,
            self.active_id,
        )

    def _unwrap(self, envelope, aad):
        if envelope.algorithm != "AES-256-GCM/v1":
            raise SecretUnavailable()
        return AESGCM(self._keys[envelope.key_id]).decrypt(
            envelope.wrap_nonce, envelope.wrapped_data_key, aad
        )

    def decrypt(self, envelope, aad):
        try:
            return AESGCM(self._unwrap(envelope, aad)).decrypt(envelope.nonce, envelope.ciphertext, aad)
        except (InvalidTag, KeyError, ValueError, TypeError):
            raise SecretUnavailable() from None

    def rewrap(self, envelope, aad):
        try:
            data_key = self._unwrap(envelope, aad)
            nonce = os.urandom(12)
            wrapped = AESGCM(self._keys[self.active_id]).encrypt(nonce, data_key, aad)
            return replace(
                envelope,
                key_id=self.active_id,
                wrap_nonce=nonce,
                wrapped_data_key=wrapped,
                crypto_revision=envelope.crypto_revision + 1,
            )
        except (InvalidTag, KeyError, ValueError, TypeError):
            raise SecretUnavailable() from None
