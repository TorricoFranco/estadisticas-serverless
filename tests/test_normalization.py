from datetime import date

import pytest

from estadisticas.normalization import (
    collapse_spaces,
    is_valid_competition,
    parse_goals,
    parse_match_date,
    parse_matchday,
    parse_season,
    slugify,
)

TODAY = date(2026, 11, 3)


def test_collapse_spaces_trims_and_reduces_inner_spaces():
    assert collapse_spaces("  Boca   Juniors ") == "Boca Juniors"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Vélez Sarsfield", "velez-sarsfield"),
        ("Liga  Profesional ", "liga-profesional"),
        ("Argentinos Jrs.", "argentinos-jrs"),
        ("1 de Mayo", "1-de-mayo"),
        ("Atlético Tucumán", "atletico-tucuman"),
    ],
)
def test_slugify_removes_accents_and_signs(raw, expected):
    assert slugify(raw) == expected


def test_slugify_returns_empty_when_nothing_is_left():
    assert slugify("--!!") == ""


@pytest.mark.parametrize(
    ("slug", "valid"),
    [
        ("liga-profesional", True),
        ("a", False),
        ("liga--profesional", False),
        ("Liga", False),
        ("x" * 41, False),
    ],
)
def test_competition_slug_rules(slug, valid):
    assert is_valid_competition(slug) is valid


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("2026", 2026), ("1999", None), ("2101", None), ("26", None), ("2026.0", None)],
)
def test_parse_season(raw, expected):
    assert parse_season(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("5", 5), ("05", 5), ("0", None), ("100", None), ("x", None)],
)
def test_parse_matchday(raw, expected):
    assert parse_matchday(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("0", 0), ("30", 30), ("31", None), ("3.0", None), ("-1", None)],
)
def test_parse_goals(raw, expected):
    assert parse_goals(raw) == expected


def test_parse_match_date_accepts_iso_dates_inside_the_range():
    assert parse_match_date("2026-03-14", TODAY) == date(2026, 3, 14)
    assert parse_match_date("2027-11-03", TODAY) == date(2027, 11, 3)


@pytest.mark.parametrize(
    "raw",
    ["2026-3-14", "2026-02-30", "14/03/2026", "1999-12-31", "2027-11-04"],
)
def test_parse_match_date_rejects_bad_or_out_of_range_dates(raw):
    assert parse_match_date(raw, TODAY) is None
