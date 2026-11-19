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
