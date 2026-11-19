"""Desktop window of Coralis: drop a score, press Convertir, open the result.

The window is HTML (index.html) shown by pywebview (WebView2 on Windows, WebKit on macOS).
JavaScript calls the methods of `Api` through `window.pywebview.api`; the work runs in a
background thread and reports back with `window.evaluate_js("onProgress(...)")`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback
from datetime import datetime
from pathlib import Path

import webview
from platformdirs import user_documents_dir
from webview.dom import DOMEventHandler

from ..config import load_config

APP_NAME = "Coralis"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
INPUT_EXTS = IMAGE_EXTS | {".pdf"}
HERE = Path(__file__).resolve().parent


def work_dir() -> Path:
    """Where the results go: Documents/Coralis (visible and easy to back up)."""
    d = Path(user_documents_dir()) / APP_NAME
    old = Path(user_documents_dir()) / "omr-coral"  # the folder before the app had its name
    if not d.exists() and old.is_dir():
        old.rename(d)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _hide_child_consoles() -> None:
    """A windowed app on Windows opens a black console for every console program it runs
    (Audiveris, homr, pip). Ask Windows not to, for every subprocess of this process."""
    if os.name != "nt":
        return
    original = subprocess.Popen.__init__

    def init(self, *args, **kwargs):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
        original(self, *args, **kwargs)

    subprocess.Popen.__init__ = init


def _open_path(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class Api:
    def __init__(self) -> None:
        self._window: webview.Window | None = None
        self._cfg = load_config(None)
        self._busy = False

    # ------------------------------------------------------------------ helpers
    def _js(self, fn: str, payload) -> None:
        if self._window:
            self._window.evaluate_js(f"{fn}({json.dumps(payload, ensure_ascii=False)})")

    def _describe(self, paths: list[str]) -> list[dict]:
        out = []
        for p in paths:
            path = Path(p)
            if path.suffix.lower() in INPUT_EXTS and path.is_file():
                out.append({"path": str(path), "name": path.name})
        return out

    # ------------------------------------------------------------------ called from JavaScript
    def setup_needed(self) -> list[str]:
        """Score readers still missing (first run of the app)."""
        from ..tools import missing_tools

        return missing_tools(self._cfg)

    def start_setup(self) -> None:
        if self._busy:
            return
        self._busy = True
        threading.Thread(target=self._setup, daemon=True).start()

    def _setup(self) -> None:
        from .. import tools

        tools.set_progress(lambda msg, frac: self._js("onSetup", {"message": msg, "fraction": frac}))
        try:
            tools.install_missing(self._cfg)
            self._js("onSetupDone", {})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._js("onSetupError", {"message": str(e) or e.__class__.__name__})
        finally:
            tools.set_progress(None)
            self._busy = False

    def pick_files(self) -> list[dict]:
        types = ("Partituras (*.pdf;*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.bmp;*.webp)", "Todos los archivos (*.*)")
        res = self._window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=True, file_types=types)
        return self._describe(list(res or []))

    def pick_lyrics(self) -> dict | None:
        res = self._window.create_file_dialog(webview.FileDialog.OPEN, file_types=("Texto (*.txt)",))
        if not res:
            return None
        p = Path(res[0])
        return {"path": str(p), "name": p.name}

    def suggest_lyrics(self, first_file: str) -> dict | None:
        """A .txt with the same name next to the score is used automatically."""
        p = Path(first_file).with_suffix(".txt")
        return {"path": str(p), "name": p.name} if p.is_file() else None

    def start(self, files: list[str], lyrics: str | None, title: str | None) -> dict:
        if self._busy:
            return {"ok": False, "error": "Ya hay una conversión en marcha."}
        paths = [Path(f) for f in files]
        if not paths:
            return {"ok": False, "error": "Primero elige la partitura."}
        if any(p.suffix.lower() == ".pdf" for p in paths) and len(paths) > 1:
            return {"ok": False, "error": "Un PDF ya trae todas sus páginas: elige solo el PDF, sin otras imágenes."}
        self._busy = True
        threading.Thread(target=self._run, args=(paths, lyrics, (title or "").strip() or None),
                         daemon=True).start()
        return {"ok": True}

    def open_result(self, run_dir: str, what: str) -> None:
        from ..pipeline import final_file
        from ..tools import find_musescore

        run = Path(run_dir)
        if what == "folder":
            _open_path(run)
        elif what == "report":
            _open_path(run / "report" / "index.html")
        elif what in ("score", "digital"):
            xml = final_file(run)
            if xml and what == "digital":
                xml = xml.with_name(f"{xml.stem} (copia digital).musicxml")
            if not xml or not xml.exists():
                return
            ms = find_musescore(self._cfg)
            if ms:
                subprocess.Popen([str(ms), str(xml)])
            else:
                _open_path(xml)

    # ------------------------------------------------------------------ review (signs)
    def review_data(self, run_dir: str) -> dict:
        """Every measure with its crop and its signs, plus the warnings about jumps."""
        from ..model import corrections
        from ..pipeline import validate_run

        run = Path(run_dir)
        if not (run / "compases.json").exists():  # made before the review existed
            validate_run(run, self._cfg)
        measures = json.loads((run / "compases.json").read_text(encoding="utf-8"))
        for m in measures:
            m["thumb"] = _thumb(run / m.pop("crop"))
        info = json.loads((run / "validation.json").read_text(encoding="utf-8"))
        warnings = [{"index": i["measure"], "label": i.get("measure_label"), "message": i["message"]}
                    for i in info.get("issues", []) if i["rule"] == "repeticion"]
        return {"title": self._summary(run)["title"], "measures": measures, "warnings": warnings,
                "saved": corrections.load(run).get("marks", {}), "jumps": list(corrections.JUMPS)}

    def save_review(self, run_dir: str, changes: dict) -> dict:
        """Store the answers and rebuild the result in the background (onReviewDone)."""
        from ..model import corrections

        if self._busy:
            return {"ok": False, "error": "Ya hay una conversión en marcha."}
        run = Path(run_dir)
        data = corrections.load(run)
        for key, fields_ in (changes or {}).items():
            data["marks"][str(key)] = fields_
        corrections.save(run, data)
        self._busy = True
        threading.Thread(target=self._revalidate, args=(run, "onReviewDone"), daemon=True).start()
        return {"ok": True}

    def notes_data(self, run_dir: str) -> dict:
        """Doubtful measures: the image and, for each disputed voice, every version read."""
        from ..model import corrections
        from ..pipeline import validate_run

        run = Path(run_dir)
        if not (run / "versiones.json").exists():
            validate_run(run, self._cfg)
        measures = json.loads((run / "versiones.json").read_text(encoding="utf-8"))
        for m in measures:
            m["thumb"] = _thumb(run / m.pop("crop"), width=760)
        return {"title": self._summary(run)["title"], "measures": measures,
                "saved": corrections.load(run).get("voices", {})}

    def save_notes(self, run_dir: str, choices: dict) -> dict:
        from ..model import corrections

        if self._busy:
            return {"ok": False, "error": "Ya hay una conversión en marcha."}
        run = Path(run_dir)
        data = corrections.load(run)
        voices = data.setdefault("voices", {})
        for key, per_voice in (choices or {}).items():
            voices.setdefault(str(key), {}).update(per_voice)
        corrections.save(run, data)
        self._busy = True
        threading.Thread(target=self._revalidate, args=(run, "onNotesDone"), daemon=True).start()
        return {"ok": True}

    def _revalidate(self, run: Path, callback: str) -> None:
        from ..pipeline import validate_run

        try:
            validate_run(run, self._cfg)
            self._js(callback, {"run_dir": str(run), "summary": self._summary(run)})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._js("onError", {"message": str(e) or e.__class__.__name__})
        finally:
            self._busy = False

    def open_work_dir(self) -> None:
        _open_path(work_dir())

    def history(self) -> list[dict]:
        items = []
        for d in work_dir().iterdir():
            marker = d / "final.txt"
            if not d.is_dir() or not marker.exists():
                continue
            items.append(self._summary(d))
        items.sort(key=lambda x: x["time"], reverse=True)
        return items[:30]

    def has_musescore(self) -> bool:
        from ..tools import find_musescore

        return find_musescore(self._cfg) is not None

    # ------------------------------------------------------------------ work
    def _summary(self, run: Path) -> dict:
        title = (run / "final.txt").read_text(encoding="utf-8").strip().rsplit(".", 1)[0]
        info = {}
        try:
            info = json.loads((run / "validation.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        t = datetime.fromtimestamp((run / "final.txt").stat().st_mtime)
        return {
            "run_dir": str(run),
            "title": title,
            "time": t.isoformat(),
            "when": t.strftime("%d/%m/%Y %H:%M"),
            "measures": info.get("measures"),
            "verses": info.get("verses"),
            "doubtful": info.get("doubtful_measures", []),
            "has_digital": (run / f"{title} (copia digital).musicxml").exists(),
            "has_versions": _has_versions(run),
        }

    def _run(self, paths: list[Path], lyrics: str | None, title: str | None) -> None:
        from ..pipeline import recognize, validate_run

        staging = None
        try:
            name = title or paths[0].stem
            if len(paths) == 1:
                src = paths[0]
            else:  # several pages: copy them, in the order given, into one folder
                staging = Path(tempfile.mkdtemp(prefix="coralis-"))
                src = staging / name
                src.mkdir()
                for i, p in enumerate(paths, start=1):
                    shutil.copyfile(p, src / f"{i:03d}{p.suffix.lower()}")
            if not lyrics:
                auto = paths[0].with_suffix(".txt")
                lyrics = str(auto) if auto.is_file() else None

            def progress(msg: str, frac: float | None) -> None:
                self._js("onProgress", {"message": _friendly(msg), "fraction": frac})

            run_dir = recognize(src, self._cfg, work_dir(), lyrics, title=title, progress=progress)
            self._js("onProgress", {"message": "Votando entre las lecturas y revisando las reglas…", "fraction": 0.92})
            validate_run(run_dir, self._cfg)
            self._js("onDone", self._summary(run_dir))
        except Exception as e:  # noqa: BLE001  (show any failure to the user instead of dying silently)
            traceback.print_exc()
            self._js("onError", {"message": str(e) or e.__class__.__name__})
        finally:
            self._busy = False
            if staging:
                shutil.rmtree(staging, ignore_errors=True)


def _has_versions(run: Path) -> bool:
    try:
        return bool(json.loads((run / "versiones.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return False


def _thumb(path: Path, width: int = 320) -> str | None:
    """Small PNG of a measure crop as a data URI (the window cannot read arbitrary files)."""
    import base64
    import io

    from PIL import Image

    if not path.exists():
        return None
    img = Image.open(path).convert("L")
    if img.width > width:
        img = img.resize((width, max(1, round(img.height * width / img.width))))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _friendly(msg: str) -> str:
    """Pipeline log line -> short sentence for the window."""
    if msg.startswith("Carpeta de trabajo"):
        return "Preparando las páginas…"
    if "página(s)" in msg:
        return "Mejorando la imagen…"
    if msg.startswith("Variantes de imagen"):
        return "Mejorando la imagen…"
    if msg.startswith("Preparando"):
        return "Preparando los lectores de partituras (la primera vez se descargan, puede tardar varios minutos)…"
    if msg.startswith("Leyendo"):
        return "Leyendo la partitura…"
    if msg.startswith("[") and "/" in msg:
        done = msg[1:msg.index("]")]
        return f"Leyendo la partitura… ({done.replace('/', ' de ')})"
    if msg.startswith("Letra tomada"):
        return "Usando la letra del archivo de texto…"
    return msg


def _selftest(score: str) -> int:
    """`Coralis --selftest <score>`: install what is missing and convert one score without
    the window (checks a freshly built app, here or on GitHub's machines)."""
    from .. import tools
    from ..pipeline import recognize, validate_run

    cfg = load_config(None)
    tools.set_progress(lambda msg, frac: print(f"  [instalación] {msg}", flush=True))
    tools.install_missing(cfg)
    out = Path(tempfile.mkdtemp(prefix="coralis-selftest-"))
    run_dir = recognize(Path(score), cfg, out, None, progress=lambda m, f: print(" ", m, flush=True))
    validate_run(run_dir, cfg)
    final = (run_dir / "final.txt").read_text(encoding="utf-8").strip()
    print(f"OK: {run_dir / final}")
    return 0


def _check() -> int:
    """`Coralis --check`: the libraries load and a measure can be drawn (a quick test of a
    freshly built app; nothing is downloaded)."""
    from music21 import corpus  # noqa: F401  (imported by the pipeline)

    from .. import pipeline  # noqa: F401  (numpy, OpenCV, music21, pypdfium2...)
    from ..config import load_config as _load
    from ..output.render import render_voice_svg  # noqa: F401
    import verovio

    tk = verovio.toolkit(False)
    tk.setResourcePath(str(Path(verovio.__file__).parent / "data"))
    _load(None)
    print("OK: Coralis", verovio.__name__, "listo")
    return 0


def main() -> int:
    # a windowed app opens a black console for every console program it runs (pip, homr,
    # Audiveris), which the user could close mid-install: hide them in every mode
    _hide_child_consoles()
    if len(sys.argv) >= 2 and sys.argv[1] == "--check":
        return _check()
    if len(sys.argv) >= 3 and sys.argv[1] == "--selftest":
        return _selftest(sys.argv[2])
    log = work_dir() / f"{APP_NAME}.log"
    if sys.stdout is None or sys.stderr is None:  # windowed app: no console to print to
        fh = open(log, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        sys.stdout = sys.stdout or fh
        sys.stderr = sys.stderr or fh
    if os.name == "nt":  # the taskbar shows Coralis' icon, not Python's
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Coralis.App")
    api = Api()
    window = webview.create_window(
        "Coralis · Partituras corales a MusicXML", str(HERE / "index.html"), js_api=api,
        width=880, height=760, min_size=(560, 600),
    )
    api._window = window

    def on_drop(e):
        files = e.get("dataTransfer", {}).get("files", [])
        paths = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
        api._js("addFiles", api._describe(paths))

    def bind(win):
        win.dom.document.events.drop += DOMEventHandler(on_drop, True, True)

    webview.start(bind, window, icon=str(HERE / "coralis.ico"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
