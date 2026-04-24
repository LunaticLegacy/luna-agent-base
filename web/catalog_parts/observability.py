from __future__ import annotations

from typing import Any, Dict, List, Optional

from .shared import (
    _collect_observability_items,
    _filter_observability_items,
    _observability_stats,
    _parse_iso_timestamp,
    jsonable_text,
)


def build_event_catalog(
    registry,
    *,
    level: Optional[str] = None,
    source: Optional[str] = None,
    from_time: Optional[str] = None,
    to_time: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
) -> Dict[str, Any]:
    items = _collect_observability_items(registry)
    filtered = _filter_observability_items(
        items,
        level=level,
        source=source,
        from_time=from_time,
        to_time=to_time,
        q=q,
    )
    page = max(1, int(page or 1))
    limit = max(1, int(limit or 50))
    start = (page - 1) * limit
    return {
        "total": len(filtered),
        "page": page,
        "limit": limit,
        "items": filtered[start : start + limit],
        "stats": _observability_stats(filtered),
    }


def build_log_catalog(
    registry,
    *,
    level: Optional[str] = None,
    service: Optional[str] = None,
    from_time: Optional[str] = None,
    to_time: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
    limit: int = 100,
) -> Dict[str, Any]:
    items = _collect_observability_items(registry)
    normalized_level = str(level or "").strip().lower()
    normalized_service = str(service or "").strip().lower()
    normalized_query = str(q or "").strip().lower()
    from_dt = _parse_iso_timestamp(from_time)
    to_dt = _parse_iso_timestamp(to_time)

    log_items: List[Dict[str, Any]] = []
    for item in items:
        item_level = str(item.get("level", "")).lower()
        if normalized_level and item_level != normalized_level:
            continue
        if normalized_service and normalized_service not in str(item.get("source", "")).lower():
            continue
        item_time = _parse_iso_timestamp(item.get("time"))
        if from_dt is not None and (item_time is None or item_time < from_dt):
            continue
        if to_dt is not None and (item_time is None or item_time > to_dt):
            continue
        if normalized_query:
            searchable = " ".join(
                [
                    str(item.get("id", "")),
                    str(item.get("source", "")),
                    str(item.get("event", "")),
                    str(item.get("detail", "")),
                    jsonable_text(item.get("data")),
                ]
            ).lower()
            if normalized_query not in searchable:
                continue
        log_items.append(
            {
                "id": item.get("id"),
                "time": item.get("time"),
                "level": str(item.get("level", "info")).upper(),
                "service": str(item.get("source", "system")),
                "message": f"{item.get('event', '')} — {item.get('detail', '')}"
                if item.get("detail")
                else str(item.get("event", "")),
                "raw": item,
            }
        )

    log_items.sort(key=lambda value: str(value.get("time") or ""), reverse=True)
    page = max(1, int(page or 1))
    limit = max(1, int(limit or 100))
    start = (page - 1) * limit
    paged = log_items[start : start + limit]
    return {
        "total": len(log_items),
        "page": page,
        "limit": limit,
        "items": paged,
        "stats": {
            "error": sum(1 for item in log_items if item["level"] == "ERROR"),
            "warn": sum(1 for item in log_items if item["level"] == "WARN"),
            "info": sum(1 for item in log_items if item["level"] == "INFO"),
            "debug": sum(1 for item in log_items if item["level"] == "DEBUG"),
        },
    }
