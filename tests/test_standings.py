import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from estadisticas.csv_validation import validate_csv
from estadisticas.models import Match
from estadisticas.normalization import slugify
from estadisticas.standings import compute_standings

FIXTURES = Path(__file__).parent / "fixtures" / "tabla"
TODAY = date(2026, 11, 3)


def load_matches():
    matches = []
    for name in ("fecha-1.csv", "fecha-2.csv", "fecha-3.csv"):
        result = validate_csv((FIXTURES / name).read_bytes(), TODAY)
        assert result.is_valid, result.errors
        matches.extend(result.matches)
    return matches


def _match(home: str, away: str, home_goals: int, away_goals: int) -> Match:
    return Match(
        competition="liga-profesional",
        season=2026,
        matchday=1,
        match_date=date(2026, 3, 7),
        home_team=home,
        home_team_id=slugify(home),
        away_team=away,
        away_team_id=slugify(away),
        home_goals=home_goals,
        away_goals=away_goals,
    )


def test_table_matches_the_expected_fixture():
    rows = [asdict(row) for row in compute_standings(load_matches())]
    expected = json.loads((FIXTURES / "tabla-esperada.json").read_text(encoding="utf-8"))

    assert rows == expected


def test_ties_are_broken_by_team_id_when_the_rest_is_equal():
    matches = [
        _match("Zeta", "Gamma", 1, 0),
        _match("Alfa", "Beta", 1, 0),
    ]
    rows = compute_standings(matches)

    assert [row.team_id for row in rows] == ["alfa", "zeta", "beta", "gamma"]
    assert [row.position for row in rows] == [1, 2, 3, 4]
