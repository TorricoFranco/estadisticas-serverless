"""POST /uploads: genera la URL firmada para subir un CSV a S3 (RF-01 y sección 8.2 del ERS)."""

import json
import re
import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any

from estadisticas import repository
from estadisticas.aws import client, dynamodb_table
from estadisticas.config import DAILY_LIMIT_PARAM, load_settings, read_parameter
from estadisticas.csv_validation import MAX_FILE_BYTES
from estadisticas.handlers.http import ApiError, api_handler

FUNCTION = "estadisticas-upload-url"
CONTENT_TYPE = "text/csv"
UPLOAD_EXPIRES_SECONDS = 300
MAX_BODY_BYTES = 1024
FILENAME_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,96}\.csv")
QUOTA_TTL = timedelta(days=2)


@api_handler(FUNCTION)
def upload_url_handler(event: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    _validate_body(event.get("body") or "")
    settings = load_settings()
    today = datetime.now(UTC).date()
    expires_at = int((datetime.combine(today, time.min, tzinfo=UTC) + QUOTA_TTL).timestamp())
    limit = int(read_parameter(DAILY_LIMIT_PARAM))
    allowed = repository.increment_daily_uploads(
        dynamodb_table(settings.matches_table),
        today.isoformat(),
        limit,
        expires_at,
    )
    if not allowed:
        raise ApiError(
            429,
            "DAILY_QUOTA_EXCEEDED",
            f"Se alcanzó la cuota diaria de {limit} subidas.",
        )

    upload_id = str(uuid.uuid4())
    post = client("s3").generate_presigned_post(
        Bucket=settings.uploads_bucket,
        Key=f"incoming/{upload_id}.csv",
        Fields={"Content-Type": CONTENT_TYPE},
        Conditions=[
            {"Content-Type": CONTENT_TYPE},
            ["content-length-range", 1, MAX_FILE_BYTES],
        ],
        ExpiresIn=UPLOAD_EXPIRES_SECONDS,
    )
    return 201, {
        "upload_id": upload_id,
        "expires_in": UPLOAD_EXPIRES_SECONDS,
        "upload": {"url": post["url"], "fields": post["fields"]},
    }


def _validate_body(raw: str) -> None:
    if len(raw.encode("utf-8")) > MAX_BODY_BYTES:
        raise ApiError(413, "PAYLOAD_TOO_LARGE", "El cuerpo de la solicitud supera 1 KB.")
    try:
        payload = json.loads(raw or "null")
    except ValueError:
        raise ApiError(400, "VALIDATION_ERROR", "El cuerpo debe ser JSON válido.") from None
    if not isinstance(payload, dict) or set(payload) != {"filename", "content_type"}:
        raise ApiError(
            400,
            "VALIDATION_ERROR",
            "El cuerpo debe tener solo los campos filename y content_type.",
        )
    filename = payload["filename"]
    if not isinstance(filename, str) or FILENAME_PATTERN.fullmatch(filename) is None:
        raise ApiError(
            400,
            "VALIDATION_ERROR",
            "filename debe terminar en .csv, tener hasta 100 caracteres y usar solo "
            "letras, números, puntos, guiones y guiones bajos.",
        )
    if payload["content_type"] != CONTENT_TYPE:
        raise ApiError(400, "VALIDATION_ERROR", "content_type debe ser text/csv.")
