"""Logs estructurados: una línea JSON por evento (NFR-07 del ERS)."""

import json
from datetime import UTC, datetime
from typing import Any


def log(level: str, function: str, event: str, **fields: Any) -> None:
    record = {
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "level": level,
        "function": function,
        "event": event,
        **fields,
    }
    print(json.dumps(record, ensure_ascii=False, default=str), flush=True)
