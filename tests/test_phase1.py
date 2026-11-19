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
