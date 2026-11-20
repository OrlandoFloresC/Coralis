from pathlib import Path

from PIL import Image

from omr_coral.config import _deep_merge, load_config
from omr_coral.preprocess.pages import extract_pages


def test_defaults_load():
    cfg = load_config()
    assert cfg["preprocess"]["dpi"] == 300
    assert set(cfg["voices"]["ranges"]) == {"soprano", "alto", "tenor", "bass"}


def test_deep_merge_keeps_unset_keys():
    out = _deep_merge({"a": {"x": 1, "y": 2}}, {"a": {"y": 3}})
    assert out == {"a": {"x": 1, "y": 3}}


def test_extract_pages_from_image_folder(tmp_path: Path):
    src = tmp_path / "fotos"
    src.mkdir()
    for name in ("b.jpg", "a.png"):
        Image.new("RGB", (50, 40), "white").save(src / name)
    pages = extract_pages(src, tmp_path / "pages")
    assert [p.name for p in pages] == ["page_001.png", "page_002.png"]
    assert Image.open(pages[0]).mode == "L"


def test_one_rest_printed_for_both_voices_of_a_staff():
    # «Bálsamo existe»: the lower staff ends a measure with one quarter rest for both voices;
    # the voice without it must rest too, not be left with a hole (that looks like a lost voice)
    from fractions import Fraction as Fr

    from omr_coral.model.score import RawEvent, _voice_from

    def raw(off, dur, pitch=None):
        from music21 import pitch as p

        return RawEvent(Fr(off), Fr(dur), [p.Pitch(pitch)] if pitch else [], [None] if pitch else [], layer="1")

    upper = [raw(0, 1, "G#3"), raw(1, 2, "F#3"), raw(3, 1)]
    lower = [raw(0, 1, "D3"), raw(1, 2, "D#3")]
    bass = _voice_from(lower, [upper], "bottom", Fr(4))
    assert [(e.pitch, e.offset, e.filled) for e in bass] == [("D3", 0, False), ("D#3", 1, False), (None, 3, False)]


def test_voices_ordered_by_stems_not_pitch():
    # «Castillo fuerte»: the alto (stems down) holds c♭ while the soprano (stems up) runs
    # c♭ b♭ a♭ g♭, so the alto is higher on average; the soprano is still the stem-up voice.
    # A crossing wider than a fifth is a misread note, and then pitch decides.
    from fractions import Fraction as Fr

    from music21 import pitch as p

    from omr_coral.model.score import RawEvent, _order_layers

    def raw(off, dur, name, stem, layer):
        return RawEvent(Fr(off), Fr(dur), [p.Pitch(name)], [None], layer=layer, stem=stem)

    sop = [raw(0, 0.5, "C-4", "up", "1"), raw(0.5, 0.5, "B-3", "up", "1"),
           raw(1, 1, "A-3", "up", "1"), raw(2, 1, "G-3", "up", "1")]
    alt = [raw(0, 2, "C-4", "down", "2"), raw(2, 1, "B-3", "down", "2")]
    assert _order_layers([alt, sop])[0] is sop
    no_stems = [[RawEvent(e.offset, e.duration, e.pitches, e.ties, layer=e.layer) for e in l] for l in (sop, alt)]
    assert _order_layers(no_stems[::-1])[0] is no_stems[0]   # voice 1 = upper

    up = [raw(0, 1, "A-3", "up", "6"), raw(1, 1, "A-2", "up", "6")]
    down = [raw(0, 1, "A-3", "down", "7"), raw(1, 1, "A-3", "down", "7")]
    assert _order_layers([up, down])[0] is down


def test_pitch_fixed_by_hand_follows_its_tie():
    from fractions import Fraction as Fr
    from pathlib import Path

    from omr_coral.model.corrections import apply_edits
    from omr_coral.model.score import VOICES, ChoralScore, Event, Measure

    def m(i, evs):
        x = Measure(index=i, system=1, page=None, staves=[], time=(4, 4), bar_length=Fr(4), duration=Fr(4))
        x.voices = {v: [] for v in VOICES}
        x.voices["alto"] = evs
        return x

    ms = [m(0, [Event(Fr(0), Fr(2), "C4"), Event(Fr(2), Fr(2), "B3", tie="start")]),
          m(1, [Event(Fr(0), Fr(4), "B3", tie="stop")])]
    cs = ChoralScore(Path("x"), ms, [])
    assert apply_edits(cs, {"edits": {"0": {"alto": {"2": "B-3", "9": "C4"}, "tenor": {"0": "Z9"}}}}) == {0}
    assert ms[0].voices["alto"][1].pitch == "B-3" and ms[0].voices["alto"][1].alter == -1.0
    assert ms[1].voices["alto"][0].pitch == "B-3"     # the tied note goes along
    assert ms[0].voices["alto"][0].pitch == "C4"


def test_tie_added_and_removed_by_hand():
    from fractions import Fraction as Fr
    from pathlib import Path

    from omr_coral.model.corrections import apply_edits
    from omr_coral.model.score import VOICES, ChoralScore, Event, Measure

    def m(i, evs):
        x = Measure(index=i, system=1, page=None, staves=[], time=(4, 4), bar_length=Fr(4), duration=Fr(4))
        x.voices = {v: [] for v in VOICES}
        x.voices["tenor"] = evs
        return x

    ms = [m(0, [Event(Fr(0), Fr(2), "C4"), Event(Fr(2), Fr(2), "D4")]),
          m(1, [Event(Fr(0), Fr(2), "D4", lyrics={1: ("la", "single")}), Event(Fr(2), Fr(2), "E4")])]
    cs = ChoralScore(Path("x"), ms, [])
    apply_edits(cs, {"edits": {"0": {"tenor": {"2": {"pitch": "D4", "tie": True}, "0": {"pitch": "C4", "tie": True}}}}})
    assert ms[0].voices["tenor"][1].tie == "start" and ms[1].voices["tenor"][0].tie == "stop"
    assert ms[1].voices["tenor"][0].lyrics == {}
    assert ms[0].voices["tenor"][0].tie is None      # C4 → D4: not the same sound, no tie
    apply_edits(cs, {"edits": {"0": {"tenor": {"2": {"pitch": "D4", "tie": False}}}}})
    assert ms[0].voices["tenor"][1].tie is None and ms[1].voices["tenor"][0].tie is None


def test_slur_added_by_hand_is_a_melisma_and_is_exported():
    from fractions import Fraction as Fr
    from pathlib import Path

    from omr_coral.config import load_config
    from omr_coral.model.corrections import apply_edits
    from omr_coral.model.export import to_music21
    from omr_coral.model.score import VOICES, ChoralScore, Event, Measure

    m = Measure(index=0, system=1, page=None, staves=[], time=(4, 4), bar_length=Fr(4), duration=Fr(4))
    m.voices = {v: [Event(Fr(0), Fr(2), "C4", lyrics={1: ("A", "single")}),
                    Event(Fr(2), Fr(2), "D4", lyrics={1: ("mén", "single")})] for v in VOICES}
    cs = ChoralScore(Path("x"), [m], [])
    apply_edits(cs, {"edits": {"0": {"soprano": {"0": {"pitch": "C4", "slur": True}}}}})
    assert m.voices["soprano"][1].slur_cont and m.voices["soprano"][1].lyrics == {}
    score = to_music21(cs, load_config(None))
    slurs = [s for s in score.parts[0].spanners if s.classes[0] == "Slur"]
    assert len(slurs) == 1 and len(slurs[0].getSpannedElements()) == 2


def test_notes_moved_by_hand():
    # «the notes are right but not where they should be»: the user moves them; the measure must still add up
    from fractions import Fraction as Fr
    from pathlib import Path

    from omr_coral.model.corrections import apply_rhythm
    from omr_coral.model.score import VOICES, ChoralScore, Event, Measure

    m = Measure(index=3, system=1, page=None, staves=[], time=(4, 4), bar_length=Fr(4), duration=Fr(4))
    m.voices = {v: [Event(Fr(0), Fr(2), "C4", lyrics={1: ("A", "single")}), Event(Fr(2), Fr(2), "D4")] for v in VOICES}
    cs = ChoralScore(Path("x"), [m], [])
    rows = [["0", "1", None, None, False], ["1", "2", "C4", None, False], ["3", "1", "D4", None, False]]
    assert apply_rhythm(cs, {"rhythm": {"3": {"alto": rows, "bass": rows[:2]}}}) == {3}
    alto = m.voices["alto"]
    assert [(e.offset, e.duration, e.pitch) for e in alto] == [(0, 1, None), (1, 2, "C4"), (3, 1, "D4")]
    assert alto[1].lyrics == {1: ("A", "single")}      # the syllable goes with its note
    assert m.voices["bass"][0].pitch == "C4"            # 3 beats only: not applied


def test_upbeat_gets_shorter_when_a_silence_is_taken_out():
    # «El camino es escabroso»: the alto was read with an extra eighth, the upbeat came out 3 eighths;
    # the user takes the silence out and the upbeat is 2 eighths again
    from fractions import Fraction as Fr
    from pathlib import Path

    from omr_coral.model.corrections import apply_rhythm
    from omr_coral.model.score import VOICES, ChoralScore, Event, Measure

    m = Measure(index=0, system=1, page=None, staves=[], time=(4, 4), bar_length=Fr(4), duration=Fr(3, 2), pickup=True)
    m.voices = {v: [Event(Fr(0), Fr(1, 2), "F3"), Event(Fr(1, 2), Fr(1, 2), "G-3"), Event(Fr(1), Fr(1, 2), filled=True)]
                for v in VOICES}
    m.voices["alto"] = [Event(Fr(0), Fr(1, 2)), Event(Fr(1, 2), Fr(1, 2), "F3"), Event(Fr(1), Fr(1, 2), "G-3")]
    cs = ChoralScore(Path("x"), [m], [])
    apply_rhythm(cs, {"rhythm": {"0": {"alto": [["0", "1/2", "F3", None, False], ["1/2", "1/2", "G-3", None, False]]}}})
    assert m.duration == 1
    assert [(e.offset, e.pitch) for e in m.voices["alto"]] == [(0, "F3"), (Fr(1, 2), "G-3")]
    assert sum(e.duration for e in m.voices["soprano"]) == 1


def test_upbeat_silence_in_front_of_some_voices_goes():
    from fractions import Fraction as Fr
    from pathlib import Path

    from omr_coral.model.corrections import apply_rhythm, apply_voice_lyrics
    from omr_coral.model.score import VOICES, ChoralScore, Event, Measure

    m = Measure(index=0, system=1, page=None, staves=[], time=(4, 4), bar_length=Fr(4), duration=Fr(3, 2), pickup=True)
    m.voices = {v: [Event(Fr(0), Fr(1, 2), "F3"), Event(Fr(1, 2), Fr(1, 2), "G-3"), Event(Fr(1), Fr(1, 2), filled=True)]
                for v in VOICES}
    cs = ChoralScore(Path("x"), [m], [])
    data = {"rhythm": {"0": {"alto": [["0", "1/2", None, None, False], ["1/2", "1/2", "F3", None, False], ["1", "1/2", "G-3", None, False]]}},
            "voice_lyrics": {"0": {"alto": {"1": {"1/2": {"text": "El", "dash": False}, "1": {"text": "ca", "dash": True}}}}}}
    apply_rhythm(cs, data)
    apply_voice_lyrics(cs, data)
    assert m.duration == 1
    assert [(e.offset, e.pitch, e.lyrics.get(1, ("",))[0]) for e in m.voices["alto"]] == [(0, "F3", "El"), (Fr(1, 2), "G-3", "ca")]
