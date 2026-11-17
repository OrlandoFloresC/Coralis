"""Audiveris engine, run in batch mode: Audiveris -batch -export -output <dir> -- <book>.

All pages are processed together as one book (a multi-page PDF built from the
page images), so time/key signatures printed only on page 1 still apply to
later pages.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image

from ..tools import ensure_audiveris
from .base import Engine, EngineResult


def _build_book(pages: list[Path], dest: Path, dpi: int) -> Path:
    imgs = [Image.open(p).convert("L") for p in pages]
    imgs[0].save(dest, "PDF", resolution=dpi, save_all=True, append_images=imgs[1:])
    return dest


class AudiverisEngine(Engine):
    name = "audiveris"

    def ensure(self) -> None:
        ensure_audiveris(self.cfg)

    def recognize(self, pages: list[Path], out_dir: Path) -> EngineResult:
        exe = ensure_audiveris(self.cfg)
        out_dir.mkdir(parents=True, exist_ok=True)
        book = _build_book(pages, out_dir / "book.pdf", self.cfg["preprocess"]["dpi"])
        log = out_dir / "audiveris.log"
        langs = self.cfg["recognition"].get("lyrics_languages")
        cmd = [str(exe), "-batch", "-export", "-output", str(out_dir)]
        if langs:
            cmd += ["-constant", f"org.audiveris.omr.text.Language.defaultSpecification={langs}"]
        cmd += ["--", str(book)]
        result = EngineResult(engine=self.name, image=book, log=log)
        timeout = self.cfg["tools"]["engine_timeout"] * len(pages)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
            log.write_text(proc.stdout + "\n" + proc.stderr, encoding="utf-8")
        except subprocess.TimeoutExpired:
            result.error = "tiempo agotado"
            return result
        # A book can yield several movements: book.mxl or book.mvt1.mxl, book.mvt2.mxl...
        result.musicxml = sorted(out_dir.glob("book*.mxl")) + sorted(out_dir.glob("book*.xml"))
        result.warnings = [l.strip() for l in log.read_text(encoding="utf-8").splitlines() if " WARN " in l]
        result.ok = bool(result.musicxml)
        if not result.ok:
            result.error = f"Audiveris no exportó MusicXML (código {proc.returncode}); ver {log.name}"
        return result
