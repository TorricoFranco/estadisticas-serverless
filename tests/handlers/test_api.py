"""Pruebas de las rutas HTTP: partidos, tabla y subidas (sección 8 del ERS)."""

import json
import uuid

import pytest
from helpers import (
    BUCKET,
    body_of,
    drain_queue,
    fixture_bytes,
    http_event,
    put_upload,
    s3_event,
    sqs_event,
)

from estadisticas.config import DAILY_LIMIT_PARAM
from estadisticas.handlers.api_matches import matches_handler
from estadisticas.handlers.api_standings import standings_handler
from estadisticas.handlers.api_uploads import upload_url_handler
from estadisticas.handlers.ingest import ingest_handler
from estadisticas.handlers.summary import summary_handler

UPLOAD = "5d2c8f1e-7a3b-4c2d-9e10-8f6a1b2c3d4e"
SEASON_QUERY = {"competition": "liga-profesional", "season": "2026"}
UPLOAD_BODY = json.dumps({"filename": "fecha-05.csv", "content_type": "text/csv"})


def _load_matchday_five(aws) -> None:
    key = put_upload(aws.s3, UPLOAD, fixture_bytes("fecha-05-valida.csv"))
    ingest_handler(s3_event(key), None)
    summary_handler(sqs_event(*drain_queue(aws.sqs, aws.queue_url)), None)


def test_matchday_list_is_sorted_by_date_and_includes_the_summary(aws):
    _load_matchday_five(aws)

    response = matches_handler(http_event({**SEASON_QUERY, "matchday": "5"}), None)

    assert response["statusCode"] == 200
    items = body_of(response)["items"]
    assert len(items) == 5
    order = [(item["match_date"], item["home_team"]) for item in items]
    assert order == sorted(order)
    boca = next(item for item in items if item["home_team"] == "Boca Juniors")
    assert boca["summary_status"] == "READY"
    assert boca["summary"] == "Boca Juniors 2-1 River Plate: ganó el local (fecha 5)."


def test_season_listing_is_paginated_without_repeats(aws):
    _load_matchday_five(aws)
    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        query = {**SEASON_QUERY, "limit": "2"}
        if cursor is not None:
            query["cursor"] = cursor
        body = body_of(matches_handler(http_event(query), None))
        seen.extend(item["match_id"] for item in body["items"])
        pages += 1
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert pages == 3
    assert len(seen) == len(set(seen)) == 5


@pytest.mark.parametrize(
    "query",
    [
        {"competition": "liga-profesional", "season": "1999"},
        {"competition": "X", "season": "2026"},
        {**SEASON_QUERY, "matchday": "0"},
        {**SEASON_QUERY, "limit": "51"},
        {**SEASON_QUERY, "cursor": "@@@"},
    ],
)
def test_invalid_parameters_return_400_with_the_error_code(aws, query):
    response = matches_handler(http_event(query), None)

    assert response["statusCode"] == 400
    error = body_of(response)["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["request_id"] == "req-test"


def test_unknown_season_in_the_table_returns_404(aws):
    response = standings_handler(http_event(SEASON_QUERY), None)

    assert response["statusCode"] == 404
    assert body_of(response)["error"]["code"] == "SEASON_NOT_FOUND"


def test_upload_url_is_a_presigned_post_for_an_incoming_key(aws):
    response = upload_url_handler(http_event(body=UPLOAD_BODY), None)

    assert response["statusCode"] == 201
    payload = body_of(response)
    assert uuid.UUID(payload["upload_id"]).version == 4
    assert payload["upload"]["fields"]["key"] == f"incoming/{payload['upload_id']}.csv"
    assert BUCKET in payload["upload"]["url"]
    assert payload["expires_in"] == 300


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ("no es json", 400, "VALIDATION_ERROR"),
        (json.dumps({"filename": "fecha-05.csv"}), 400, "VALIDATION_ERROR"),
        (
            json.dumps({"filename": "fecha-05.csv", "content_type": "text/csv", "x": 1}),
            400,
            "VALIDATION_ERROR",
        ),
        (
            json.dumps({"filename": "fecha.txt", "content_type": "text/csv"}),
            400,
            "VALIDATION_ERROR",
        ),
        (
            json.dumps({"filename": "fecha-05.csv", "content_type": "text/plain"}),
            400,
            "VALIDATION_ERROR",
        ),
        (" " * 1025, 413, "PAYLOAD_TOO_LARGE"),
    ],
)
def test_upload_rejects_bad_bodies(aws, body, status, code):
    response = upload_url_handler(http_event(body=body), None)

    assert response["statusCode"] == status
    assert body_of(response)["error"]["code"] == code


def test_daily_quota_stops_uploads_after_the_limit(aws):
    aws.ssm.put_parameter(Name=DAILY_LIMIT_PARAM, Value="1", Type="String", Overwrite=True)

    first = upload_url_handler(http_event(body=UPLOAD_BODY), None)
    second = upload_url_handler(http_event(body=UPLOAD_BODY), None)

    assert first["statusCode"] == 201
    assert second["statusCode"] == 429
    assert body_of(second)["error"]["code"] == "DAILY_QUOTA_EXCEEDED"
