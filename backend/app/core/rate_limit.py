import threading
import time
from collections import OrderedDict

from fastapi import HTTPException


class LoginLimiter:
    """Bounded, single-worker IP limit. Never trust arbitrary forwarding headers."""

    def __init__(self):
        self.entries = OrderedDict()
        self.lock = threading.Lock()

    def check(self, request):
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with self.lock:
            hits = [t for t in self.entries.pop(key, []) if now - t < 60]
            if len(hits) >= 20:
                self.entries[key] = hits
                raise HTTPException(
                    429, "Too many sign-in attempts; retry in one minute", headers={"Retry-After": "60"}
                )
            self.entries[key] = hits + [now]
            if len(self.entries) > 10000:
                self.entries.popitem(last=False)
