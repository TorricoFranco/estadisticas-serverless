"""Modelos del dominio: partidos, errores de validación y resultado de validar un archivo."""

from dataclasses import dataclass
from datetime import date

from estadisticas.identifiers import data_hash_for, match_id_for


@dataclass(frozen=True)
class Match:
    """Un partido ya validado y normalizado."""

    competition: str
    season: int
    matchday: int
    match_date: date
    home_team: str
    home_team_id: str
    away_team: str
    away_team_id: str
    home_goals: int
    away_goals: int

    @property
    def match_id(self) -> str:
        return match_id_for(
            self.competition,
            self.season,
            self.matchday,
            self.home_team_id,
            self.away_team_id,
        )

    @property
    def data_hash(self) -> str:
        return data_hash_for(
            self.match_date.isoformat(),
            self.home_team,
            self.away_team,
            self.home_goals,
            self.away_goals,
        )


@dataclass(frozen=True)
class Issue:
    """Un error o una advertencia del archivo, con la línea y la columna donde aparece."""

    line: int
    column: str | None
    code: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    """Resultado de validar un CSV. `matches` solo tiene partidos si el archivo no tiene errores."""

    rows_total: int
    matches: tuple[Match, ...]
    errors: tuple[Issue, ...]
    warnings: tuple[Issue, ...]

    @property
    def is_valid(self) -> bool:
        return not self.errors
