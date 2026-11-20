"""ChoralScore -> music21 Score with one part per voice (names and clefs from config)."""

from __future__ import annotations

from music21 import clef, key, metadata, meter, note, spanner, stream, tie
from music21.musicxml.m21ToXml import GeneralObjectExporter

from .score import VOICES, ChoralScore

CLEFS = {"G": clef.TrebleClef, "F": clef.BassClef, "G8vb": clef.Treble8vbClef, "C": clef.AltoClef}


def to_music21(cs: ChoralScore, cfg: dict, indices: list[int] | None = None) -> stream.Score:
    parts_cfg = cfg["output"]["parts"]
    chosen = [cs.measures[i] for i in indices] if indices is not None else cs.measures
    score = stream.Score()
    score.metadata = metadata.Metadata(title=cs.title or "")
    score.metadata.composer = ""  # otherwise music21 signs the score as "Music21"
    for v in VOICES:
        part = stream.Part(id=v)
        part.partName = parts_cfg[v]["name"]
        prev_time = prev_key = None
        slur: list = []          # the notes of the slur being drawn
        last_note = None

        def close_slur() -> None:
            if len(slur) >= 2:
                part.insert(0, spanner.Slur(list(slur)))
            slur.clear()

        for k, m in enumerate(chosen):
            meas = stream.Measure(number=m.number)
            if k == 0:
                meas.insert(0, CLEFS.get(parts_cfg[v]["clef"], clef.TrebleClef)())
            if m.key_fifths != prev_key:
                meas.insert(0, key.KeySignature(m.key_fifths))
            if m.time != prev_time:
                meas.insert(0, meter.TimeSignature(f"{m.time[0]}/{m.time[1]}"))
            prev_time, prev_key = m.time, m.key_fifths
            for e in m.voices.get(v, []):
                if e.duration <= 0:
                    continue
                if e.is_rest:
                    n = note.Rest(quarterLength=e.duration)
                else:
                    n = note.Note(e.pitch, quarterLength=e.duration)
                    if e.tie:
                        n.tie = tie.Tie(e.tie)
                    for verse, (text, syllabic) in sorted(e.lyrics.items()):
                        ly = note.Lyric(text=text, number=verse)
                        ly.syllabic = syllabic
                        n.lyrics.append(ly)
                    # a note sung on the syllable before (inside a slur): draw the slur
                    if e.slur_cont and last_note is not None:
                        if not slur:
                            slur.append(last_note)
                        slur.append(n)
                    elif not e.slur_cont and e.tie not in ("stop", "continue"):
                        close_slur()
                    last_note = n
                meas.insert(float(e.offset), n)
            if m.pickup and k == 0:
                meas.paddingLeft = float(m.bar_length - m.duration)
            part.append(meas)
        close_slur()
        score.insert(0, part)
    return score


def to_musicxml_string(score: stream.Score) -> str:
    return GeneralObjectExporter(score).parse().decode("utf-8")
