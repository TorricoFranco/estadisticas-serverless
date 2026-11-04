"""Identificadores estables y hashes de los partidos (sección 7.4 del ERS)."""

import hashlib
import json


def match_id_for(
    competition: str,
    season: int,
    matchday: int,
    home_team_id: str,
    away_team_id: str,
) -> str:
    """Los 16 primeros caracteres hexadecimales del SHA-256 de la clave del partido.

    El orden de local y visitante importa: el mismo cruce al revés es otro partido.
    """
    source = f"{competition}|{season}|{matchday}|{home_team_id}|{away_team_id}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def data_hash_for(
    match_date: str,
    home_team: str,
    away_team: str,
    home_goals: int,
    away_goals: int,
) -> str:
    """SHA-256 del JSON canónico con los datos del partido."""
    payload = {
        "away_goals": away_goals,
        "away_team": away_team,
        "home_goals": home_goals,
        "home_team": home_team,
        "match_date": match_date,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
