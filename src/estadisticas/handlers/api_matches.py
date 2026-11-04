"""GET /partidos: partidos de una temporada con el estado de su resumen (sección 8.3 del ERS)."""

import base64
import json
from typing import Any

from estadisticas import repository
from estadisticas.aws import dynamodb_table
from estadisticas.config import load_settings
from estadisticas.handlers.http import (
    ApiError,
    api_handler,
    competition_and_season,
    optional_int,
    query_params,
)

FUNCTION = "estadisticas-matches"
DEFAULT_LIMIT = 20
MAX_LIMIT = 50
MAX_CURSOR_LENGTH = 512


@api_handler(FUNCTION)
def matches_handler(event: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    params = query_params(event)
    competition, season = competition_and_season(params)
    matchday = optional_int(params, "matchday", 1, 99)
    table = dynamodb_table(load_settings().matches_table)
    pk = repository.season_pk(competition, season)
    if matchday is not None:
        items = repository.query_matchday(table, pk, matchday)
        items.sort(key=lambda item: (item["match_date"], item["home_team"]))
        return 200, {"items": [_match_view(item) for item in items], "next_cursor": None}

    limit = optional_int(params, "limit", 1, MAX_LIMIT, default=DEFAULT_LIMIT) or DEFAULT_LIMIT
    start_key = _decode_cursor(params.get("cursor"), pk)
    items, last_key = repository.query_season_page(table, pk, limit, start_key)
    next_cursor = _encode_cursor(last_key) if last_key else None
    return 200, {"items": [_match_view(item) for item in items], "next_cursor": next_cursor}


def _match_view(item: dict[str, Any]) -> dict[str, Any]:
    ready = item.get("summary_status") == "READY"
    return {
        "match_id": item["match_id"],
        "competition": item["competition"],
        "season": int(item["season"]),
        "matchday": int(item["matchday"]),
        "match_date": item["match_date"],
        "home_team": item["home_team"],
        "away_team": item["away_team"],
        "home_goals": int(item["home_goals"]),
        "away_goals": int(item["away_goals"]),
        "summary_status": item.get("summary_status", "PENDING"),
        "summary": item.get("summary") if ready else None,
    }


def _encode_cursor(key: dict[str, Any]) -> str:
    raw = json.dumps(key, sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None, pk: str) -> dict[str, Any] | None:
    if cursor is None:
        return None
    invalid = ApiError(400, "VALIDATION_ERROR", "El parámetro cursor no es válido.")
    if len(cursor) > MAX_CURSOR_LENGTH:
        raise invalid
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        key = json.loads(base64.urlsafe_b64decode(padded))
    except ValueError:
        raise invalid from None
    if not isinstance(key, dict) or set(key) != {"pk", "sk"} or key["pk"] != pk:
        raise invalid
    if not isinstance(key["sk"], str):
        raise invalid
    return key
