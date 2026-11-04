"""Recálculo de la tabla y GET /tabla con tres fechas de ejemplo (RF-13 y RF-14)."""

import json

from helpers import body_of, fixture_bytes, http_event, put_upload, s3_event

from estadisticas.handlers.api_standings import standings_handler
from estadisticas.handlers.ingest import ingest_handler
from estadisticas.handlers.standings_recalc import standings_recalc_handler

SEASON_QUERY = {"competition": "liga-profesional", "season": "2026"}
TOURNAMENT_FILES = ("tabla/fecha-1.csv", "tabla/fecha-2.csv", "tabla/fecha-3.csv")


def _load_tournament(aws) -> None:
    for number, name in enumerate(TOURNAMENT_FILES, start=1):
        key = put_upload(aws.s3, f"tabla-{number}", fixture_bytes(name))
        ingest_handler(s3_event(key), None)


def _expected_table() -> list[dict]:
    return json.loads(fixture_bytes("tabla/tabla-esperada.json"))


def test_recalculated_table_matches_the_expected_fixture(aws):
    _load_tournament(aws)

    assert standings_recalc_handler({}, None) == {"seasons": 1}
    response = standings_handler(http_event(SEASON_QUERY), None)

    assert response["statusCode"] == 200
    assert body_of(response)["items"] == _expected_table()


def test_recalculation_is_idempotent_and_removes_teams_that_no_longer_belong(aws):
    _load_tournament(aws)
    standings_recalc_handler({}, None)
    aws.standings.put_item(
        Item={
            "pk": "SEASON#liga-profesional#2026",
            "sk": "TEAM#equipo-fantasma",
            "team_id": "equipo-fantasma",
            "team": "Equipo Fantasma",
            "position": 99,
            "played": 0,
            "won": 0,
            "drawn": 0,
            "lost": 0,
            "goals_for": 0,
            "goals_against": 0,
            "goal_difference": 0,
            "points": 0,
            "computed_at": "2026-01-01T00:00:00",
        }
    )

    standings_recalc_handler({}, None)

    response = standings_handler(http_event(SEASON_QUERY), None)
    assert body_of(response)["items"] == _expected_table()
