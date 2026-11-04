"""Smoke test de la demo desplegada (RF-16 del ERS).

Sube una fecha de ejemplo, espera a que sus partidos tengan resumen y consulta la tabla.
Uso: python scripts/smoke_test.py --api-url https://<api-id>.execute-api.us-east-1.amazonaws.com
Las credenciales de AWS salen de la cadena normal de boto3 (perfil, variables o rol).
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

REGION = "us-east-1"
COMPETITION = "liga-profesional"
SEASON = 2026
MATCHDAY = 5
EXPECTED_MATCHES = 5  # Partidos de tests/fixtures/fecha-05-valida.csv.
FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "fecha-05-valida.csv"


class SmokeTestError(Exception):
    """Un paso de la demo no se cumplió. El mensaje explica qué falló."""


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--api-url", required=True, help="URL base de la API, sin barra final.")
    parser.add_argument(
        "--timeout", type=int, default=180, help="Segundos a esperar los resúmenes."
    )
    args = parser.parse_args(argv)
    api = args.api_url.rstrip("/")
    try:
        _run(api, args.timeout)
    except SmokeTestError as error:
        print(f"FALLÓ: {error}", file=sys.stderr)
        return 1
    print("OK: la demo responde y la fecha de ejemplo quedó cargada.")
    return 0


def _run(api: str, timeout: int) -> None:
    started = time.monotonic()
    upload = _request_upload(api)
    _upload_csv(upload)
    print(f"Subida aceptada en {time.monotonic() - started:.1f} s.")

    waited = time.monotonic()
    _wait_for_summaries(api, timeout)
    print(f"Partidos con resumen READY en {time.monotonic() - waited:.1f} s.")

    table = _get_json(f"{api}/tabla?{_season_query()}")
    if not table.get("items"):
        raise SmokeTestError("GET /tabla no devolvió equipos para la temporada de ejemplo.")
    print(f"Tabla con {len(table['items'])} equipos, calculada el {table['computed_at']}.")


def _request_upload(api: str) -> dict:
    body = json.dumps({"filename": "fecha-05.csv", "content_type": "text/csv"}).encode("utf-8")
    headers = _sigv4_headers(f"{api}/uploads", "POST", body)
    response = _send(urllib.request.Request(f"{api}/uploads", data=body, headers=headers))
    return json.loads(response)["upload"]


def _upload_csv(upload: dict) -> None:
    content = FIXTURE.read_bytes()
    body, content_type = _multipart(upload["fields"], FIXTURE.name, content)
    request = urllib.request.Request(
        upload["url"],
        data=body,
        headers={"Content-Type": content_type},
        method="POST",
    )
    try:
        _send(request)
    except SmokeTestError as error:
        raise SmokeTestError(f"S3 rechazó la subida del CSV: {error}") from None


def _wait_for_summaries(api: str, timeout: int) -> None:
    deadline = time.monotonic() + timeout
    while True:
        items = _get_json(f"{api}/partidos?{_season_query()}&matchday={MATCHDAY}")["items"]
        ready = [item for item in items if item["summary_status"] == "READY"]
        if len(items) == EXPECTED_MATCHES and len(ready) == EXPECTED_MATCHES:
            return
        if time.monotonic() > deadline:
            raise SmokeTestError(
                f"Después de {timeout} s hay {len(items)} partidos y {len(ready)} con resumen "
                f"READY (se esperaban {EXPECTED_MATCHES}). Revisar los logs de la ingesta."
            )
        time.sleep(5)


def _season_query() -> str:
    return urllib.parse.urlencode({"competition": COMPETITION, "season": SEASON})


def _get_json(url: str) -> dict:
    return json.loads(_send(urllib.request.Request(url)))


def _send(request: urllib.request.Request) -> str:
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:300]
        raise SmokeTestError(f"HTTP {error.code} en {request.full_url}: {detail}") from None
    except urllib.error.URLError as error:
        raise SmokeTestError(f"No se pudo conectar a {request.full_url}: {error.reason}") from None


def _sigv4_headers(url: str, method: str, body: bytes) -> dict[str, str]:
    credentials = boto3.Session(region_name=REGION).get_credentials()
    if credentials is None:
        raise SmokeTestError(
            "No hay credenciales de AWS. Configurar un perfil o variables de entorno."
        )
    request = AWSRequest(
        method=method,
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    SigV4Auth(credentials.get_frozen_credentials(), "execute-api", REGION).add_auth(request)
    return dict(request.headers.items())


def _multipart(fields: dict[str, str], filename: str, content: bytes) -> tuple[bytes, str]:
    """Arma el cuerpo multipart/form-data que espera el presigned POST de S3."""
    boundary = uuid.uuid4().hex
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        for name, value in fields.items()
    ]
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: text/csv\r\n\r\n".encode()
        + content
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
