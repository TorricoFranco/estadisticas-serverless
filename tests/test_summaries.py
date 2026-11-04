from datetime import date

import pytest

from estadisticas.models import Match
from estadisticas.summaries import build_summary


def _match(home: str, away: str, home_goals: int, away_goals: int) -> Match:
    return Match(
        competition="liga-profesional",
        season=2026,
        matchday=5,
        match_date=date(2026, 3, 14),
        home_team=home,
        home_team_id=home.lower().replace(" ", "-"),
        away_team=away,
        away_team_id=away.lower().replace(" ", "-"),
        home_goals=home_goals,
        away_goals=away_goals,
    )


@pytest.mark.parametrize(
    ("home", "away", "home_goals", "away_goals", "expected"),
    [
        (
            "Boca Juniors",
            "River Plate",
            2,
            1,
            "Boca Juniors 2-1 River Plate: ganó el local (fecha 5).",
        ),
        (
            "Gimnasia",
            "Estudiantes",
            0,
            3,
            "Gimnasia 0-3 Estudiantes: ganó el visitante (fecha 5).",
        ),
        (
            "Racing Club",
            "Independiente",
            0,
            0,
            "Racing Club 0-0 Independiente: empate (fecha 5).",
        ),
    ],
)
def test_summary_uses_the_template_for_each_outcome(home, away, home_goals, away_goals, expected):
    assert build_summary(_match(home, away, home_goals, away_goals)) == expected
