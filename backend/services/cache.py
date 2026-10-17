from collections import OrderedDict
from time import monotonic

from backend.schemas import SearchResult


class EvidenceCache:
    def __init__(self, ttl_seconds: int, max_entries: int = 64, clock=monotonic):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.clock = clock
        self.entries = OrderedDict()

    def get(self, key: tuple) -> SearchResult | None:
        entry = self.entries.get(key)
        if entry is None:
            return None
        expires, result = entry
        if self.clock() >= expires:
            del self.entries[key]
            return None
        self.entries.move_to_end(key)
        return result.model_copy(deep=True)

    def put(self, key: tuple, result: SearchResult) -> None:
        if not self.ttl_seconds or result.status not in {"ok", "partial"} or not result.evidence:
            return
        self.entries[key] = (self.clock() + self.ttl_seconds, result.model_copy(deep=True))
        self.entries.move_to_end(key)
        while len(self.entries) > self.max_entries:
            self.entries.popitem(last=False)
