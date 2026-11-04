"""GET /tabla: tabla de posiciones de una temporada (sección 8.4 del ERS)."""

from typing import Any

from estadisticas import repository
from estadisticas.aws import dynamodb_table
from estadisticas.config import load_settings
from estadisticas.handlers.http import ApiError, api_handler, competition_and_season, query_params

FUNCTION = "estadisticas-standings"


@api_handler(FUNCTION)
def standings_handler(event: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    competition, season = competition_and_season(query_params(event))
    table = dynamodb_table(load_settings().standings_table)
    items = repository.query_standings(table, repository.season_pk(competition, season))
    if not items:
        raise ApiError(404, "SEASON_NOT_FOUND", "No hay tabla para esa competición y temporada.")
    items.sort(key=lambda item: int(item["position"]))
    return 200, {
        "competition": competition,
        "season": season,
        "computed_at": max(item["computed_at"] for item in items),
        "items": [_row_view(item) for item in items],
    }


def _row_view(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "position": int(item["position"]),
        "team": item["team"],
        "team_id": item["team_id"],
        "played": int(item["played"]),
        "won": int(item["won"]),
        "drawn": int(item["drawn"]),
        "lost": int(item["lost"]),
        "goals_for": int(item["goals_for"]),
        "goals_against": int(item["goals_against"]),
        "goal_difference": int(item["goal_difference"]),
        "points": int(item["points"]),
    }
