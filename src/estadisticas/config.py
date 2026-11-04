"""Configuración de las funciones: variables de entorno y parámetros de SSM."""

import os
import time
from dataclasses import dataclass

from estadisticas.aws import client

MAX_RECEIVE_COUNT = 3
DAILY_LIMIT_PARAM = "/estadisticas/upload/daily-limit"
_PARAM_TTL_SECONDS = 300
_param_cache: dict[str, tuple[float, str]] = {}


@dataclass(frozen=True)
class Settings:
    matches_table: str
    standings_table: str
    uploads_bucket: str
    summary_queue_url: str


def load_settings() -> Settings:
    """Lee los nombres de recursos en cada invocación, para que las pruebas puedan cambiarlos."""
    return Settings(
        matches_table=os.environ["MATCHES_TABLE"],
        standings_table=os.environ["STANDINGS_TABLE"],
        uploads_bucket=os.environ["UPLOADS_BUCKET"],
        summary_queue_url=os.environ["SUMMARY_QUEUE_URL"],
    )


def read_parameter(name: str) -> str:
    """Lee un parámetro de SSM con caché de 5 minutos (sección 10.5 del ERS)."""
    now = time.monotonic()
    cached = _param_cache.get(name)
    if cached is not None and now - cached[0] < _PARAM_TTL_SECONDS:
        return cached[1]
    value = client("ssm").get_parameter(Name=name)["Parameter"]["Value"]
    _param_cache[name] = (now, value)
    return value


def clear_parameter_cache() -> None:
    _param_cache.clear()
