"""Refine the voted score by comparing it with the image (analysis by synthesis).

For each measure whose noteheads do not fully match the image, try the other
versions the readings offered for each voice, one voice at a time. A version
replaces the current one only if
  - it explains more of the noteheads printed in the image,
  - the measure clearly looks more like the image (similarity +min_gain),
  - it does not break more rules than the current one.
Passes repeat until nothing improves.
"""

from __future__ import annotations

import copy
from pathlib import Path

from ..model.issues import Issue
from ..model.score import PARTNER, VOICES, ChoralScore, Event
from .compare import Geometry, compare

_VOICE_ES = {"soprano": "soprano", "alto": "contralto", "tenor": "tenor/barítono", "bass": "bajo"}


def geometry_of(m) -> Geometry | None:
    g = m.geometry
    if not g or not m.geometry_dir:
        return None
    image = Path(m.geometry_dir) / f"page_{g['page']:03d}.png"
    if not image.exists():
        return None
    return Geometry(image, g["x0"], g["x1"], [tuple(s) for s in g["staves"]], list(g["clefs"]))


def _move_lyrics(old: list[Event], new: list[Event]) -> list[Event]:
    """Carry the syllables of the replaced version over to the new notes."""
    new = copy.deepcopy(new)
    for e in new:
        e.lyrics = {}
    targets = {e.offset: e for e in new if e.is_attack}
    pending = []
    for e in old:
        if e.lyrics:
            if e.offset in targets:
                targets[e.offset].lyrics = dict(e.lyrics)
            else:
                pending.append(e.lyrics)
    free = [e for e in new if e.takes_syllable and not e.lyrics]
    for lyr, e in zip(pending, free):
        e.lyrics = dict(lyr)
    return new


def _shape(events: list[Event]) -> list[tuple]:
    return [(e.offset, e.duration, e.pitch) for e in events]


def _follow_partner(m, v: str, old: dict, new: dict) -> None:
    """The staff partner sang exactly what voice v had (a unison or a solo printed once: «El cielo es
    Jesús» c.2): it takes the new version too, when one of its readings has it."""
    p = PARTNER[v]
    if _shape(m.voices.get(p, [])) != _shape(m.voices[v]):
        return
    alts = m.alternatives.get(p, [])
    twin = next((a for a in alts if _shape(a["events"]) == _shape(new["events"])), None)
    if twin is None:
        return
    m.voices[p] = _move_lyrics(m.voices[p], twin["events"])
    for a in alts:
        a["chosen"] = a is twin


def _min_agreement(m) -> float:
    ratios = [d["weight"] / d["total"] for d in m.votes.values() if d.get("total")]
    return min(ratios) if ratios else 1.0


def refine(score: ChoralScore, cfg: dict) -> list[Issue]:
    opts = cfg.get("synthesis", {})
    if not opts.get("enabled", True):
        return []
    min_gain = opts.get("min_gain", 0.05)
    threshold = opts.get("min_similarity", 0.85)
    max_passes = opts.get("max_passes", 5)
    trust_agreement = opts.get("trust_agreement", 0.8)
    issues: list[Issue] = []

    for m in score.measures:
        geom = geometry_of(m)
        if geom is None:
            continue
        before = compare(m.voices, geom)
        current = before
        for _ in range(max_passes):
            improved = False
            for v in VOICES:
                alts = m.alternatives.get(v, [])
                cur = next((a for a in alts if a.get("chosen")), None)
                if not alts or cur is None:
                    continue
                # (almost) every reading agrees on this voice: the detector does not overrule them
                # («Mis culpas él llevó»: the pickup's lone quarter rest, 8 of 10 readings, became a
                # half-note A2 one reading saw — matching heads of the next measure)
                if cur["weight"] >= trust_agreement * sum(a["weight"] for a in alts):
                    continue
                best_alt, best_res = None, current
                for alt in alts:
                    if alt is cur or alt["errors"] > cur["errors"] or alt["avisos"] > cur["avisos"]:
                        continue
                    trial = dict(m.voices)
                    trial[v] = [e for e in alt["events"]]
                    res = compare(trial, geom)
                    # It must explain MORE printed heads, not just expect fewer: a version that
                    # merges a voice into a unison expects one head less, and would otherwise
                    # "win" whenever the detector missed that head.
                    if res.matched > best_res.matched and res.similarity >= best_res.similarity + min_gain:
                        best_alt, best_res = alt, res
                if best_alt is not None:
                    _follow_partner(m, v, cur, best_alt)
                    m.voices[v] = _move_lyrics(m.voices[v], best_alt["events"])
                    cur["chosen"], best_alt["chosen"] = False, True
                    m.votes[v] = {**m.votes.get(v, {}), "weight": best_alt["weight"],
                                  "sources": best_alt["sources"], "by_image": True}
                    issues.append(Issue(
                        "sintesis", "info",
                        f"Compás {m.label}: {_VOICE_ES[v]} cambiada por la versión de "
                        f"{', '.join(best_alt['sources'][:3])} porque coincide mejor con la imagen "
                        f"({current.similarity:.0%} → {best_res.similarity:.0%}).", m.index, v))
                    current = best_res
                    improved = True
            if not improved:
                break
        m.synth = current
        # The detector is imperfect: when (almost) every reading agrees, trust them over a
        # low similarity. The image only casts doubt where the readings disagree.
        if current.similarity < threshold and _min_agreement(m) < trust_agreement:
            parts = []
            if current.missing:
                parts.append(f"{len(current.missing)} nota(s) que no se ven en la imagen")
            if current.extra:
                parts.append(f"{len(current.extra)} cabeza(s) en la imagen sin explicar")
            issues.append(Issue(
                "sintesis", "aviso",
                f"Lo que entendió el programa coincide en un {current.similarity:.0%} con las cabezas de nota "
                f"de la imagen ({'; '.join(parts) or 'diferencias de posición'}). Revisa el panel de verificación.",
                m.index))
    return issues
