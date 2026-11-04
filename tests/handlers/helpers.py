"""Constructores de eventos y datos para las pruebas de handlers: S3, SQS y API Gateway."""

import json
from pathlib import Path
from typing import Any

REGION = "us-east-1"
BUCKET = "estadisticas-uploads-test"
MATCHES_TABLE = "estadisticas-matches"
STANDINGS_TABLE = "estadisticas-standings"
QUEUE_NAME = "estadisticas-summary"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CSV_HEADER = "competition,season,matchday,match_date,home_team,away_team,home_goals,away_goals"


def fixture_bytes(relative: str) -> bytes:
    return (FIXTURES / relative).read_bytes()


def csv_bytes(*rows: str) -> bytes:
    return "\n".join((CSV_HEADER, *rows)).encode("utf-8")


def put_upload(s3: Any, upload_id: str, content: bytes) -> str:
    """Sube un CSV a `incoming/` como lo haría la URL firmada y devuelve su clave."""
    key = f"incoming/{upload_id}.csv"
    s3.put_object(Bucket=BUCKET, Key=key, Body=content)
    return key


def s3_event(key: str) -> dict[str, Any]:
    return {"Records": [{"s3": {"bucket": {"name": BUCKET}, "object": {"key": key}}}]}


def sqs_event(*bodies: dict[str, Any], receive_count: int = 1) -> dict[str, Any]:
    return {
        "Records": [
            {
                "body": json.dumps(body),
                "attributes": {"ApproximateReceiveCount": str(receive_count)},
            }
            for body in bodies
        ]
    }


def drain_queue(sqs: Any, queue_url: str) -> list[dict[str, Any]]:
    """Recibe todos los mensajes disponibles y devuelve sus cuerpos decodificados."""
    bodies: list[dict[str, Any]] = []
    while True:
        response = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10)
        messages = response.get("Messages", [])
        if not messages:
            return bodies
        bodies.extend(json.loads(message["Body"]) for message in messages)


def http_event(query: dict[str, str] | None = None, body: str | None = None) -> dict[str, Any]:
    return {
        "requestContext": {"requestId": "req-test"},
        "queryStringParameters": query,
        "body": body,
    }


def body_of(response: dict[str, Any]) -> dict[str, Any]:
    return json.loads(response["body"])
