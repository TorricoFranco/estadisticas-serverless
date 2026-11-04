"""Pruebas del handler de ingesta con S3, DynamoDB y SQS simulados (RF-01 a RF-08)."""

import json

import pytest
from botocore.exceptions import ClientError
from helpers import (
    BUCKET,
    csv_bytes,
    drain_queue,
    fixture_bytes,
    put_upload,
    s3_event,
    sqs_event,
)

from estadisticas.handlers.ingest import ingest_handler
from estadisticas.handlers.summary import summary_handler

UPLOAD = "5d2c8f1e-7a3b-4c2d-9e10-8f6a1b2c3d4e"
SECOND_UPLOAD = "6e3d9f2a-8b4c-4d3e-8f21-9a7b2c3d4e5f"


def _report(aws, upload_id: str = UPLOAD) -> dict:
    body = aws.s3.get_object(Bucket=BUCKET, Key=f"reports/{upload_id}.json")["Body"].read()
    return json.loads(body)


def _keys(aws, prefix: str) -> list[str]:
    response = aws.s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix)
    return [item["Key"] for item in response.get("Contents", [])]


def _season_matches(aws) -> list[dict]:
    items = aws.matches.scan()["Items"]
    return [item for item in items if item["pk"].startswith("SEASON#")]


def test_valid_file_writes_matches_queues_summaries_and_archives(aws):
    key = put_upload(aws.s3, UPLOAD, fixture_bytes("fecha-05-valida.csv"))

    ingest_handler(s3_event(key), None)

    assert len(_season_matches(aws)) == 5
    report = _report(aws)
    assert report["status"] == "PROCESSED"
    assert (report["matches_written"], report["messages_enqueued"]) == (5, 5)
    assert len(drain_queue(aws.sqs, aws.queue_url)) == 5
    assert _keys(aws, "processed/") == [f"processed/{UPLOAD}.csv"]
    assert _keys(aws, "incoming/") == []


def test_invalid_file_is_rejected_with_a_report_and_writes_nothing(aws):
    key = put_upload(aws.s3, UPLOAD, fixture_bytes("fecha-05-fecha-invalida.csv"))

    ingest_handler(s3_event(key), None)

    report = _report(aws)
    assert report["status"] == "REJECTED"
    assert [(error["code"], error["line"]) for error in report["errors"]] == [("DATE_INVALID", 3)]
    assert _season_matches(aws) == []
    assert drain_queue(aws.sqs, aws.queue_url) == []
    assert _keys(aws, "rejected/") == [f"rejected/{UPLOAD}.csv"]


def test_repeated_event_after_archiving_is_a_no_op(aws):
    key = put_upload(aws.s3, UPLOAD, fixture_bytes("fecha-05-valida.csv"))
    ingest_handler(s3_event(key), None)

    ingest_handler(s3_event(key), None)

    assert len(_season_matches(aws)) == 5
    assert len(drain_queue(aws.sqs, aws.queue_url)) == 5


def test_uploading_the_same_file_again_writes_and_queues_nothing(aws):
    key = put_upload(aws.s3, UPLOAD, fixture_bytes("fecha-05-valida.csv"))
    ingest_handler(s3_event(key), None)
    summary_handler(sqs_event(*drain_queue(aws.sqs, aws.queue_url)), None)

    key_again = put_upload(aws.s3, SECOND_UPLOAD, fixture_bytes("fecha-05-valida.csv"))
    ingest_handler(s3_event(key_again), None)

    report = _report(aws, SECOND_UPLOAD)
    assert (report["matches_written"], report["messages_enqueued"]) == (0, 0)
    assert len(_season_matches(aws)) == 5


def test_changed_score_updates_only_that_match_and_requests_a_new_summary(aws):
    key = put_upload(aws.s3, UPLOAD, fixture_bytes("fecha-05-valida.csv"))
    ingest_handler(s3_event(key), None)
    summary_handler(sqs_event(*drain_queue(aws.sqs, aws.queue_url)), None)

    corrected = csv_bytes("liga-profesional,2026,5,2026-03-14,Boca Juniors,River Plate,3,1")
    key_again = put_upload(aws.s3, SECOND_UPLOAD, corrected)
    ingest_handler(s3_event(key_again), None)

    report = _report(aws, SECOND_UPLOAD)
    assert (report["matches_written"], report["messages_enqueued"]) == (1, 1)
    assert len(_season_matches(aws)) == 5
    boca = next(item for item in _season_matches(aws) if item["home_team"] == "Boca Juniors")
    assert boca["home_goals"] == 3
    assert boca["summary_status"] == "PENDING"


def test_failed_queue_send_is_retried_by_the_next_run(aws, monkeypatch):
    key = put_upload(aws.s3, UPLOAD, fixture_bytes("fecha-05-valida.csv"))
    missing_queue = "https://sqs.us-east-1.amazonaws.com/123456789012/no-existe"
    monkeypatch.setenv("SUMMARY_QUEUE_URL", missing_queue)

    with pytest.raises(ClientError):
        ingest_handler(s3_event(key), None)
    assert _keys(aws, "incoming/") == [key]

    monkeypatch.setenv("SUMMARY_QUEUE_URL", aws.queue_url)
    ingest_handler(s3_event(key), None)

    assert _report(aws)["messages_enqueued"] == 5
    assert len(drain_queue(aws.sqs, aws.queue_url)) == 5
