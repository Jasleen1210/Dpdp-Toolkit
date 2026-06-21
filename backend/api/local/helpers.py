from datetime import datetime, timezone
import os

DEVICE_ACTIVE_WINDOW_SECONDS = max(
    30,
    int(os.getenv("DEVICE_ACTIVE_WINDOW_SECONDS", "180")),
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt_value):
    if dt_value is None:
        return None
    if isinstance(dt_value, str):
        try:
            dt_value = datetime.fromisoformat(dt_value)
        except ValueError:
            return None
    if dt_value.tzinfo is None:
        return dt_value.replace(tzinfo=timezone.utc)
    return dt_value.astimezone(timezone.utc)


def _parse_iso_datetime(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return _as_utc(dt)


def _is_device_active(last_seen_value) -> bool:
    last_seen = _as_utc(last_seen_value)
    if not last_seen:
        return False
    return (utc_now() - last_seen).total_seconds() <= DEVICE_ACTIVE_WINDOW_SECONDS


def _with_device_activity(device_doc: dict) -> dict:
    enriched = dict(device_doc)
    is_active = _is_device_active(device_doc.get("last_seen"))
    enriched["is_active"] = is_active
    enriched["activity_status"] = "active" if is_active else "inactive"
    enriched["active_window_seconds"] = DEVICE_ACTIVE_WINDOW_SECONDS
    return enriched