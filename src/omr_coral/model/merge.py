"""Concatenate per-page recognition results into a single score."""

from __future__ import annotations

import copy
import shutil
from pathlib import Path

from music21 import converter, stream


def load_score(path: Path) -> stream.Score:
    s = converter.parse(str(path))
    if isinstance(s, stream.Opus):  # some exports wrap movements in an Opus
        s = s.scores[0] if len(s.scores) == 1 else _concat(list(s.scores))[0]
    return s


def _concat(scores: list[stream.Score]) -> tuple[stream.Score, list[str]]:
    warnings: list[str] = []
    base = copy.deepcopy(scores[0])
    base_parts = list(base.parts)
    next_number = {i: _last_number(p) + 1 for i, p in enumerate(base_parts)}
    for k, sc in enumerate(scores[1:], start=2):
        parts = list(sc.parts)
        if len(parts) != len(base_parts):
            warnings.append(
                f"Fragmento {k}: {len(parts)} partes frente a {len(base_parts)} en el primero; "
                "se unen por orden y las sobrantes se descartan."
            )
        for i, part in enumerate(parts[: len(base_parts)]):
            for m in part.getElementsByClass(stream.Measure):
                m2 = copy.deepcopy(m)
                m2.number = next_number[i]
                next_number[i] += 1
                base_parts[i].append(m2)
    return base, warnings


def _last_number(part: stream.Part) -> int:
    ms = list(part.getElementsByClass(stream.Measure))
    return ms[-1].number if ms else 0


def merge_pages(files: list[Path], out: Path) -> tuple[Path, list[str]]:
    """Join several MusicXML files. A single file is copied untouched (keeps the engine's layout)."""
    if not files:
        raise ValueError("No hay MusicXML para unir.")
    if len(files) == 1:
        dest = out.with_suffix(files[0].suffix)
        shutil.copyfile(files[0], dest)
        return dest, []
    out = out.with_suffix(".musicxml")
    scores = [load_score(f) for f in files]
    merged, warnings = _concat(scores)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        merged.write("musicxml", fp=str(out))
    except Exception as e:  # noqa: BLE001  (KeyError, StreamException «already found in this Stream»…)
        # music21 re-makes the notation on writing and breaks on some engine output (a note of
        # voice 7 running past the bar into a measure without voice 7: KeyError '7'). The pages
        # are already notated: write them as they are.
        merged.write("musicxml", fp=str(out), makeNotation=False)
        warnings.append(f"Las páginas se unieron sin rehacer la notación ({type(e).__name__}).")
    return out, warnings
