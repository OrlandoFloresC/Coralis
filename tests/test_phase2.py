"""Phase 2: normalization into 4 voices and validation rules."""

from pathlib import Path

from music21 import chord, clef, corpus, key, layout, meter, note, stream

from omr_coral.config import load_config
from omr_coral.model.score import VOICES, build_choral_score
from omr_coral.rules import run_rules

CFG = load_config()


def _doubtful(cs):
    return sorted({i.measure for i in run_rules(cs, CFG) if i.severity != "info"})


def _write(score: stream.Score, tmp_path: Path) -> Path:
    p = tmp_path / "s.musicxml"
    # makeNotation=False: keep measures exactly as built (music21 would otherwise re-bar overflows)
    score.write("musicxml", fp=str(p), makeNotation=False)
    return p


def _hymn(measures_sa, measures_tb, split_first_system=False) -> stream.Score:
    """Two-staff 3/4 hymn: SA chords on treble, TB chords on bass.

    measures_*: list of measures, each a list of (pitch_names, quarterLength).
    split_first_system: imitate the engine bug where system 1's staves come out
    as two consecutive single-staff systems.
    """
    s = stream.Score()
    p1, p2 = stream.Part(), stream.Part()

    def build(m_events, number, clf=None, new_system=False):
        m = stream.Measure(number=number)
        if new_system:
            m.insert(0, layout.SystemLayout(isNew=True))
        if clf:
            m.insert(0, clf)
            m.insert(0, key.KeySignature(-1))
            m.insert(0, meter.TimeSignature("3/4"))
        for names, ql in m_events:
            m.append(chord.Chord(names, quarterLength=ql) if len(names) > 1 else note.Note(names[0], quarterLength=ql))
        return m

    def rest_measure(number, clf=None, new_system=False):
        m = stream.Measure(number=number)
        if new_system:
            m.insert(0, layout.SystemLayout(isNew=True))
        if clf:
            m.insert(0, clf)
            m.insert(0, key.KeySignature(-1))
            m.insert(0, meter.TimeSignature("3/4"))
        m.append(note.Rest(quarterLength=3))
        return m

    n = len(measures_sa)
    if split_first_system:
        half = n // 2
        # system 1 = treble staff only (part 2), system 2 = bass staff only (part 2), then normal
        for i in range(half):
            p1.append(rest_measure(i, clef.TrebleClef() if i == 0 else None))
            p2.append(build(measures_sa[i], i, clef.TrebleClef() if i == 0 else None))
        for i in range(half):
            p1.append(rest_measure(half + i, None, new_system=i == 0))
            p2.append(build(measures_tb[i], half + i, clef.BassClef() if i == 0 else None, new_system=i == 0))
        for i in range(half, n):
            p1.append(build(measures_sa[i], half + i, None, new_system=i == half))
            p2.append(build(measures_tb[i], half + i, None, new_system=i == half))
    else:
        for i in range(n):
            p1.append(build(measures_sa[i], i, clef.TrebleClef() if i == 0 else None))
            p2.append(build(measures_tb[i], i, clef.BassClef() if i == 0 else None))
    s.insert(0, p1)
    s.insert(0, p2)
    return s


SA = [[(["F4", "A4"], 2), (["E4", "G4"], 1)],
      [(["F4", "A4"], 2), (["C4", "F4"], 1)],
      [(["D4", "B-4"], 2), (["E4", "G4"], 1)],
      [(["C4", "F4"], 3)]]
TB = [[(["F3", "C4"], 2), (["C3", "B-3"], 1)],
      [(["F3", "C4"], 2), (["A2", "C4"], 1)],
      [(["B-2", "D4"], 2), (["C3", "C4"], 1)],
      [(["F2", "A3"], 3)]]


def test_bach_chorale_has_no_doubtful_measures(tmp_path):
    p = _write(corpus.parse("bach/bwv269"), tmp_path)
    cs = build_choral_score(p)
    assert len(cs.measures) == 24
    assert cs.measures[0].pickup
    assert _doubtful(cs) == []


def test_two_staff_hymn_is_split_into_four_voices(tmp_path):
    cs = build_choral_score(_write(_hymn(SA, TB), tmp_path))
    m = cs.measures[0]
    got = {v: [e.pitch for e in m.voices[v]] for v in VOICES}
    assert got == {"soprano": ["A4", "G4"], "alto": ["F4", "E4"], "tenor": ["C4", "B-3"], "bass": ["F3", "C3"]}
    assert _doubtful(cs) == []


def test_split_systems_are_merged_back(tmp_path):
    cs = build_choral_score(_write(_hymn(SA, TB, split_first_system=True), tmp_path))
    assert len(cs.measures) == 4
    assert any(i.rule == "estructura" and i.severity == "info" for i in cs.issues)
    assert [e.pitch for e in cs.measures[0].voices["bass"]] == ["F3", "C3"]
    assert _doubtful(cs) == []


def test_duration_error_is_flagged(tmp_path):
    sa = [list(m) for m in SA]
    sa[1] = [(["F4", "A4"], 2), (["C4", "F4"], 1.5)]  # 3.5 beats in 3/4
    cs = build_choral_score(_write(_hymn(sa, TB), tmp_path))
    issues = [i for i in run_rules(cs, CFG) if i.rule == "duracion"]
    assert issues and all(i.measure == 1 for i in issues)


def test_range_error_is_flagged(tmp_path):
    tb = [list(m) for m in TB]
    tb[2] = [(["E1", "D4"], 2), (["C3", "C4"], 1)]  # bass E1: far below C2 (a reading error, not a low bass)
    cs = build_choral_score(_write(_hymn(SA, tb), tmp_path))
    issues = [i for i in run_rules(cs, CFG) if i.rule == "rango"]
    assert [(i.measure, i.voice, i.severity) for i in issues] == [(2, "bass", "error")]  # 8 semitones out


def test_isolated_accidental_is_flagged_but_inflection_is_not(tmp_path):
    sa = [list(m) for m in SA]
    sa[1] = [(["D-4", "A4"], 2), (["F4", "A4"], 1)]   # alto D♭ out of the blue, leaps away to F
    sa[2] = [(["E4", "B-4"], 1), (["E-4", "B-4"], 1), (["E-4", "G4"], 1)]  # mi -> mi♭: inflection
    cs = build_choral_score(_write(_hymn(sa, TB), tmp_path))
    issues = [(i.measure, i.voice) for i in run_rules(cs, CFG) if i.rule == "alteraciones"]
    assert issues == [(1, "alto")]


def test_lost_voice_unison_is_flagged(tmp_path):
    sa = [list(m) for m in SA]
    sa[2] = [(["B-4"], 1.5), (["A4"], 0.5), (["G4"], 1)]  # alto notes missing -> alto copies soprano
    cs = build_choral_score(_write(_hymn(sa, TB), tmp_path))
    issues = [(i.measure, i.voice) for i in run_rules(cs, CFG) if i.rule == "unisono"]
    assert issues == [(2, "alto")]


def test_a_leap_after_a_rest_is_a_new_phrase():
    from fractions import Fraction as Fr
    from pathlib import Path

    from omr_coral.model.score import ChoralScore, Event, Measure
    from omr_coral.rules import melody

    m = Measure(index=0, system=1, page=None, staves=[])
    m.voices = {"soprano": [Event(Fr(0), Fr(1), "C4", 60), Event(Fr(1), Fr(1)), Event(Fr(2), Fr(1), "B-4", 70)]}
    assert not melody.check(ChoralScore(Path("x"), [m], []), {})
    m.voices = {"soprano": [Event(Fr(0), Fr(1), "C4", 60), Event(Fr(1), Fr(1), "B-4", 70)]}
    assert melody.check(ChoralScore(Path("x"), [m], []), {})
