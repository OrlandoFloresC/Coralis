"""Render measures of a ChoralScore to SVG with Verovio."""

from __future__ import annotations

from pathlib import Path

import verovio

from ..model.export import to_music21, to_musicxml_string
from ..model.score import ChoralScore

_OPTIONS = {
    "adjustPageHeight": True,
    "adjustPageWidth": True,
    "breaks": "none",
    "header": "none",
    "footer": "none",
    "svgViewBox": True,
    "scale": 40,
    "pageMarginLeft": 20,
    "pageMarginRight": 20,
    "pageMarginTop": 20,
    "pageMarginBottom": 20,
}


def render_measures_svg(cs: ChoralScore, cfg: dict, indices: list[int]) -> str:
    xml = to_musicxml_string(to_music21(cs, cfg, indices))
    # A single measure cut from the piece has ties that continue outside it; Verovio would warn.
    verovio.enableLog(verovio.LOG_ERROR)
    # Outside the main thread (the desktop window works in a background thread) Verovio does
    # not find its fonts by itself: create it without them and point it to its data folder.
    tk = verovio.toolkit(False)
    tk.setResourcePath(str(Path(verovio.__file__).parent / "data"))
    tk.setOptions(_OPTIONS)
    if not tk.loadData(xml):
        raise RuntimeError("Verovio no pudo cargar el compás")
    return tk.renderToSVG(1)


def render_voice_svg(m, voice: str, events, cfg: dict) -> str:
    """One voice of one measure on its own staff (one version of it, for the review)."""
    from music21 import clef, key, meter, note, spanner, stream, tie

    from ..model.export import CLEFS

    part = stream.Part()
    meas = stream.Measure(number=m.number)
    meas.insert(0, CLEFS.get(cfg["output"]["parts"][voice]["clef"], clef.TrebleClef)())
    meas.insert(0, key.KeySignature(m.key_fifths))
    meas.insert(0, meter.TimeSignature(f"{m.time[0]}/{m.time[1]}"))
    slur, prev = [], None   # the slurs (a syllable sung over several notes), as printed

    def close_slur() -> None:
        if len(slur) >= 2:
            part.insert(0, spanner.Slur(list(slur)))
        slur.clear()

    for e in events:
        if e.duration <= 0:
            continue
        n = note.Rest(quarterLength=e.duration) if e.is_rest else note.Note(e.pitch, quarterLength=e.duration)
        if not e.is_rest:
            if e.slur_cont and prev is not None:
                if not slur:
                    slur.append(prev)
                slur.append(n)
            elif not e.slur_cont and e.tie not in ("stop", "continue"):
                close_slur()
            prev = n
        if e.tie and not e.is_rest:
            n.tie = tie.Tie(e.tie)
        if not e.is_rest and e.lyrics:  # the words being typed, under their notes
            text, syl = next(iter(e.lyrics.values()))
            n.lyric = text
            if n.lyrics:
                n.lyrics[0].syllabic = syl
        meas.insert(float(e.offset), n)
    close_slur()
    if m.pickup:
        meas.paddingLeft = float(m.bar_length - m.duration)
    part.append(meas)
    score = stream.Score([part])
    tk = verovio.toolkit(False)
    tk.setResourcePath(str(Path(verovio.__file__).parent / "data"))
    tk.setOptions({**_OPTIONS, "pageWidth": 900, "scale": 45})
    if not tk.loadData(to_musicxml_string(score)):
        raise RuntimeError("Verovio no pudo cargar la versión")
    return tk.renderToSVG(1)
