from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def publication_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return date.astimezone(timezone.utc) if date.tzinfo else None
    except ValueError:
        return None
