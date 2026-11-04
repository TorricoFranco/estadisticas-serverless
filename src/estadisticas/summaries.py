"""Resumen de cada partido con plantilla (RF-09)."""

from estadisticas.models import Match


def build_summary(match: Match) -> str:
    """Texto del resultado. Ejemplo: 'Boca Juniors 2-1 River Plate: ganó el local (fecha 5).'"""
    if match.home_goals > match.away_goals:
        outcome = "ganó el local"
    elif match.home_goals < match.away_goals:
        outcome = "ganó el visitante"
    else:
        outcome = "empate"
    score = f"{match.home_team} {match.home_goals}-{match.away_goals} {match.away_team}"
    return f"{score}: {outcome} (fecha {match.matchday})."
