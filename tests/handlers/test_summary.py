"""Pruebas del handler de resúmenes (RF-09 y RF-11)."""

import pytest
from helpers import drain_queue, fixture_bytes, put_upload, s3_event, sqs_event

from estadisticas.handlers.ingest import ingest_handler
from estadisticas.handlers.summary import summary_handler
from estadisticas.repository import matchday_sk, season_pk

UPLOAD = "5d2c8f1e-7a3b-4c2d-9e10-8f6a1b2c3d4e"


def _load_fixture_matches(aws) -> list[dict]:
    """Ingiere la fecha 5 y devuelve los cuerpos de los mensajes de resumen que dejó."""
    key = put_upload(aws.s3, UPLOAD, fixture_bytes("fecha-05-valida.csv"))
    ingest_handler(s3_event(key), None)
    return drain_queue(aws.sqs, aws.queue_url)


def _item(aws, message: dict) -> dict:
    key = {
        "pk": season_pk(message["competition"], message["season"]),
        "sk": matchday_sk(message["matchday"], message["match_id"]),
    }
    return aws.matches.get_item(Key=key)["Item"]


def test_each_match_gets_its_template_summary(aws):
    messages = _load_fixture_matches(aws)

    summary_handler(sqs_event(*messages), None)

    statuses = {_item(aws, message)["summary_status"] for message in messages}
    assert statuses == {"READY"}
    summaries = {
        _item(aws, message)["home_team"]: _item(aws, message)["summary"] for message in messages
    }
    assert summaries["Boca Juniors"] == "Boca Juniors 2-1 River Plate: ganó el local (fecha 5)."
    assert summaries["Gimnasia"] == "Gimnasia 0-3 Estudiantes: ganó el visitante (fecha 5)."
    assert summaries["Racing Club"] == "Racing Club 0-0 Independiente: empate (fecha 5)."


def test_duplicate_delivery_leaves_the_same_summary(aws):
    messages = _load_fixture_matches(aws)
    summary_handler(sqs_event(*messages), None)
    first = _item(aws, messages[0])["summary"]

    summary_handler(sqs_event(*messages), None)

    assert _item(aws, messages[0])["summary"] == first
    assert _item(aws, messages[0])["summary_status"] == "READY"


def test_stale_message_is_ignored(aws):
    messages = _load_fixture_matches(aws)
    stale = {**messages[0], "data_hash": "0" * 64}

    summary_handler(sqs_event(stale), None)

    assert _item(aws, messages[0])["summary_status"] == "PENDING"
    assert "summary" not in _item(aws, messages[0])


def test_failed_attempts_raise_and_only_the_last_one_marks_the_match_as_failed(aws, monkeypatch):
    messages = _load_fixture_matches(aws)

    def broken(match):
        raise RuntimeError("falla simulada")

    monkeypatch.setattr("estadisticas.handlers.summary.build_summary", broken)

    with pytest.raises(RuntimeError):
        summary_handler(sqs_event(messages[0], receive_count=1), None)
    assert _item(aws, messages[0])["summary_status"] == "PENDING"

    with pytest.raises(RuntimeError):
        summary_handler(sqs_event(messages[0], receive_count=3), None)
    assert _item(aws, messages[0])["summary_status"] == "FAILED"
