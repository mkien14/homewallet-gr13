"""Per-process cached readiness; no external API or Redis dependency."""
import threading
import time

from .db import connect


class Readiness:
    def __init__(self):
        self._lock = threading.Lock()
        self._expires = 0.0
        self._ok = False

    def check(self, config):
        if time.monotonic() < self._expires:
            return self._ok
        # Concurrent requests fail closed instead of queueing more DB probes.
        if not self._lock.acquire(blocking=False):
            return False
        try:
            if time.monotonic() < self._expires:
                return self._ok
            db = None
            try:
                db = connect(config, probe=True)
                with db.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
                self._ok = True
            except Exception:
                # Do not expose credentials, SQL errors or hostnames to callers.
                self._ok = False
            finally:
                if db is not None:
                    try:
                        db.close()
                    except Exception:
                        self._ok = False
            self._expires = time.monotonic() + 10
            return self._ok
        finally:
            self._lock.release()
