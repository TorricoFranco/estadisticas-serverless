"""Handler de resúmenes: consume la cola de resúmenes y escribe cada resumen (RF-09)."""

import json
from datetime import UTC, datetime
from typing import Any

from estadisticas import repository
from estadisticas.aws import dynamodb_table
from estadisticas.config import MAX_RECEIVE_COUNT, load_settings
from estadisticas.logs import log
from estadisticas.summaries import build_summary

FUNCTION = "estadisticas-summary"
MESSAGE_SCHEMA_VERSION = 1
MESSAGE_TYPE = "match.summary.requested"


def summary_handler(event: dict[str, Any], context: object) -> None:
    table = dynamodb_table(load_settings().matches_table)
    for record in event["Records"]:
        message = json.loads(record["body"])
        attempt = int(record["attributes"]["ApproximateReceiveCount"])
        try:
            _process(table, message)
        except Exception:
            # En el último intento el partido queda en FAILED antes de que el mensaje vaya a la DLQ.
            if attempt >= MAX_RECEIVE_COUNT:
                _mark_failed(table, message)
            raise


def _process(table: Any, message: dict[str, Any]) -> None:
    if (
        message.get("schema_version") != MESSAGE_SCHEMA_VERSION
        or message.get("type") != MESSAGE_TYPE
    ):
        raise ValueError("Mensaje de resumen con formato desconocido.")
    pk, sk = _keys(message)
    item = repository.get_match(table, pk, sk)
    if item is None or item["data_hash"] != message["data_hash"]:
        log("INFO", FUNCTION, "summary_skipped_stale", match_id=message["match_id"])
        return
    summary = build_summary(repository.match_from_item(item))
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    if repository.mark_summary_ready(table, pk, sk, summary, message["data_hash"], stamp):
        log("INFO", FUNCTION, "summary_ready", match_id=message["match_id"])
    else:
        log("INFO", FUNCTION, "summary_skipped_stale", match_id=message["match_id"])


def _mark_failed(table: Any, message: dict[str, Any]) -> None:
    pk, sk = _keys(message)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    repository.mark_summary_failed(table, pk, sk, message["data_hash"], stamp)
    log("ERROR", FUNCTION, "summary_failed", match_id=message["match_id"])


def _keys(message: dict[str, Any]) -> tuple[str, str]:
    pk = repository.season_pk(message["competition"], int(message["season"]))
    sk = repository.matchday_sk(int(message["matchday"]), message["match_id"])
    return pk, sk
