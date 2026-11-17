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
