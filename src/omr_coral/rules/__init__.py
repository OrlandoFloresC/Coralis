"""Musical validation rules. Each rule takes (score, cfg) and returns a list of Issues."""

from __future__ import annotations

from ..model.issues import Issue
from ..model.score import ChoralScore
from . import accidentals, consistency, duration, lyrics, melody, ranges, unison

RULES = {
    "duracion": duration.check,
    "rango": ranges.check,
    "coherencia": consistency.check,
    "alteraciones": accidentals.check,
    "letra": lyrics.check,
    "unisono": unison.check,
    "melodia": melody.check,
}

RULE_LABELS = {
    "duracion": "Duración del compás",
    "rango": "Fuera de rango",
    "coherencia": "Coherencia entre voces",
    "alteraciones": "Alteración sospechosa",
    "letra": "Sílabas de la letra",
    "unisono": "Voz perdida o copiada",
    "melodia": "Salto o ligadura improbable",
    "estructura": "Estructura",
    "votacion": "Lecturas en desacuerdo",
    "sintesis": "No coincide con la imagen",
    "repeticion": "Repetición o salto sin destino",
}


def run_rules(score: ChoralScore, cfg: dict) -> list[Issue]:
    enabled = cfg.get("rules", {}).get("enabled", list(RULES))
    issues = list(score.issues)
    for name in enabled:
        issues += RULES[name](score, cfg)
    return issues
