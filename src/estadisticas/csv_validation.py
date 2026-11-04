"""Validación de un CSV con los partidos de una fecha (RF-02, RF-03 y RF-04).

La validación es todo o nada: si una fila tiene un error, no se devuelve ningún partido.
"""

import csv
import io
from datetime import date

from estadisticas.models import Issue, Match, ValidationResult
from estadisticas.normalization import (
    collapse_spaces,
    is_valid_competition,
    is_valid_team_name,
    parse_goals,
    parse_match_date,
    parse_matchday,
    parse_season,
    slugify,
)

MAX_FILE_BYTES = 1_048_576
MAX_DATA_ROWS = 500
REQUIRED_COLUMNS = (
    "competition",
    "season",
    "matchday",
    "match_date",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
)

_COMPETITION_MESSAGE = (
    "La competición debe tener entre 2 y 40 caracteres: minúsculas, números y guiones."
)
_SEASON_MESSAGE = "La temporada debe ser un año entre 2000 y 2100."
_MATCHDAY_MESSAGE = "La fecha debe ser un número entre 1 y 99."
_GOALS_MESSAGE = "Los goles deben ser un entero entre 0 y 30."
_SAME_TEAM_MESSAGE = "Local y visitante no pueden ser el mismo equipo."
_DUPLICATE_MESSAGE = "Este local y visitante ya aparecen en el archivo."
_MIXED_MESSAGE = "La competición, la temporada o la fecha no coinciden con la primera fila."


def validate_csv(raw: bytes, today: date) -> ValidationResult:
    """Valida el archivo completo. `today` fija el límite superior de las fechas."""
    if len(raw) > MAX_FILE_BYTES:
        too_large = Issue(1, None, "FILE_TOO_LARGE", "El archivo supera 1 MB (1.048.576 bytes).")
        return _rejected(too_large)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        not_utf8 = Issue(1, None, "ENCODING_INVALID", "El archivo no está codificado en UTF-8.")
        return _rejected(not_utf8)

    numbered_rows = _read_rows(text)
    if not numbered_rows:
        return _rejected(Issue(1, None, "EMPTY_FILE", "El archivo está vacío."))

    header_line, header = numbered_rows[0]
    data_rows = numbered_rows[1:]
    columns = [name.strip().lower() for name in header]
    warnings = tuple(
        Issue(
            header_line,
            name,
            "EXTRA_COLUMN_IGNORED",
            f"La columna {name} no se usa y se ignora.",
        )
        for name in columns
        if name not in REQUIRED_COLUMNS
    )
    missing = tuple(
        Issue(
            header_line,
            name,
            "HEADER_MISSING_COLUMN",
            f"Falta la columna obligatoria {name}.",
        )
        for name in REQUIRED_COLUMNS
        if name not in columns
    )
    if missing:
        return ValidationResult(len(data_rows), (), missing, warnings)
    if not data_rows:
        no_rows = Issue(header_line, None, "NO_DATA_ROWS", "El archivo no tiene partidos.")
        return ValidationResult(0, (), (no_rows,), warnings)
    if len(data_rows) > MAX_DATA_ROWS:
        line = data_rows[MAX_DATA_ROWS][0]
        too_many = Issue(
            line, None, "TOO_MANY_ROWS", "El archivo supera los 500 partidos permitidos."
        )
        return ValidationResult(len(data_rows), (), (too_many,), warnings)

    column_index = {name: columns.index(name) for name in REQUIRED_COLUMNS}
    errors: list[Issue] = []
    parsed: list[tuple[int, Match]] = []
    for line, row in data_rows:
        if len(row) != len(columns):
            message = f"La fila tiene {len(row)} campos y el encabezado tiene {len(columns)}."
            errors.append(Issue(line, None, "ROW_FORMAT_INVALID", message))
            continue
        match = _parse_row(line, row, column_index, today, errors)
        if match is not None:
            parsed.append((line, match))

    errors.extend(_check_consistency(parsed))
    if errors:
        ordered = tuple(sorted(errors, key=lambda issue: issue.line))
        return ValidationResult(len(data_rows), (), ordered, warnings)
    matches = tuple(match for _, match in parsed)
    return ValidationResult(len(data_rows), matches, (), warnings)


def _read_rows(text: str) -> list[tuple[int, list[str]]]:
    """Devuelve las filas no vacías junto con el número de línea donde termina cada una."""
    reader = csv.reader(io.StringIO(text))
    rows: list[tuple[int, list[str]]] = []
    for row in reader:
        if any(cell.strip() for cell in row):
            rows.append((reader.line_num, row))
    return rows


def _parse_row(
    line: int,
    row: list[str],
    column_index: dict[str, int],
    today: date,
    errors: list[Issue],
) -> Match | None:
    """Valida y normaliza una fila; agrega los errores a `errors` y devuelve None si algo falla."""
    values = {name: collapse_spaces(row[index]) for name, index in column_index.items()}
    empty = [name for name in REQUIRED_COLUMNS if not values[name]]
    if empty:
        for name in empty:
            errors.append(Issue(line, name, "FIELD_REQUIRED", f"El campo {name} está vacío."))
        return None

    failures_before = len(errors)
    competition = slugify(values["competition"])
    if not is_valid_competition(competition):
        errors.append(Issue(line, "competition", "FIELD_INVALID", _COMPETITION_MESSAGE))
    season = parse_season(values["season"])
    if season is None:
        errors.append(Issue(line, "season", "FIELD_INVALID", _SEASON_MESSAGE))
    matchday = parse_matchday(values["matchday"])
    if matchday is None:
        errors.append(Issue(line, "matchday", "FIELD_INVALID", _MATCHDAY_MESSAGE))
    match_date = parse_match_date(values["match_date"], today)
    if match_date is None:
        message = f"La fecha {values['match_date']} debe tener formato YYYY-MM-DD y ser válida."
        errors.append(Issue(line, "match_date", "DATE_INVALID", message))
    home = _team(line, "home_team", values["home_team"], errors)
    away = _team(line, "away_team", values["away_team"], errors)
    home_goals = parse_goals(values["home_goals"])
    if home_goals is None:
        errors.append(Issue(line, "home_goals", "GOALS_INVALID", _GOALS_MESSAGE))
    away_goals = parse_goals(values["away_goals"])
    if away_goals is None:
        errors.append(Issue(line, "away_goals", "GOALS_INVALID", _GOALS_MESSAGE))
    if home is not None and away is not None and home[1] == away[1]:
        errors.append(Issue(line, "away_team", "SAME_TEAM", _SAME_TEAM_MESSAGE))

    if (
        len(errors) > failures_before
        or season is None
        or matchday is None
        or match_date is None
        or home is None
        or away is None
        or home_goals is None
        or away_goals is None
    ):
        return None
    return Match(
        competition=competition,
        season=season,
        matchday=matchday,
        match_date=match_date,
        home_team=home[0],
        home_team_id=home[1],
        away_team=away[0],
        away_team_id=away[1],
        home_goals=home_goals,
        away_goals=away_goals,
    )


def _team(line: int, column: str, name: str, errors: list[Issue]) -> tuple[str, str] | None:
    """Devuelve el nombre y su team_id, o None si el nombre no sirve."""
    if not is_valid_team_name(name):
        message = f'El nombre "{name}" debe tener entre 2 y 60 caracteres.'
        errors.append(Issue(line, column, "TEAM_NAME_INVALID", message))
        return None
    team_id = slugify(name)
    if not team_id:
        message = f'El nombre "{name}" no tiene letras ni números.'
        errors.append(Issue(line, column, "TEAM_NAME_INVALID", message))
        return None
    return name, team_id


def _check_consistency(parsed: list[tuple[int, Match]]) -> list[Issue]:
    """Reglas entre filas: una sola fecha, sin cruces repetidos y sin equipos repetidos."""
    if not parsed:
        return []
    issues: list[Issue] = []
    first = parsed[0][1]
    reference = (first.competition, first.season, first.matchday)
    pairs: set[tuple[str, str]] = set()
    teams_seen: set[str] = set()
    for line, match in parsed:
        if (match.competition, match.season, match.matchday) != reference:
            issues.append(Issue(line, None, "MIXED_MATCHDAY", _MIXED_MESSAGE))
            continue
        pair = (match.home_team_id, match.away_team_id)
        if pair in pairs:
            issues.append(Issue(line, None, "DUPLICATE_MATCH", _DUPLICATE_MESSAGE))
            continue
        pairs.add(pair)
        for column, team, team_id in (
            ("home_team", match.home_team, match.home_team_id),
            ("away_team", match.away_team, match.away_team_id),
        ):
            if team_id in teams_seen:
                message = f"{team} ya juega en esta fecha."
                issues.append(Issue(line, column, "TEAM_REPEATED_IN_MATCHDAY", message))
            teams_seen.add(team_id)
    return issues


def _rejected(issue: Issue) -> ValidationResult:
    return ValidationResult(rows_total=0, matches=(), errors=(issue,), warnings=())
