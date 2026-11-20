"""Desktop window of Coralis: drop a score, press Convertir, open the result.

The window is HTML (index.html) shown by pywebview (WebView2 on Windows, WebKit on macOS).
JavaScript calls the methods of `Api` through `window.pywebview.api`; the work runs in a
background thread and reports back with `window.evaluate_js("onProgress(...)")`.
"""

from __future__ import annotations

import json
import re
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


PENDING = "pendiente_rehacer.txt"  # corrections saved, the score not rebuilt yet


class Api:
    def __init__(self) -> None:
        self._window: webview.Window | None = None
        self._cfg = load_config(None)
        self._busy = False

    # ------------------------------------------------------------------ helpers
    def _fresh(self, run: Path) -> None:
        """Changes were saved without rebuilding: rebuild before showing or giving out results."""
        from ..pipeline import validate_run

        flag = run / PENDING
        if flag.exists():
            validate_run(run, self._cfg)
            flag.unlink(missing_ok=True)

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
        if what != "folder":
            self._fresh(run)
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
        self._fresh(run)
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
        self._fresh(run)
        if not (run / "versiones.json").exists():
            validate_run(run, self._cfg)
        measures = json.loads((run / "versiones.json").read_text(encoding="utf-8"))
        if not (run / "notas.json").exists():
            validate_run(run, self._cfg)
        keys = {m["index"]: m["key"] for m in json.loads((run / "notas.json").read_text(encoding="utf-8"))}
        for m in measures:
            m["thumb"] = _thumb(run / m.pop("crop"), width=760)
            m["key"] = keys.get(m["index"], 0)
        return {"title": self._summary(run)["title"], "measures": measures,
                "saved": corrections.load(run).get("voices", {})}

    def _measure_meta(self, run: Path, index: int) -> dict | None:
        p = run / "notas.json"
        if not p.exists():
            from ..pipeline import validate_run
            validate_run(run, self._cfg)
        return next((m for m in json.loads(p.read_text(encoding="utf-8")) if m["index"] == index), None)

    def _render(self, meta: dict, voice: str, events: list) -> str | None:
        """One voice of one measure drawn on its own staff, from the window's note list."""
        from fractions import Fraction
        from types import SimpleNamespace

        from ..model.score import Event
        from ..output.render import render_voice_svg

        m = SimpleNamespace(number=meta["number"], key_fifths=meta["key"], time=tuple(meta["time"]),
                            pickup=meta["pickup"], bar_length=Fraction(meta["bar_length"]),
                            duration=Fraction(meta["duration"]))
        evs = [Event(Fraction(e["offset"]), Fraction(e["duration"]), e.get("pitch"), tie=e.get("tie"),
                     filled=bool(e.get("filled")), slur_cont=bool(e.get("slur")),
                     lyrics={1: (e["lyric"], e.get("syl") or "single")} if e.get("lyric") else {})
               for e in events]
        try:
            return render_voice_svg(m, voice, evs, self._cfg)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            return None

    def render_voice(self, run_dir: str, index: int, voice: str, events: list) -> str | None:
        meta = self._measure_meta(Path(run_dir), int(index))
        return self._render(meta, voice, events) if meta else None

    def measure_data(self, run_dir: str, label: str) -> dict:
        """Any measure, by the number the user sees (for «Ir al compás…»)."""
        run = Path(run_dir)
        self._fresh(run)
        if not (run / "notas.json").exists():
            from ..pipeline import validate_run
            validate_run(run, self._cfg)
        all_ = json.loads((run / "notas.json").read_text(encoding="utf-8"))
        meta = next((m for m in all_ if str(m["label"]).lower() == str(label).strip().lower()), None)
        if meta is None:
            return {"ok": False, "error": f"No hay un compás «{label}» (van del {all_[0]['label']} al {all_[-1]['label']})."}
        names = self._cfg["output"]["parts"]
        voices = {}
        for v, evs in meta["voices"].items():
            if not any(e.get("pitch") for e in evs):
                continue
            voices[v] = {"name": names[v]["name"], "options": [{
                "key": "current", "votes": 0, "total": 0, "chosen": True, "events": evs,
                "svg": self._render(meta, v, evs), "desc": ""}]}
        crop = run / meta["crop"]
        return {"ok": True, "measure": {"index": meta["index"], "label": meta["label"], "voices": voices,
                                        "key": meta["key"],
                                        "thumb": _thumb(crop, width=760) if crop.exists() else None,
                                        "single": True}}

    def playback_data(self, run_dir: str) -> dict:
        """The file for practice, ready to play: per voice, its notes in quarter notes from the
        start (tied notes joined into one sound), with the words; and every measure's start."""
        from ..model.score import VOICES, build_choral_score
        from ..pipeline import final_file

        run = Path(run_dir)
        self._fresh(run)
        path = final_file(run)
        if path is None:
            return {"ok": False, "error": "Todavía no hay partitura para escuchar."}
        cs = build_choral_score(path)
        names = self._cfg["output"]["parts"]
        measures, voices = [], {v: [] for v in VOICES}
        words = {v: [] for v in VOICES}
        t = 0.0
        tempo = None
        for m in cs.measures:
            length = float(m.bar_length)
            silent = not any(not e.is_rest for evs in m.voices.values() for e in evs)
            measures.append({"start": t, "length": length, "time": list(m.time), "number": m.number,
                             "silent": silent})
            for st in m.staves:
                tempo = tempo or st.tempo
            for v in VOICES:
                notes = voices[v]
                for e in m.voices.get(v, []):
                    if e.is_rest or e.midi is None:
                        continue
                    start = t + float(e.offset)
                    if e.tie in ("stop", "continue") and notes and notes[-1]["midi"] == e.midi \
                            and abs(notes[-1]["start"] + notes[-1]["dur"] - start) < 1e-6:
                        notes[-1]["dur"] += float(e.duration)  # one sound across the tie
                    else:
                        notes.append({"start": start, "dur": float(e.duration), "midi": e.midi})
                    if 1 in e.lyrics:
                        words[v].append({"start": start, "text": e.lyrics[1][0], "syl": e.lyrics[1][1]})
            t += length
        # where each stanza starts: the first measure, and the first one with music after a silent one
        stanzas = [0] if measures else []
        for k in range(1, len(measures)):
            if measures[k - 1]["silent"] and not measures[k]["silent"]:
                stanzas.append(k)
        return {"ok": True, "title": self._summary(run)["title"], "tempo": tempo, "measures": measures,
                "stanzas": stanzas,
                "voices": [{"id": v, "name": names[v]["name"], "notes": voices[v], "words": words[v]}
                           for v in VOICES]}

    # ------------------------------------------------------------------ editing the words
    def lyrics_text(self, run_dir: str) -> dict:
        """The words of every stanza as plain text: the user's file if there is one, else what
        the OCR read (syllables joined back into words), for the user to correct."""
        from ..pipeline import LYRICS_FILE, validate_run

        run = Path(run_dir)
        self._fresh(run)
        own = run / LYRICS_FILE
        if own.exists():
            return {"text": own.read_text(encoding="utf-8-sig"), "from_file": True,
                    "title": self._summary(run)["title"]}
        if not (run / "notas.json").exists() or "words" not in (run / "notas.json").read_text(encoding="utf-8")[:20000]:
            validate_run(run, self._cfg)
        measures = json.loads((run / "notas.json").read_text(encoding="utf-8"))
        lines = sorted({int(n) for m in measures for n in m.get("words", {})})
        blocks = []
        for n in lines:
            text = ""
            for m in measures:
                for _off, syl_text, syl in m.get("words", {}).get(str(n), []):
                    piece = syl_text.replace("‿", " ")
                    text += piece + ("" if syl in ("begin", "middle") else " ")
            text = " ".join(text.split())
            # one line per phrase, so that it reads like the hymnal
            text = re.sub(r"([;:.!?])\s*(?=[^\s.,;:!?)»”])", r"\1\n", text)
            text = re.sub(r",(?=\S)", ", ", text)
            blocks.append(f"{n}. {text}")
        return {"text": "\n\n".join(blocks), "from_file": False, "title": self._summary(run)["title"]}

    def save_lyrics(self, run_dir: str, text: str | None) -> dict:
        """Save the corrected words (None: back to what the OCR read) and rebuild the score."""
        from ..pipeline import LYRICS_FILE

        if self._busy:
            return {"ok": False, "error": "Ya hay una conversión en marcha."}
        run = Path(run_dir)
        own = run / LYRICS_FILE
        if text is None:
            if own.exists():
                own.unlink()
        else:
            if not text.strip():
                return {"ok": False, "error": "La letra está vacía."}
            own.write_text(text.strip() + "\n", encoding="utf-8")
        self._busy = True
        threading.Thread(target=self._revalidate, args=(run, "onLyricsDone"), daemon=True).start()
        return {"ok": True}

    # ------------------------------------------------------------------ words note by note
    def lyric_editor_data(self, run_dir: str) -> dict:
        """Every measure with the notes of the voice that carries the words and the words on
        them, stanza by stanza (as the score stands now)."""
        from ..pipeline import validate_run

        run = Path(run_dir)
        self._fresh(run)
        p = run / "notas.json"
        if not p.exists() or '"lyric_voice"' not in p.read_text(encoding="utf-8")[:50000]:
            validate_run(run, self._cfg)
        measures = json.loads(p.read_text(encoding="utf-8"))
        # the versions the readings gave, where they disagreed (to pick another one here too)
        versions = {}
        vp = run / "versiones.json"
        if vp.exists():
            for vm in json.loads(vp.read_text(encoding="utf-8")):
                versions[vm["index"]] = {v: [{"key": o["key"], "events": o.get("events", []), "votes": o["votes"],
                                              "total": o["total"], "chosen": o["chosen"], "edited": o.get("edited", False)}
                                             for o in info["options"] if not o.get("edited")]
                                         for v, info in vm["voices"].items()}
        out = []
        for m in measures:
            lead = m.get("lyric_voice", "soprano")
            out.append({k: m[k] for k in ("index", "label", "number", "key", "time", "pickup", "bar_length", "duration")}
                       | {"voice": lead, "voices": m["voices"], "words": m.get("words", {}),
                          "vwords": m.get("vwords", {}), "own_words": m.get("own_words", False),
                          "versions": {v: o for v, o in versions.get(m["index"], {}).items() if len(o) > 1}})
        lines = max([int(n) for m in measures for n in m.get("words", {})] + [1])
        names = self._cfg["output"]["parts"]
        return {"title": self._summary(run)["title"], "measures": out, "verses": lines,
                "voice_names": {v: names[v]["name"] for v in names}}

    def measure_thumb(self, run_dir: str, index: int) -> str | None:
        crop = Path(run_dir) / "report" / "img" / f"m{int(index):03d}.png"
        return _thumb(crop, width=1000) if crop.exists() else None

    def save_editor(self, run_dir: str, choices: dict, edits: dict, lyrics: dict, rebuild: bool = True,
                    rhythm: dict | None = None, voice_lyrics: dict | None = None) -> dict:
        """Everything the editor changed, at once: versions picked, notes fixed, words typed.
        rebuild=False only saves (instant): the score is rebuilt later, before it is shown or
        given out, or when the user asks."""
        from ..model import corrections

        if self._busy:
            return {"ok": False, "error": "Ya hay una conversión en marcha."}
        run = Path(run_dir)
        data = corrections.load(run)
        for key, per_voice in (choices or {}).items():
            data.setdefault("voices", {}).setdefault(str(key), {}).update(per_voice)
        fixed = data.setdefault("edits", {})
        for key, per_voice in (edits or {}).items():
            for v, notes in per_voice.items():
                if notes:
                    fixed.setdefault(str(key), {})[v] = notes
                else:
                    fixed.get(str(key), {}).pop(v, None)
            if not fixed.get(str(key)):
                fixed.pop(str(key), None)
        moved = data.setdefault("rhythm", {})
        for idx, per_voice in (rhythm or {}).items():
            for v, rows in per_voice.items():
                moved.setdefault(str(idx), {})[v] = rows
                fixed.get(str(idx), {}).pop(v, None)  # the pitches travel with the rhythm now
        own = data.setdefault("voice_lyrics", {})
        for idx, per_voice in (voice_lyrics or {}).items():
            for v, lines in per_voice.items():
                for line, notes in lines.items():
                    own.setdefault(str(idx), {}).setdefault(v, {})[str(line)] = notes
        typed = data.setdefault("lyrics", {})
        for idx, lines in (lyrics or {}).items():
            for line, notes in lines.items():
                typed.setdefault(str(idx), {})[str(line)] = notes
        corrections.save(run, data)
        if not rebuild:
            (run / PENDING).write_text("Correcciones guardadas; falta rehacer la partitura.\n", encoding="utf-8")
            return {"ok": True, "pending": True}
        return self.rebuild(run_dir)

    def rebuild(self, run_dir: str) -> dict:
        if self._busy:
            return {"ok": False, "error": "Ya hay una conversión en marcha."}
        self._busy = True
        threading.Thread(target=self._revalidate, args=(Path(run_dir), "onEditorDone"), daemon=True).start()
        return {"ok": True}

    def save_lyric_notes(self, run_dir: str, edits: dict) -> dict:
        from ..model import corrections

        if self._busy:
            return {"ok": False, "error": "Ya hay una conversión en marcha."}
        run = Path(run_dir)
        data = corrections.load(run)
        typed = data.setdefault("lyrics", {})
        for idx, lines in (edits or {}).items():
            for line, notes in lines.items():
                typed.setdefault(str(idx), {})[str(line)] = notes
        corrections.save(run, data)
        self._busy = True
        threading.Thread(target=self._revalidate, args=(run, "onLyricNotesDone"), daemon=True).start()
        return {"ok": True}

    def voice_names(self) -> list[dict]:
        from ..model.score import VOICES

        return [{"id": v, "name": self._cfg["output"]["parts"][v]["name"]} for v in VOICES]

    def export_voice(self, run_dir: str, voice: str) -> dict:
        """A MusicXML with one voice only (with its words, every stanza), where the user says."""
        from ..model.export import to_music21
        from ..model.score import VOICES, build_choral_score
        from ..pipeline import final_file

        if voice not in VOICES:
            return {"ok": False, "error": "Esa voz no existe."}
        run = Path(run_dir)
        self._fresh(run)
        path = final_file(run)
        if path is None:
            return {"ok": False, "error": "Todavía no hay partitura."}
        name = self._cfg["output"]["parts"][voice]["name"]
        default = f"{path.stem} - {name}.musicxml"
        res = self._window.create_file_dialog(webview.FileDialog.SAVE, directory=str(run.parent),
                                              save_filename=default, file_types=("MusicXML (*.musicxml)",))
        if not res:
            return {"ok": False}
        dest = Path(res if isinstance(res, str) else res[0])
        if dest.suffix.lower() not in (".musicxml", ".xml"):
            dest = dest.with_suffix(".musicxml")
        score = to_music21(build_choral_score(path), self._cfg)
        for part in list(score.parts):
            if part.id != voice:
                score.remove(part)
        score.write("musicxml", fp=str(dest))
        return {"ok": True, "path": str(dest)}

    def video_begin(self, run_dir: str) -> str:
        """Start receiving a video, piece by piece. Returns a token (the temporary file)."""
        import tempfile

        fd, path = tempfile.mkstemp(prefix="coralis-video-", suffix=".part")
        os.close(fd)
        self._videos = getattr(self, "_videos", set()) | {path}
        return path

    def video_chunk(self, token: str, data_b64: str) -> bool:
        import base64

        if token not in getattr(self, "_videos", set()):
            return False
        try:
            data = base64.b64decode(data_b64)
        except ValueError:
            traceback.print_exc()
            return False
        with open(token, "ab") as f:
            f.write(data)
        return True

    def video_end(self, token: str, run_dir: str, name: str, ext: str) -> dict:
        """The video is complete: ask where to keep it."""
        import re
        import shutil

        if token not in getattr(self, "_videos", set()):
            return {"ok": False, "error": "No se encontró el video."}
        self._videos.discard(token)
        ext = ext if ext in ("mp4", "webm") else "mp4"
        safe = re.sub(r'[\\/:*?"<>|]+', " ", name).strip() or "video"
        res = self._window.create_file_dialog(webview.FileDialog.SAVE, directory=str(Path(run_dir).parent),
                                              save_filename=f"{safe}.{ext}", file_types=(f"Video (*.{ext})",))
        if not res:
            Path(token).unlink(missing_ok=True)
            return {"ok": False, "error": "No se guardó (cancelado)."}
        dest = Path(res if isinstance(res, str) else res[0])
        if dest.suffix.lower() != f".{ext}":
            dest = dest.with_suffix(f".{ext}")
        shutil.move(token, dest)
        return {"ok": True, "path": str(dest)}

    def video_cancel(self, token: str) -> None:
        if token in getattr(self, "_videos", set()):
            self._videos.discard(token)
            Path(token).unlink(missing_ok=True)

    def save_audio(self, run_dir: str, name: str, data_b64: str) -> dict:
        """Save the mp3 the window rendered, where the user says."""
        import base64
        import re

        safe = re.sub(r'[\\/:*?"<>|]+', " ", name).strip() or "audio.mp3"
        res = self._window.create_file_dialog(webview.FileDialog.SAVE, directory=str(Path(run_dir).parent),
                                              save_filename=safe, file_types=("Audio MP3 (*.mp3)",))
        if not res:
            return {"ok": False, "error": "No se guardó (cancelado)."}
        dest = Path(res if isinstance(res, str) else res[0])
        if dest.suffix.lower() != ".mp3":
            dest = dest.with_suffix(".mp3")
        dest.write_bytes(base64.b64decode(data_b64))
        return {"ok": True, "path": str(dest)}

    def save_notes(self, run_dir: str, choices: dict, edits: dict | None = None) -> dict:
        from ..model import corrections

        if self._busy:
            return {"ok": False, "error": "Ya hay una conversión en marcha."}
        run = Path(run_dir)
        data = corrections.load(run)
        voices = data.setdefault("voices", {})
        for key, per_voice in (choices or {}).items():
            voices.setdefault(str(key), {}).update(per_voice)
        fixed = data.setdefault("edits", {})
        for key, per_voice in (edits or {}).items():
            for v, notes in per_voice.items():
                if notes:
                    fixed.setdefault(str(key), {})[v] = notes
                else:  # back to the notes of the readings
                    fixed.get(str(key), {}).pop(v, None)
            if not fixed.get(str(key)):
                fixed.pop(str(key), None)
        corrections.save(run, data)
        self._busy = True
        threading.Thread(target=self._revalidate, args=(run, "onNotesDone"), daemon=True).start()
        return {"ok": True}

    def _revalidate(self, run: Path, callback: str) -> None:
        from ..pipeline import validate_run

        try:
            validate_run(run, self._cfg)
            (run / PENDING).unlink(missing_ok=True)
            self._js(callback, {"run_dir": str(run), "summary": self._summary(run)})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._js("onError", {"message": str(e) or e.__class__.__name__})
        finally:
            self._busy = False

    # ------------------------------------------------------------------ new version
    def check_update(self) -> dict:
        from .updates import check

        return check()

    def open_download(self, url: str) -> None:
        """Open a release download in the browser (only links of Coralis on GitHub)."""
        import webbrowser

        from .updates import REPO

        if url.startswith(f"https://github.com/{REPO}/"):
            webbrowser.open(url)

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
            "pending": (run / PENDING).exists(),
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
