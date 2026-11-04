"""Acceso a DynamoDB: partidos, tabla, temporadas y cuota diaria (sección 7 del ERS)."""

from collections.abc import Iterable
from dataclasses import asdict
from datetime import date
from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from estadisticas.models import Match
from estadisticas.standings import StandingRow

SEASONS_PK = "SYSTEM#SEASONS"
QUOTA_PK = "SYSTEM#QUOTA"
SUMMARY_SOURCE = "template"

_MATCHDAY_PREFIX = "MATCHDAY#"
_TEAM_PREFIX = "TEAM#"
_CONDITION_FAILED = "ConditionalCheckFailedException"


def season_pk(competition: str, season: int) -> str:
    return f"SEASON#{competition}#{season}"


def matchday_sk(matchday: int, match_id: str) -> str:
    return f"{_MATCHDAY_PREFIX}{matchday:02d}#{match_id}"


def save_match(table: Any, match: Match, upload_id: str, updated_at: str) -> tuple[bool, bool]:
    """Upsert de un partido. Devuelve (escrito, hay_que_pedir_resumen) (RF-05 y RF-06).

    Si los datos no cambiaron, la condición falla y no se escribe nada. En ese caso el
    resumen se pide solo si el último generado no corresponde a estos datos.
    """
    pk = season_pk(match.competition, match.season)
    sk = matchday_sk(match.matchday, match.match_id)
    data_hash = match.data_hash
    values: dict[str, Any] = {
        "competition": match.competition,
        "season": match.season,
        "matchday": match.matchday,
        "match_id": match.match_id,
        "match_date": match.match_date.isoformat(),
        "home_team": match.home_team,
        "home_team_id": match.home_team_id,
        "away_team": match.away_team,
        "away_team_id": match.away_team_id,
        "home_goals": match.home_goals,
        "away_goals": match.away_goals,
        "data_hash": data_hash,
        "summary_status": "PENDING",
        "upload_id": upload_id,
        "updated_at": updated_at,
    }
    names = {f"#a{i}": name for i, name in enumerate(values)}
    placeholders = {f":v{i}": value for i, value in enumerate(values.values())}
    assignments = ", ".join(f"#a{i} = :v{i}" for i in range(len(values)))
    try:
        table.update_item(
            Key={"pk": pk, "sk": sk},
            UpdateExpression=f"SET {assignments}",
            ConditionExpression="attribute_not_exists(#pk) OR #hash <> :hash",
            ExpressionAttributeNames={**names, "#pk": "pk", "#hash": "data_hash"},
            ExpressionAttributeValues={**placeholders, ":hash": data_hash},
        )
        return True, True
    except ClientError as error:
        if error.response["Error"]["Code"] != _CONDITION_FAILED:
            raise
    current = table.get_item(Key={"pk": pk, "sk": sk}, ConsistentRead=True).get("Item", {})
    return False, current.get("summary_data_hash") != data_hash


def mark_summary_ready(
    table: Any,
    pk: str,
    sk: str,
    summary: str,
    data_hash: str,
    updated_at: str,
) -> bool:
    """Guarda el resumen solo si el partido sigue con estos datos. False si el mensaje era viejo."""
    try:
        table.update_item(
            Key={"pk": pk, "sk": sk},
            UpdateExpression=(
                "SET #summary = :summary, #status = :ready, #source = :source, "
                "#sdh = :hash, #updated = :now"
            ),
            ConditionExpression="#dh = :hash",
            ExpressionAttributeNames={
                "#summary": "summary",
                "#status": "summary_status",
                "#source": "summary_source",
                "#sdh": "summary_data_hash",
                "#dh": "data_hash",
                "#updated": "updated_at",
            },
            ExpressionAttributeValues={
                ":summary": summary,
                ":ready": "READY",
                ":source": SUMMARY_SOURCE,
                ":hash": data_hash,
                ":now": updated_at,
            },
        )
    except ClientError as error:
        if error.response["Error"]["Code"] == _CONDITION_FAILED:
            return False
        raise
    return True


def mark_summary_failed(table: Any, pk: str, sk: str, data_hash: str, updated_at: str) -> None:
    """Marca el resumen como FAILED, solo si el partido sigue con estos datos."""
    try:
        table.update_item(
            Key={"pk": pk, "sk": sk},
            UpdateExpression="SET #status = :failed, #updated = :now",
            ConditionExpression="#dh = :hash",
            ExpressionAttributeNames={
                "#status": "summary_status",
                "#updated": "updated_at",
                "#dh": "data_hash",
            },
            ExpressionAttributeValues={":failed": "FAILED", ":now": updated_at, ":hash": data_hash},
        )
    except ClientError as error:
        if error.response["Error"]["Code"] != _CONDITION_FAILED:
            raise


def get_match(table: Any, pk: str, sk: str) -> dict[str, Any] | None:
    return table.get_item(Key={"pk": pk, "sk": sk}, ConsistentRead=True).get("Item")


def match_from_item(item: dict[str, Any]) -> Match:
    return Match(
        competition=item["competition"],
        season=int(item["season"]),
        matchday=int(item["matchday"]),
        match_date=date.fromisoformat(item["match_date"]),
        home_team=item["home_team"],
        home_team_id=item["home_team_id"],
        away_team=item["away_team"],
        away_team_id=item["away_team_id"],
        home_goals=int(item["home_goals"]),
        away_goals=int(item["away_goals"]),
    )


def query_matchday(table: Any, pk: str, matchday: int) -> list[dict[str, Any]]:
    condition = Key("pk").eq(pk) & Key("sk").begins_with(f"{_MATCHDAY_PREFIX}{matchday:02d}#")
    return _query_all(table, KeyConditionExpression=condition)


def list_season_matches(table: Any, pk: str) -> list[dict[str, Any]]:
    condition = Key("pk").eq(pk) & Key("sk").begins_with(_MATCHDAY_PREFIX)
    return _query_all(table, KeyConditionExpression=condition)


def query_season_page(
    table: Any,
    pk: str,
    limit: int,
    start_key: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Una página de partidos de la temporada, en orden de fecha (GET /partidos sin matchday)."""
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": Key("pk").eq(pk) & Key("sk").begins_with(_MATCHDAY_PREFIX),
        "Limit": limit,
    }
    if start_key is not None:
        kwargs["ExclusiveStartKey"] = start_key
    response = table.query(**kwargs)
    return response.get("Items", []), response.get("LastEvaluatedKey")


def query_standings(table: Any, pk: str) -> list[dict[str, Any]]:
    return _query_all(table, KeyConditionExpression=Key("pk").eq(pk))


def save_standings(table: Any, pk: str, rows: Iterable[StandingRow], computed_at: str) -> None:
    """Reemplaza la tabla de una temporada: escribe los equipos actuales y borra los que sobran."""
    rows = list(rows)
    keep = {f"{_TEAM_PREFIX}{row.team_id}" for row in rows}
    stale = [item["sk"] for item in query_standings(table, pk) if item["sk"] not in keep]
    with table.batch_writer() as batch:
        for row in rows:
            batch.put_item(
                Item={
                    **asdict(row),
                    "pk": pk,
                    "sk": f"{_TEAM_PREFIX}{row.team_id}",
                    "computed_at": computed_at,
                }
            )
        for sk in stale:
            batch.delete_item(Key={"pk": pk, "sk": sk})


def list_seasons(table: Any) -> list[tuple[str, int]]:
    items = _query_all(table, KeyConditionExpression=Key("pk").eq(SEASONS_PK))
    return [(item["competition"], int(item["season"])) for item in items]


def register_season(table: Any, competition: str, season: int, updated_at: str) -> None:
    table.put_item(
        Item={
            "pk": SEASONS_PK,
            "sk": f"SEASON#{competition}#{season}",
            "competition": competition,
            "season": season,
            "updated_at": updated_at,
        }
    )


def increment_daily_uploads(table: Any, day: str, limit: int, expires_at: int) -> bool:
    """Suma una subida al día. Devuelve False si el día ya llegó al límite (cuota de NFR-02)."""
    try:
        table.update_item(
            Key={"pk": QUOTA_PK, "sk": f"UPLOADS#{day}"},
            UpdateExpression="ADD #count :one SET #expires = :expires",
            ConditionExpression="attribute_not_exists(#count) OR #count < :limit",
            ExpressionAttributeNames={"#count": "count", "#expires": "expires_at"},
            ExpressionAttributeValues={":one": 1, ":limit": limit, ":expires": expires_at},
        )
    except ClientError as error:
        if error.response["Error"]["Code"] == _CONDITION_FAILED:
            return False
        raise
    return True


def _query_all(table: Any, **kwargs: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    while True:
        response = table.query(**kwargs)
        items.extend(response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if last_key is None:
            return items
        kwargs["ExclusiveStartKey"] = last_key
