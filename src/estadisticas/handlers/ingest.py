"""Handler de ingesta: valida el CSV que llega a S3 y guarda sus partidos (RF-01 a RF-08)."""

import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote_plus

from botocore.exceptions import ClientError

from estadisticas import repository
from estadisticas.aws import client, dynamodb_table
from estadisticas.config import Settings, load_settings
from estadisticas.csv_validation import validate_csv
from estadisticas.logs import log
from estadisticas.models import Match
from estadisticas.reports import build_report

FUNCTION = "estadisticas-ingest"
INCOMING_PREFIX = "incoming/"
MESSAGE_SCHEMA_VERSION = 1
MESSAGE_TYPE = "match.summary.requested"


def ingest_handler(event: dict[str, Any], context: object) -> None:
    settings = load_settings()
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        if not key.startswith(INCOMING_PREFIX) or not key.endswith(".csv"):
            log("INFO", FUNCTION, "object_ignored", key=key)
            continue
        upload_id = key.removeprefix(INCOMING_PREFIX).removesuffix(".csv")
        _ingest(settings, bucket, key, upload_id)


def _ingest(settings: Settings, bucket: str, key: str, upload_id: str) -> None:
    s3 = client("s3")
    try:
        raw = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    except ClientError as error:
        # Un evento repetido llega después de que el archivo ya se archivó: no hay nada que hacer.
        if error.response["Error"]["Code"] == "NoSuchKey":
            log("INFO", FUNCTION, "upload_already_processed", upload_id=upload_id)
            return
        raise

    now = datetime.now(UTC)
    stamp = now.isoformat(timespec="seconds")
    result = validate_csv(raw, now.date())
    matches_written = 0
    messages = 0
    if result.is_valid:
        matches_table = dynamodb_table(settings.matches_table)
        for match in result.matches:
            written, needs_summary = repository.save_match(matches_table, match, upload_id, stamp)
            matches_written += int(written)
            if needs_summary:
                _request_summary(settings, match, upload_id, stamp)
                messages += 1
        seasons = sorted({(match.competition, match.season) for match in result.matches})
        for competition, season in seasons:
            repository.register_season(matches_table, competition, season, stamp)
        target = "processed"
    else:
        target = "rejected"

    report = build_report(upload_id, result, matches_written, messages)
    s3.put_object(
        Bucket=bucket,
        Key=f"reports/{upload_id}.json",
        Body=json.dumps(report, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )
    s3.copy_object(
        Bucket=bucket,
        CopySource={"Bucket": bucket, "Key": key},
        Key=f"{target}/{upload_id}.csv",
    )
    s3.delete_object(Bucket=bucket, Key=key)
    log(
        "INFO",
        FUNCTION,
        "upload_processed",
        upload_id=upload_id,
        status=report["status"],
        errors=len(result.errors),
        matches_written=matches_written,
        messages_enqueued=messages,
    )


def _request_summary(settings: Settings, match: Match, upload_id: str, stamp: str) -> None:
    body = {
        "schema_version": MESSAGE_SCHEMA_VERSION,
        "type": MESSAGE_TYPE,
        "match_id": match.match_id,
        "competition": match.competition,
        "season": match.season,
        "matchday": match.matchday,
        "data_hash": match.data_hash,
        "upload_id": upload_id,
        "requested_at": stamp,
    }
    client("sqs").send_message(
        QueueUrl=settings.summary_queue_url,
        MessageBody=json.dumps(body, ensure_ascii=False),
    )
