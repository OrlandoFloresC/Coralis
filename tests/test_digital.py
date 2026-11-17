"""Copia digital (2 pentagramas con signos) y votación de signos."""

from fractions import Fraction as Fr
from pathlib import Path

from music21.musicxml.m21ToXml import GeneralObjectExporter

from omr_coral.config import load_config
from omr_coral.model.digital import to_two_staves
from omr_coral.model.score import VOICES, ChoralScore, Event, Marks, Measure
from omr_coral.voting.vote import _fix_endings


def _note(off, dur, pitch, **lyr):
    e = Event(Fr(off), Fr(dur), pitch, 60)
    e.lyrics = {int(k[1:]): (t, "single") for k, t in lyr.items()}
    return e


def _m(i, voices, **marks):
    m = Measure(index=i, system=1, page=None, staves=[], time=(3, 4), bar_length=Fr(3), duration=Fr(3))
    m.voices, m.number, m.marks = voices, i + 1, Marks(**marks)
    return m


def _xml(cs) -> str:
    return GeneralObjectExporter(to_two_staves(cs, load_config())).parse().decode("utf-8")


def test_two_staves_chords_unison_and_signs():
    chords = {"soprano": [_note(0, 3, "E4", v1="Gloria", v2="Santo")], "alto": [_note(0, 3, "C4")],
              "tenor": [_note(0, 3, "G3")], "bass": [_note(0, 3, "C3")]}
    unison = {v: [_note(0, 3, "D4" if v in ("soprano", "alto") else "D3")] for v in VOICES}
    cs = ChoralScore(Path("x"), [
        _m(0, chords, repeat_start=True, segno=True, dynamics=[("upper", Fr(0), "mf")]),
        _m(1, unison, repeat_end=True, volta=1),
        _m(2, chords, volta=2, barline="final", jump="D.S. al Coda"),
    ], [], "Prueba")
    x = _xml(cs)
    assert x.count("<score-part ") == 2                 # 2 pentagramas
    assert "<chord" in x                                # soprano y contralto en acorde
    assert 'direction="forward"' in x and 'direction="backward"' in x
    assert x.count("<ending ") >= 4                     # casillas 1 y 2 en las dos partes
    assert "<segno" in x and "<mf" in x
    assert "light-heavy" in x
    assert 'number="2"' in x and "Santo" in x           # estrofas apiladas


def test_endings_only_go_up_inside_a_run():
    ms = [_m(i, {v: [_note(0, 3, "C4")] for v in VOICES}, volta=n) for i, n in enumerate([1, 2, 1, 2])]
    cs = ChoralScore(Path("x"), ms, [])
    _fix_endings(cs)
    assert [m.marks.volta for m in cs.measures] == [1, 2, 2, 2]


def test_solo_words_read_as_plain_text_become_syllables():
    from omr_coral.model.score import _is_sign_text, _solo_syllables

    sy = _solo_syllables("40 Gran-de es Dios, El es san - to y re — al, con— ﬁ - a - mos")
    assert [t for t, _ in sy][:4] == ["Gran", "de", "es", "Dios,"]
    assert ("fi", "middle") in sy and ("san", "begin") in sy
    assert _is_sign_text("D. al Coda") and _is_sign_text("S. alCoda") and _is_sign_text("37 |2_")
    assert not _is_sign_text("Gran-de es Dios")
