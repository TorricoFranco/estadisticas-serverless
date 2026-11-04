"""Piezas comunes de las rutas HTTP: respuestas, errores y validación de parámetros (sección 8)."""

import functools
import json
import re
from collections.abc import Callable
from typing import Any

from estadisticas.logs import log
from estadisticas.normalization import is_valid_competition, parse_season

_DIGITS = re.compile(r"[0-9]+")


class ApiError(Exception):
    """Error que se devuelve al cliente, con su código HTTP y su código de error (sección 8.5)."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def api_handler(function_name: str) -> Callable[..., Callable[..., dict[str, Any]]]:
    """Convierte `(event) -> (status, body)` en un handler de API Gateway con errores uniformes."""

    def decorator(
        handler: Callable[[dict[str, Any]], tuple[int, dict[str, Any]]],
    ) -> Callable[..., dict[str, Any]]:
        @functools.wraps(handler)
        def wrapper(event: dict[str, Any], context: object) -> dict[str, Any]:
            request_id = request_id_from(event)
            try:
                status, body = handler(event)
            except ApiError as error:
                return _error(error.status, error.code, error.message, request_id)
            except Exception as error:
                log(
                    "ERROR",
                    function_name,
                    "unhandled_error",
                    request_id=request_id,
                    error_type=type(error).__name__,
                )
                return _error(500, "INTERNAL_ERROR", "Ocurrió un error interno.", request_id)
            return _respond(status, body, request_id)

        return wrapper

    return decorator


def request_id_from(event: dict[str, Any]) -> str:
    return str(event.get("requestContext", {}).get("requestId", ""))


def query_params(event: dict[str, Any]) -> dict[str, str]:
    return dict(event.get("queryStringParameters") or {})


def competition_and_season(params: dict[str, str]) -> tuple[str, int]:
    competition = params.get("competition", "")
    if not is_valid_competition(competition):
        raise ApiError(
            400,
            "VALIDATION_ERROR",
            "El parámetro competition debe tener de 2 a 40 caracteres: "
            "minúsculas, números y guiones.",
        )
    season = parse_season(params.get("season", ""))
    if season is None:
        raise ApiError(
            400,
            "VALIDATION_ERROR",
            "El parámetro season debe ser un año entre 2000 y 2100.",
        )
    return competition, season


def optional_int(
    params: dict[str, str],
    name: str,
    lowest: int,
    highest: int,
    default: int | None = None,
) -> int | None:
    raw = params.get(name)
    if raw is None:
        return default
    if _DIGITS.fullmatch(raw) is None or not lowest <= int(raw) <= highest:
        raise ApiError(
            400,
            "VALIDATION_ERROR",
            f"El parámetro {name} debe ser un entero entre {lowest} y {highest}.",
        )
    return int(raw)


def _respond(status: int, body: dict[str, Any], request_id: str) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json; charset=utf-8", "X-Request-Id": request_id},
        "body": json.dumps(body, ensure_ascii=False),
    }


def _error(status: int, code: str, message: str, request_id: str) -> dict[str, Any]:
    body = {"error": {"code": code, "message": message, "request_id": request_id}}
    return _respond(status, body, request_id)
