"""homr engine: `homr <page.png>` writes <page>.musicxml next to the image.

homr reads one page at a time; the pages are then joined into one score.
It does not read lyrics.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from ..model.merge import merge_pages
from ..tools import ensure_homr
from .base import Engine, EngineResult


class HomrEngine(Engine):
    name = "homr"

    def ensure(self) -> None:
        ensure_homr(self.cfg)

    def recognize(self, pages: list[Path], out_dir: Path) -> EngineResult:
        exe = ensure_homr(self.cfg)
        out_dir = out_dir.resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        log = out_dir / "homr.log"
        result = EngineResult(engine=self.name, image=pages[0], log=log)
        page_xml: list[Path] = []
        log_text = []
        for page in pages:
            local = out_dir / page.name  # homr writes its output next to the image
            shutil.copyfile(page, local)
            try:
                # Only the file name, run from its folder: OpenCV (inside homr) cannot open paths with
                # non-ASCII characters on Windows ("Señor", a user called "José").
                proc = subprocess.run([str(exe), "--no-title", local.name], capture_output=True, text=True, encoding="utf-8", errors="replace",
                                      timeout=self.cfg["tools"]["engine_timeout"], cwd=out_dir,
                                      env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
                log_text.append(f"== {page.name}\n{proc.stdout[-4000:]}\n{proc.stderr[-4000:]}")
            except subprocess.TimeoutExpired:
                log_text.append(f"== {page.name}: tiempo agotado")
                continue
            xml = local.with_suffix(".musicxml")
            if xml.exists():
                page_xml.append(xml)
            else:
                result.warnings.append(f"homr no produjo resultado para {page.name}")
        log.write_text("\n".join(log_text), encoding="utf-8")
        if not page_xml:
            result.error = f"homr no exportó MusicXML; ver {log.name}"
            return result
        merged, warns = merge_pages(page_xml, out_dir / "book")
        result.warnings += warns
        result.musicxml = [merged]
        result.ok = True
        return result
