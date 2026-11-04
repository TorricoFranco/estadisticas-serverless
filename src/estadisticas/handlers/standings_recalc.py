"""Handler de recálculo de la tabla de posiciones: corre una vez por día con EventBridge (RF-14)."""

from datetime import UTC, datetime
from typing import Any

from estadisticas import repository
from estadisticas.aws import dynamodb_table
from estadisticas.config import load_settings
from estadisticas.logs import log
from estadisticas.standings import compute_standings

FUNCTION = "estadisticas-standings-recalc"


def standings_recalc_handler(event: dict[str, Any], context: object) -> dict[str, int]:
    settings = load_settings()
    matches_table = dynamodb_table(settings.matches_table)
    standings_table = dynamodb_table(settings.standings_table)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    seasons = repository.list_seasons(matches_table)
    for competition, season in seasons:
        pk = repository.season_pk(competition, season)
        items = repository.list_season_matches(matches_table, pk)
        rows = compute_standings(repository.match_from_item(item) for item in items)
        repository.save_standings(standings_table, pk, rows, stamp)
        log(
            "INFO",
            FUNCTION,
            "standings_recalculated",
            competition=competition,
            season=season,
            teams=len(rows),
        )
    return {"seasons": len(seasons)}
