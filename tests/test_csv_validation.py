from datetime import date
from pathlib import Path

import pytest

from estadisticas.csv_validation import MAX_FILE_BYTES, validate_csv

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = date(2026, 11, 3)
HEADER = "competition,season,matchday,match_date,home_team,away_team,home_goals,away_goals"
VALID_ROW = "liga-profesional,2026,5,2026-03-14,Boca Juniors,River Plate,2,1"


def make_csv(*rows: str, header: str = HEADER) -> bytes:
    return "\n".join((header, *rows)).encode("utf-8")


def codes(issues) -> list[str]:
    return [issue.code for issue in issues]


def test_valid_fixture_returns_all_matches():
    result = validate_csv((FIXTURES / "fecha-05-valida.csv").read_bytes(), TODAY)

    assert result.is_valid
    assert result.rows_total == 5
    assert len(result.matches) == 5
    first = result.matches[0]
    assert (first.home_team, first.home_team_id) == ("Boca Juniors", "boca-juniors")
    assert (first.home_goals, first.away_goals) == (2, 1)


def test_missing_column_is_reported_and_no_match_is_returned():
    result = validate_csv((FIXTURES / "fecha-05-sin-away-goals.csv").read_bytes(), TODAY)

    assert codes(result.errors) == ["HEADER_MISSING_COLUMN"]
    assert result.errors[0].column == "away_goals"
    assert result.matches == ()


def test_invalid_date_rejects_the_whole_file():
    result = validate_csv((FIXTURES / "fecha-05-fecha-invalida.csv").read_bytes(), TODAY)

    found = [(issue.code, issue.line, issue.column) for issue in result.errors]
    assert found == [("DATE_INVALID", 3, "match_date")]
    assert result.matches == ()


def test_bom_is_accepted():
    assert validate_csv(b"\xef\xbb\xbf" + make_csv(VALID_ROW), TODAY).is_valid


def test_empty_file_is_rejected():
    assert codes(validate_csv(b"", TODAY).errors) == ["EMPTY_FILE"]


def test_header_without_rows_is_rejected():
    assert codes(validate_csv(make_csv(), TODAY).errors) == ["NO_DATA_ROWS"]


def test_file_that_is_not_utf8_is_rejected():
    text = f"{HEADER}\nliga-profesional,2026,5,2026-03-14,Vélez Sarsfield,River Plate,2,1"
    assert codes(validate_csv(text.encode("latin-1"), TODAY).errors) == ["ENCODING_INVALID"]


def test_file_over_one_megabyte_is_rejected():
    raw = make_csv(VALID_ROW) + b" " * MAX_FILE_BYTES
    assert codes(validate_csv(raw, TODAY).errors) == ["FILE_TOO_LARGE"]


def test_more_than_500_rows_is_rejected():
    rows = [
        f"liga-profesional,2026,5,2026-03-14,Equipo {i:03d} A,Equipo {i:03d} B,1,0"
        for i in range(501)
    ]
    result = validate_csv(make_csv(*rows), TODAY)

    assert codes(result.errors) == ["TOO_MANY_ROWS"]
    assert result.rows_total == 501


def test_exactly_500_rows_is_accepted():
    rows = [
        f"liga-profesional,2026,5,2026-03-14,Equipo {i:03d} A,Equipo {i:03d} B,1,0"
        for i in range(500)
    ]
    result = validate_csv(make_csv(*rows), TODAY)

    assert result.is_valid
    assert len(result.matches) == 500


def test_row_with_an_extra_field_is_reported_with_its_line():
    result = validate_csv(make_csv(VALID_ROW, VALID_ROW + ",extra"), TODAY)

    found = [(issue.code, issue.line) for issue in result.errors]
    assert found == [("ROW_FORMAT_INVALID", 3)]


def test_extra_column_is_a_warning_not_an_error():
    row = "liga-profesional,2026,5,2026-03-14,Boca Juniors,River Plate,2,1,sin novedades"
    result = validate_csv(make_csv(row, header=HEADER + ",notes"), TODAY)

    assert result.is_valid
    assert codes(result.warnings) == ["EXTRA_COLUMN_IGNORED"]


@pytest.mark.parametrize(
    ("row", "code", "column"),
    [
        (
            "liga-profesional,2026,5,2026-03-14,Boca Juniors,Boca Juniors,2,1",
            "SAME_TEAM",
            "away_team",
        ),
        (
            "liga-profesional,2026,5,2026-03-14,Boca Juniors,River Plate,3.0,1",
            "GOALS_INVALID",
            "home_goals",
        ),
        (
            "liga-profesional,2026,5,2026-03-14,,River Plate,2,1",
            "FIELD_REQUIRED",
            "home_team",
        ),
        (
            "liga-profesional,2026,5,2026-03-14,B,River Plate,2,1",
            "TEAM_NAME_INVALID",
            "home_team",
        ),
        (
            "liga-profesional,2026,5,2026-03-14,-- ,River Plate,2,1",
            "TEAM_NAME_INVALID",
            "home_team",
        ),
        ("x,2026,5,2026-03-14,Boca Juniors,River Plate,2,1", "FIELD_INVALID", "competition"),
        (
            "liga-profesional,1999,5,2026-03-14,Boca Juniors,River Plate,2,1",
            "FIELD_INVALID",
            "season",
        ),
        (
            "liga-profesional,2026,0,2026-03-14,Boca Juniors,River Plate,2,1",
            "FIELD_INVALID",
            "matchday",
        ),
    ],
)
def test_row_level_errors_point_to_the_line_and_column(row, code, column):
    result = validate_csv(make_csv(row), TODAY)

    found = [(issue.code, issue.line, issue.column) for issue in result.errors]
    assert found == [(code, 2, column)]
    assert result.matches == ()


def test_mixed_matchday_is_reported_on_the_row_that_differs():
    other_matchday = "liga-profesional,2026,6,2026-03-21,Racing Club,Independiente,0,0"
    result = validate_csv(make_csv(VALID_ROW, other_matchday), TODAY)

    found = [(issue.code, issue.line) for issue in result.errors]
    assert found == [("MIXED_MATCHDAY", 3)]


def test_same_pair_twice_is_a_duplicate_match():
    result = validate_csv(make_csv(VALID_ROW, VALID_ROW), TODAY)

    found = [(issue.code, issue.line) for issue in result.errors]
    assert found == [("DUPLICATE_MATCH", 3)]


def test_team_cannot_play_twice_in_the_same_matchday():
    second = "liga-profesional,2026,5,2026-03-14,Boca Juniors,Racing Club,0,0"
    result = validate_csv(make_csv(VALID_ROW, second), TODAY)

    found = [(issue.code, issue.line, issue.column) for issue in result.errors]
    assert found == [("TEAM_REPEATED_IN_MATCHDAY", 3, "home_team")]
