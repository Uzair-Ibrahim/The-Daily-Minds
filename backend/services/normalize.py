from datetime import datetime
import math
from urllib.parse import urlsplit, urlunsplit

from pydantic import ValidationError

from backend.schemas import EvidenceRecord
from backend.services.provenance import publication_time


def normalize_results(rows: list, retrieved: datetime, limit: int) -> tuple[list[EvidenceRecord], int]:
    evidence, seen = [], set()
    dropped = 0
    for row in rows[:40]:
        if not isinstance(row, dict):
            dropped += 1
            continue
        try:
            raw_url = row.get("url")
            if not isinstance(raw_url, str) or len(raw_url) > 8192:
                raise ValueError("Invalid URL")
            parts = urlsplit(raw_url)
            if parts.scheme not in {"https", "http"} or not parts.hostname or parts.username or parts.password:
                raise ValueError("Invalid source URL")
            canonical = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, ""))
            if canonical in seen:
                continue
            snippet = row.get("content")
            if not isinstance(snippet, str) or not snippet.strip():
                raise ValueError("Missing content")
            score = row.get("score")
            if not isinstance(score, (float, int)) or not math.isfinite(score) or not 0 <= score <= 1:
                score = None
            item = EvidenceRecord(
                id=f"src_{len(evidence) + 1}", title=str(row.get("title") or "Untitled source")[:300],
                url=raw_url, snippet=snippet.strip()[:3000], retrieved_at_utc=retrieved,
                published_at_utc=publication_time(row.get("published_date")), relevance_score=score,
            )
            seen.add(canonical)
            evidence.append(item)
        except (ValueError, TypeError, ValidationError):
            dropped += 1
        if len(evidence) >= limit:
            break
    evidence.sort(key=lambda item: item.relevance_score if item.relevance_score is not None else -1, reverse=True)
    return evidence, dropped
