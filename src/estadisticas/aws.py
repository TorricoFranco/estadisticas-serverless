"""Clientes de AWS reutilizados entre invocaciones: se crean una vez por contenedor de Lambda."""

from typing import Any

import boto3

_clients: dict[str, Any] = {}
_resources: dict[str, Any] = {}


def client(service: str) -> Any:
    if service not in _clients:
        _clients[service] = boto3.client(service)
    return _clients[service]


def dynamodb_table(name: str) -> Any:
    if "dynamodb" not in _resources:
        _resources["dynamodb"] = boto3.resource("dynamodb")
    return _resources["dynamodb"].Table(name)


def reset_clients() -> None:
    """Olvida los clientes guardados. Las pruebas lo llaman para arrancar limpias."""
    _clients.clear()
    _resources.clear()
