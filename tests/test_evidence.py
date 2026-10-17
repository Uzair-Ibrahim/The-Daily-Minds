from backend.services.normalize import normalize_results
from backend.services.provenance import utc_now, publication_time


def test_dedupe_complete_urls_and_bounds():
    rows = [
        {"url": "https://example.org/path?a=1#first", "title": "t" * 400, "content": "x" * 4000, "score": 0.2},
        {"url": "https://example.org/path?a=1#second", "content": "duplicate"},
        {"url": "https://example.org/path?a=2", "content": "different query", "score": 0.9},
        {"url": "https://user:secret@example.org/", "content": "bad"},
    ]
    records, dropped = normalize_results(rows, utc_now(), 8)
    assert len(records) == 2 and dropped == 1
    assert str(records[1].url) == rows[0]["url"]
    assert len(records[1].snippet) == 3000 and len(records[1].title) == 300
    assert records[0].relevance_score == 0.9
    assert all(item.is_official_source is None for item in records)


def test_unknown_dates_stay_unknown():
    for value in (None, "invalid", "2026-10-17", "2026-10-17T12:00:00"):
        assert publication_time(value) is None
    assert publication_time("2026-10-17T12:00:00+05:00").hour == 7
