import hashlib
import json
import time


class TTLCache:
    def __init__(self, ttl_seconds=300, max_entries=256):
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self.entries = {}

    def get(self, key):
        entry = self.entries.get(key)

        if entry is None:
            return None

        expires_at, answer = entry

        if time.monotonic() >= expires_at:
            del self.entries[key]
            return None

        return answer

    def set(self, key, answer):
        if key not in self.entries and len(self.entries) >= self.max_entries:
            self.entries.pop(next(iter(self.entries)))

        self.entries[key] = (
            time.monotonic() + self.ttl,
            answer,
        )

    def clear(self):
        self.entries.clear()


def build_cache_key(provider, model, parameters):
    payload = {
        "provider": provider,
        "model": model,
        "parameters": parameters,
    }

    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()
