"""Normalización de textos y valores de un partido (RF-03).

Cada función de análisis devuelve None cuando el valor no cumple la regla.
Quien llama decide qué código de error registrar.
"""

import re
import unicodedata
from datetime import date, timedelta

MIN_TEAM_NAME_LENGTH = 2
MAX_TEAM_NAME_LENGTH = 60
MIN_COMPETITION_LENGTH = 2
MAX_COMPETITION_LENGTH = 40
MIN_SEASON = 2000
MAX_SEASON = 2100
MAX_MATCHDAY = 99
MAX_GOALS = 30

_COMPETITION_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_SEASON = re.compile(r"[0-9]{4}")
_MATCHDAY = re.compile(r"[0-9]{1,2}")
_GOALS = re.compile(r"[0-9]+")
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_NOT_SLUG_CHARS = re.compile(r"[^a-z0-9]+")


def collapse_spaces(value: str) -> str:
    """Quita los espacios de los extremos y reduce los espacios internos a uno."""
    return " ".join(value.split())


def slugify(value: str) -> str:
    """Pasa un texto a slug: minúsculas, sin tildes y con guiones donde había espacios o signos."""
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _NOT_SLUG_CHARS.sub("-", without_accents.lower()).strip("-")


def is_valid_competition(slug: str) -> bool:
    """Un slug de competición tiene entre 2 y 40 caracteres, solo con a-z, 0-9 y guiones."""
    return (
        MIN_COMPETITION_LENGTH <= len(slug) <= MAX_COMPETITION_LENGTH
        and _COMPETITION_SLUG.fullmatch(slug) is not None
    )


def is_valid_team_name(name: str) -> bool:
    """Un nombre de equipo tiene entre 2 y 60 caracteres."""
    return MIN_TEAM_NAME_LENGTH <= len(name) <= MAX_TEAM_NAME_LENGTH


def parse_season(value: str) -> int | None:
    """Temporada: 4 dígitos entre 2000 y 2100."""
    if _SEASON.fullmatch(value) is None:
        return None
    season = int(value)
    return season if MIN_SEASON <= season <= MAX_SEASON else None


def parse_matchday(value: str) -> int | None:
    """Número de fecha: entero entre 1 y 99."""
    if _MATCHDAY.fullmatch(value) is None:
        return None
    matchday = int(value)
    return matchday if 1 <= matchday <= MAX_MATCHDAY else None


def parse_goals(value: str) -> int | None:
    """Goles: entero entre 0 y 30, sin signos ni decimales."""
    if _GOALS.fullmatch(value) is None:
        return None
    goals = int(value)
    return goals if goals <= MAX_GOALS else None


def parse_match_date(value: str, today: date) -> date | None:
    """Fecha en YYYY-MM-DD, existente y entre 2000-01-01 y un año después de `today`."""
    if _ISO_DATE.fullmatch(value) is None:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    if date(2000, 1, 1) <= parsed <= today + timedelta(days=365):
        return parsed
    return None
