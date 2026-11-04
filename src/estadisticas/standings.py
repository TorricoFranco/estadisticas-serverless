"""Tabla de posiciones de una competición y temporada (RF-13 y RF-14)."""

from collections.abc import Iterable
from dataclasses import dataclass

from estadisticas.models import Match

POINTS_WIN = 3
POINTS_DRAW = 1


@dataclass
class _Totals:
    team: str
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0

    def add_result(self, goals_for: int, goals_against: int) -> None:
        self.played += 1
        self.goals_for += goals_for
        self.goals_against += goals_against
        if goals_for > goals_against:
            self.won += 1
        elif goals_for == goals_against:
            self.drawn += 1
        else:
            self.lost += 1

    @property
    def points(self) -> int:
        return POINTS_WIN * self.won + POINTS_DRAW * self.drawn

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against


@dataclass(frozen=True)
class StandingRow:
    position: int
    team_id: str
    team: str
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int


def compute_standings(matches: Iterable[Match]) -> list[StandingRow]:
    """Calcula la tabla a partir de los partidos de una sola competición y temporada.

    Orden: puntos, diferencia de goles, goles a favor y, por último, team_id alfabético.
    Los desempates por enfrentamientos directos quedan fuera de la v1.
    """
    totals: dict[str, _Totals] = {}
    for match in matches:
        _totals_for(totals, match.home_team_id, match.home_team).add_result(
            match.home_goals, match.away_goals
        )
        _totals_for(totals, match.away_team_id, match.away_team).add_result(
            match.away_goals, match.home_goals
        )

    ordered = sorted(
        totals.items(),
        key=lambda item: (
            -item[1].points,
            -item[1].goal_difference,
            -item[1].goals_for,
            item[0],
        ),
    )
    return [
        StandingRow(
            position=position,
            team_id=team_id,
            team=team_totals.team,
            played=team_totals.played,
            won=team_totals.won,
            drawn=team_totals.drawn,
            lost=team_totals.lost,
            goals_for=team_totals.goals_for,
            goals_against=team_totals.goals_against,
            goal_difference=team_totals.goal_difference,
            points=team_totals.points,
        )
        for position, (team_id, team_totals) in enumerate(ordered, start=1)
    ]


def _totals_for(totals: dict[str, _Totals], team_id: str, team: str) -> _Totals:
    if team_id not in totals:
        totals[team_id] = _Totals(team)
    return totals[team_id]
