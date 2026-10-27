"""Bounded, local record of confirmed Apple Store stock transitions."""

import json
from pathlib import Path


def read_history(path, limit=30):
    """Return newest events first, ignoring missing or malformed history."""
    if limit <= 0:
        return []
    try:
        events = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return []
    if not isinstance(events, list):
        return []
    return [event for event in events[-limit:] if isinstance(event, dict)][::-1]


def append_history(path, events, max_entries=500):
    """Append transitions atomically, retaining at most max_entries events.

    History is best-effort and must never interrupt stock monitoring.
    """
    if not events or max_entries <= 0:
        return True
    target = Path(path)
    previous = read_history(target, limit=max_entries)[::-1]
    combined = (previous + list(events))[-max_entries:]
    temporary = target.with_name(target.name + ".tmp")
    try:
        temporary.write_text(
            json.dumps(combined, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(target)
        return True
    except OSError as exc:
        print(f"History save error: {exc}", flush=True)
        return False


def transition_event(item, event_type, timestamp):
    """Keep only useful non-sensitive metadata from an observed stock change."""
    if event_type not in ("available", "unavailable"):
        raise ValueError("History accepts only confirmed stock transitions")
    return {
        "at": timestamp,
        "type": event_type,
        "product_id": item.get("product_id"),
        "product": item.get("productName"),
        "market": item.get("market"),
        "store_id": item.get("storeNumber"),
        "store": item.get("storeName"),
        "city": item.get("city"),
        "state": item.get("state"),
    }
