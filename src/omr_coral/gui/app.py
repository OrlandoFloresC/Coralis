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
FAVORITE = "favorito.txt"   # ★ in the list of hymns


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

    def save_review(self, run_dir: str, changes: dict, rebuild: bool = False) -> dict:
        """Store the signs. Like the editor: saved at once; the score is rebuilt later (before it
        is shown or given out), or now with rebuild=True (onReviewDone)."""
        from ..model import corrections

        if self._busy:
            return {"ok": False, "error": "Ya hay una conversión en marcha."}
        run = Path(run_dir)
        data = corrections.load(run)
        for key, fields_ in (changes or {}).items():
            data["marks"][str(key)] = fields_
        corrections.save(run, data)
        if not rebuild:
            (run / PENDING).write_text("Signos guardados; falta rehacer la partitura.\n", encoding="utf-8")
            return {"ok": True, "pending": True}
        return self.rebuild(run_dir, "onReviewDone")

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
        names = {v: {"name": n} for v, n in self._names(run).items()}
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
                "key": cs.measures[0].key_fifths if cs.measures else 0,
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
                    # as in the hymnal: «Cas-ti-llo fuer-te», a hyphen between the syllables of a word, so
                    # that it shows on which note each one goes and where a space is missing («fuer-te-nues-tro»)
                    joins = syl in ("begin", "middle") and not re.search(r"[.,;:!?»”)]$", piece)
                    text += piece + ("-" if joins else " ")
            text = " ".join(text.split())
            # one line per phrase, so that it reads like the hymnal
            text = re.sub(r"([;:.!?])\s*(?=[^\s.,;:!?)»”])", r"\1\n", text)
            text = re.sub(r",(?=\S)", ", ", text)
            blocks.append(f"{n}. {text}")
        return {"text": "\n\n".join(blocks), "from_file": False, "title": self._summary(run)["title"]}

    def save_lyrics(self, run_dir: str, text: str | None, rebuild: bool = False) -> dict:
        """Save the corrected words (None: back to what the OCR read). Like the editor: the score is
        rebuilt later, or now with rebuild=True (onLyricsDone)."""
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
        if not rebuild:
            (run / PENDING).write_text("Letra guardada; falta rehacer la partitura.\n", encoding="utf-8")
            return {"ok": True, "pending": True}
        return self.rebuild(run_dir, "onLyricsDone")

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
        signs = {}
        cp = run / "compases.json"
        if cp.exists():
            signs = {c["index"]: c.get("marks", {}) for c in json.loads(cp.read_text(encoding="utf-8"))}
        out = []
        for m in measures:
            lead = m.get("lyric_voice", "soprano")
            out.append({k: m[k] for k in ("index", "label", "number", "key", "time", "pickup", "bar_length", "duration")}
                       | {"voice": lead, "voices": m["voices"], "words": m.get("words", {}),
                          "vwords": m.get("vwords", {}), "own_words": m.get("own_words", False),
                          "marks": signs.get(m["index"], {}),
                          "versions": {v: o for v, o in versions.get(m["index"], {}).items() if len(o) > 1}})
        lines = max([int(n) for m in measures for n in m.get("words", {})] + [1])
        from ..model import corrections

        saved = corrections.load(run)
        return {"title": self._summary(run)["title"], "measures": out, "verses": lines,
                "voice_names": self._names(run), "doubtful": self._doubtful_indices(run),
                "structure": saved.get("structure") or [], "signatures": saved.get("signatures") or {},
                "jumps": list(corrections.JUMPS)}

    def measure_thumb(self, run_dir: str, index: int) -> str | None:
        crop = Path(run_dir) / "report" / "img" / f"m{int(index):03d}.png"
        return _thumb(crop, width=1000) if crop.exists() else None

    def save_editor(self, run_dir: str, choices: dict, edits: dict, lyrics: dict, rebuild: bool = True,
                    rhythm: dict | None = None, voice_lyrics: dict | None = None, marks: dict | None = None) -> dict:
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
        for idx, fields_ in (marks or {}).items():   # signs of a measure, set in the editor
            data["marks"][str(idx)] = {f: v for f, v in fields_.items() if f in corrections.EDITABLE}
        corrections.save(run, data)
        if not rebuild:
            (run / PENDING).write_text("Correcciones guardadas; falta rehacer la partitura.\n", encoding="utf-8")
            return {"ok": True, "pending": True}
        return self.rebuild(run_dir)

    def measure_op(self, run_dir: str, op: str, at: int) -> dict:
        """Add a measure of rests at that place, or remove the measure there; the corrections saved
        for the other measures follow them. The score is rebuilt (onEditorDone)."""
        from ..model import corrections
        from ..model.structure import KEYED, rekey

        if self._busy:
            return {"ok": False, "error": "Ya hay una conversión en marcha."}
        run = Path(run_dir)
        count = len(json.loads((run / "notas.json").read_text(encoding="utf-8")))
        at = int(at)
        if op not in ("insert", "delete") or not (0 <= at <= count) or (op == "delete" and (at == count or count < 2)):
            return {"ok": False, "error": "Ese compás no existe."}
        data = corrections.load(run)
        entry = {"op": op, "at": at}
        if op == "delete":   # kept with the step, to give them back if it is undone
            entry["saved"] = {name: data[name][str(at)] for name in KEYED
                              if isinstance(data.get(name), dict) and str(at) in data[name]}
        rekey(data, entry)
        data.setdefault("structure", []).append(entry)
        corrections.save(run, data)
        (run / PENDING).unlink(missing_ok=True)
        return self.rebuild(run_dir)

    def measure_undo(self, run_dir: str) -> dict:
        """Undo the last measure added or removed (with the corrections the removed one had)."""
        from ..model import corrections
        from ..model.structure import rekey

        if self._busy:
            return {"ok": False, "error": "Ya hay una conversión en marcha."}
        run = Path(run_dir)
        data = corrections.load(run)
        ops = data.get("structure") or []
        if not ops:
            return {"ok": False, "error": "No hay cambios de compases que deshacer."}
        last = ops.pop()
        if last["op"] == "insert":
            rekey(data, {"op": "delete", "at": last["at"]})
        else:
            rekey(data, {"op": "insert", "at": last["at"]})
            for name, val in (last.get("saved") or {}).items():
                data.setdefault(name, {})[str(last["at"])] = val
        corrections.save(run, data)
        return self.rebuild(run_dir)

    def set_signature(self, run_dir: str, index: int, time: list | None, key: int | None, scope: str = "run") -> dict:
        """The time and/or key signature from that measure ("run": until the reading changes;
        "one": that measure only). None for both = back to what was read. Rebuilds."""
        from ..model import corrections

        if self._busy:
            return {"ok": False, "error": "Ya hay una conversión en marcha."}
        run = Path(run_dir)
        data = corrections.load(run)
        sigs = data.setdefault("signatures", {})
        entry = {"scope": "one" if scope == "one" else "run"}
        if time:
            entry["time"] = [int(time[0]), int(time[1])]
        if key is not None:
            entry["key"] = int(key)
        if "time" in entry or "key" in entry:
            sigs[str(int(index))] = entry
        else:
            sigs.pop(str(int(index)), None)
        corrections.save(run, data)
        return self.rebuild(run_dir)

    def rebuild(self, run_dir: str, callback: str = "onEditorDone") -> dict:
        if self._busy:
            return {"ok": False, "error": "Ya hay una conversión en marcha."}
        if callback not in ("onEditorDone", "onReviewDone", "onLyricsDone"):
            callback = "onEditorDone"
        self._busy = True
        threading.Thread(target=self._revalidate, args=(Path(run_dir), callback), daemon=True).start()
        return {"ok": True}

    def _names(self, run: Path) -> dict:
        from ..pipeline import voice_names

        return voice_names(run, self._cfg)

    def _cfg_for(self, run: Path) -> dict:
        from ..pipeline import cfg_for

        return cfg_for(run, self._cfg)

    def _doubtful_indices(self, run: Path) -> list[int]:
        """The measures still doubtful (by index), to jump from one to the next in the editor."""
        try:
            info = json.loads((run / "validation.json").read_text(encoding="utf-8"))
            labels = {str(x) for x in info.get("doubtful_measures", [])}
            notes = json.loads((run / "notas.json").read_text(encoding="utf-8"))
            return [m["index"] for m in notes if str(m["label"]) in labels]
        except (OSError, ValueError):
            return []

    def voice_names(self, run_dir: str | None = None) -> list[dict]:
        from ..model.score import VOICES

        names = self._names(Path(run_dir)) if run_dir else {v: p["name"] for v, p in self._cfg["output"]["parts"].items()}
        return [{"id": v, "name": names[v]} for v in VOICES]

    def set_voice_names(self, run_dir: str, names: dict) -> dict:
        """Rename the voices of this hymn; every file and screen uses the new names."""
        from ..pipeline import NAMES_FILE

        run = Path(run_dir)
        default = {v: p["name"] for v, p in self._cfg["output"]["parts"].items()}
        clean = {v: str(n).strip() for v, n in (names or {}).items() if v in default and str(n).strip()}
        if all(clean.get(v, default[v]) == default[v] for v in default):
            (run / NAMES_FILE).unlink(missing_ok=True)
        else:
            (run / NAMES_FILE).write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
        (run / PENDING).write_text("Nombres de las voces cambiados; falta rehacer la partitura.\n", encoding="utf-8")
        return {"ok": True, "names": self._names(run)}

    def export_voice(self, run_dir: str, voice: str | None, semitones: int = 0) -> dict:
        """A MusicXML with one voice only (with its words, every stanza), or with the four
        (voice None), in the hymn's folder; raised or lowered by some semitones if asked."""
        prep = self._export_score(run_dir, voice, semitones)
        if not prep["ok"]:
            return prep
        dest = _free_name(prep["run"], prep["stem"], "musicxml")
        prep["score"].write("musicxml", fp=str(dest))
        return {"ok": True, "path": str(dest), "folder": str(dest.parent)}

    def export_midi(self, run_dir: str, voice: str | None, semitones: int = 0, tempo: float | None = None) -> dict:
        """A MIDI file (one track per voice) at the speed the player has, in the hymn's folder."""
        from music21 import duration, instrument, tempo as m21tempo

        prep = self._export_score(run_dir, voice, semitones)
        if not prep["ok"]:
            return prep
        score = prep["score"]
        for part in score.parts:   # each track named after its voice, with a piano sound
            inst = instrument.Piano()
            inst.partName = inst.instrumentName = part.partName
            part.insert(0, inst)
        if tempo:
            first = score.parts[0].getElementsByClass("Measure").first() if score.parts else None
            if first is not None:
                for mm in first.getElementsByClass(m21tempo.MetronomeMark):
                    first.remove(mm)
                (n, d) = prep["time"]
                beat = 1.5 if d == 8 and n % 3 == 0 and n > 3 else 4 / d
                first.insert(0, m21tempo.MetronomeMark(number=float(tempo), referent=duration.Duration(beat)))
        dest = _free_name(prep["run"], prep["stem"], "mid")
        score.write("midi", fp=str(dest))
        return {"ok": True, "path": str(dest), "folder": str(dest.parent)}

    def score_pages(self, run_dir: str, voice: str | None = None, semitones: int = 0) -> dict:
        """The file for practice drawn as A4 pages (Verovio SVG), to follow it while it plays and to
        print it. With what sounds when: per measure (in order), [measure, quarter notes from its
        start, notes that start, notes that end] (ids of the drawing)."""
        import verovio

        from ..model.export import to_musicxml_string

        prep = self._export_score(run_dir, voice, semitones)
        if not prep["ok"]:
            return prep
        verovio.enableLog(verovio.LOG_ERROR)
        tk = verovio.toolkit(False)   # in a thread: without its fonts, then pointed to them
        tk.setResourcePath(str(Path(verovio.__file__).parent / "data"))
        tk.setOptions({"pageWidth": 2100, "pageHeight": 2970, "scale": 40, "breaks": "auto",
                       "header": "auto", "footer": "auto", "svgViewBox": True,
                       "pageMarginTop": 80, "pageMarginBottom": 80, "pageMarginLeft": 100, "pageMarginRight": 100})
        if not tk.loadData(to_musicxml_string(prep["score"])):
            return {"ok": False, "error": "No se pudo dibujar la partitura."}
        pages = [tk.renderToSVG(i + 1) for i in range(tk.getPageCount())]
        order = {mid: k for k, mid in enumerate(m for s in pages for m in re.findall(r'<g id="([^"]+)" class="measure', s))}
        tm = tk.renderToTimemap({"includeMeasures": True, "includeRests": False})
        if isinstance(tm, str):
            tm = json.loads(tm)
        events, k, start = [], 0, 0.0
        for e in tm:
            if "measureOn" in e and e["measureOn"] in order:
                k, start = order[e["measureOn"]], float(e["qstamp"])
            if e.get("on") or e.get("off"):
                events.append([k, round(float(e["qstamp"]) - start, 6), e.get("on", []), e.get("off", [])])
        return {"ok": True, "pages": pages, "events": events, "measures": len(order), "name": prep["stem"]}

    def learn_example(self, spec: dict) -> dict:
        """«Aprende»: a short example written in tinyNotation (c4 = middle C, quarter note; c'8 an
        octave up, eighth; r4 rest; c4_ma a syllable), drawn on its staff, with its notes to play:
        {"svg", "notes": [[offset in quarters, duration, midi], ...]}."""
        import verovio
        from music21 import clef, converter, key, meter, stream

        from ..model.export import to_musicxml_string

        try:
            time = spec.get("time")
            part = converter.parse("tinyNotation: " + (f"{time} " if time else "4/4 ") + spec.get("tiny", ""))
            measures = list(part.getElementsByClass(stream.Measure))
            if measures:
                first = measures[0]
                for c in list(first.getElementsByClass(clef.Clef)):
                    first.remove(c)
                first.insert(0, {"F": clef.BassClef, "G8": clef.Treble8vbClef}.get(spec.get("clef"), clef.TrebleClef)())
                if spec.get("key"):
                    first.insert(0, key.KeySignature(int(spec["key"])))
                if not time:   # a note or two, no meter to show
                    for ts in list(first.getElementsByClass(meter.TimeSignature)):
                        ts.style.hideObjectOnPrint = True
            notes = []
            for n in part.recurse().notes:
                off = float(n.getOffsetInHierarchy(part))
                for p in getattr(n, "pitches", [n.pitch]):
                    notes.append([off, float(n.quarterLength), int(p.midi)])
            verovio.enableLog(verovio.LOG_ERROR)
            tk = verovio.toolkit(False)
            tk.setResourcePath(str(Path(verovio.__file__).parent / "data"))
            tk.setOptions({"adjustPageHeight": True, "adjustPageWidth": True, "breaks": "none", "header": "none",
                           "footer": "none", "svgViewBox": True, "scale": int(spec.get("scale", 45)),
                           "pageMarginLeft": 20, "pageMarginRight": 20, "pageMarginTop": 10, "pageMarginBottom": 10})
            if not tk.loadData(to_musicxml_string(stream.Score([part]))):
                return {"ok": False, "error": "No se pudo dibujar el ejemplo."}
            return {"ok": True, "svg": tk.renderToSVG(1), "notes": notes}
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return {"ok": False, "error": f"No se pudo dibujar el ejemplo: {e}"}

    def pdf_begin(self, run_dir: str) -> str:
        """Start receiving the pages of a PDF (each one a picture of an A4 page)."""
        folder = tempfile.mkdtemp(prefix="coralis-pdf-")
        self._pdfs = getattr(self, "_pdfs", set()) | {folder}
        return folder

    def pdf_page(self, token: str, jpeg_b64: str) -> bool:
        import base64

        if token not in getattr(self, "_pdfs", set()):
            return False
        n = len(list(Path(token).glob("*.jpg")))
        (Path(token) / f"{n:04d}.jpg").write_bytes(base64.b64decode(jpeg_b64))
        return True

    def pdf_end(self, token: str, run_dir: str, name: str) -> dict:
        """Join the pages into an A4 PDF, in the hymn's folder."""
        import pypdfium2 as pdfium

        if token not in getattr(self, "_pdfs", set()):
            return {"ok": False, "error": "No se encontraron las páginas."}
        self._pdfs.discard(token)
        files = sorted(Path(token).glob("*.jpg"))
        try:
            if not files:
                return {"ok": False, "error": "No llegó ninguna página."}
            dest = _free_name(Path(run_dir), name, "pdf")
            w, h = 595.28, 841.89   # A4 in points
            pdf = pdfium.PdfDocument.new()
            for f in files:
                page = pdf.new_page(w, h)
                img = pdfium.PdfImage.new(pdf)
                img.load_jpeg(str(f), inline=True)
                img.set_matrix(pdfium.PdfMatrix().scale(w, h))
                page.insert_obj(img)
                page.gen_content()
            pdf.save(str(dest))
            pdf.close()
            return {"ok": True, "path": str(dest), "folder": str(dest.parent)}
        finally:
            shutil.rmtree(token, ignore_errors=True)

    def pdf_cancel(self, token: str) -> None:
        if token in getattr(self, "_pdfs", set()):
            self._pdfs.discard(token)
            shutil.rmtree(token, ignore_errors=True)

    def _export_score(self, run_dir: str, voice: str | None, semitones: int) -> dict:
        from ..model.export import to_music21
        from ..model.score import VOICES, build_choral_score
        from ..model.transpose import shift_label, transpose_score
        from ..pipeline import final_file

        if voice is not None and voice not in VOICES:
            return {"ok": False, "error": "Esa voz no existe."}
        run = Path(run_dir)
        self._fresh(run)
        path = final_file(run)
        if path is None:
            return {"ok": False, "error": "Todavía no hay partitura."}
        semitones = max(-12, min(12, int(semitones or 0)))
        cs = transpose_score(build_choral_score(path), semitones)
        score = to_music21(cs, self._cfg_for(run))
        if voice is not None:
            for part in list(score.parts):
                if part.id != voice:
                    score.remove(part)
        who = self._names(run)[voice] if voice else "4 voces"
        return {"ok": True, "run": run, "score": score, "stem": f"{path.stem} - {who}{shift_label(semitones)}",
                "time": cs.measures[0].time if cs.measures else (4, 4)}

    def video_staves(self, run_dir: str, voice: str, semitones: int = 0) -> list:
        """Each measure of the file for practice, one voice, drawn on its own staff (for the video)."""
        from ..model.score import VOICES, build_choral_score
        from ..model.transpose import transpose_score
        from ..output.render import render_voice_svg
        from ..pipeline import final_file

        if voice not in VOICES:
            return []
        run = Path(run_dir)
        self._fresh(run)
        path = final_file(run)
        if path is None:
            return []
        out = []
        cs = transpose_score(build_choral_score(path), max(-12, min(12, int(semitones or 0))))
        for m in cs.measures:
            evs = [e for e in m.voices.get(voice, []) if e.duration > 0]
            for e in evs:
                e.lyrics = {}   # the words are shown big, apart
            if not any(not e.is_rest for e in evs):
                out.append(None)
                continue
            try:
                svg = render_voice_svg(m, voice, evs, self._cfg)
            except Exception:  # noqa: BLE001  (a measure that cannot be drawn: no staff there)
                out.append(None)
                continue
            # where each note head is drawn (in the units of the drawing), to light the one that sounds
            out.append({"svg": svg, "heads": _note_heads(svg),
                        "notes": [[float(e.offset), float(e.duration)] for e in evs if not e.is_rest]})
        return out

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

    def video_end(self, token: str, run_dir: str, name: str, ext: str, folder: str | None = None) -> dict:
        """The video is complete: ask where to keep it (or put it in the folder chosen for several)."""
        import shutil

        if token not in getattr(self, "_videos", set()):
            return {"ok": False, "error": "No se encontró el video."}
        self._videos.discard(token)
        ext = ext if ext in ("mp4", "webm") else "mp4"
        dest = _free_name(Path(folder) if folder and Path(folder).is_dir() else Path(run_dir), name, ext)
        shutil.move(token, dest)
        return {"ok": True, "path": str(dest), "folder": str(dest.parent)}

    def video_cancel(self, token: str) -> None:
        if token in getattr(self, "_videos", set()):
            self._videos.discard(token)
            Path(token).unlink(missing_ok=True)

    def save_audio(self, run_dir: str, name: str, data_b64: str) -> dict:
        """Save the mp3 the window rendered, in the hymn's folder."""
        import base64

        dest = _free_name(Path(run_dir), name.rsplit(".", 1)[0], "mp3")
        dest.write_bytes(base64.b64decode(data_b64))
        return {"ok": True, "path": str(dest), "folder": str(dest.parent)}

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
        return items   # all of them: the window filters (favourites, needing attention) and searches

    def set_favorite(self, run_dir: str, on: bool) -> bool:
        """★: a hymn the user loves. Kept inside the hymn's folder (it travels with it)."""
        mark = Path(run_dir) / FAVORITE
        try:
            if on:
                mark.write_text("★\n", encoding="utf-8")
            else:
                mark.unlink(missing_ok=True)
        except OSError:
            return False
        return True

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
            "favorite": (run / FAVORITE).exists(),
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


def _free_name(folder: Path, name: str, ext: str) -> Path:
    """A file name in this folder that does not write over another one."""
    safe = re.sub(r'[\\/:*?"<>|]+', " ", name).strip() or "archivo"
    dest = folder / f"{safe}.{ext}"
    n = 2
    while dest.exists():
        dest = folder / f"{safe} ({n}).{ext}"
        n += 1
    return dest


def _note_heads(svg: str) -> list[list[float]]:
    """Centre of each note head of a Verovio drawing, in the units of its outer viewBox, in order."""
    outer = re.search(r'<svg[^>]*viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    inner = re.search(r'class="definition-scale"[^>]*viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    margin = re.search(r'class="page-margin" transform="translate\(([\d.-]+), ([\d.-]+)\)"', svg)
    if not (outer and inner):
        return []
    k = float(outer.group(1)) / float(inner.group(1))
    mx, my = (float(margin.group(1)), float(margin.group(2))) if margin else (0.0, 0.0)
    heads = []
    for note in re.finditer(r'class="note"[\s\S]*?class="notehead"[\s\S]*?translate\(([\d.-]+), ([\d.-]+)\)', svg):
        heads.append([(float(note.group(1)) + mx + 150) * k, (float(note.group(2)) + my) * k])  # +150: half a head
    return heads


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

    _mac_app_name()
    webview.start(bind, window, icon=str(HERE / "coralis.ico"), localization=MENUS_ES)
    return 0


# the Mac menu bar in Spanish (pywebview's are in English); «Edición» must stay: ⌘C ⌘V ⌘A live there
MENUS_ES = {
    "global.quitConfirmation": "¿Seguro que quieres salir?", "global.ok": "Aceptar", "global.quit": "Salir",
    "global.cancel": "Cancelar", "global.saveFile": "Guardar archivo",
    "cocoa.menu.about": "Acerca de", "cocoa.menu.services": "Servicios", "cocoa.menu.view": "Visualización",
    "cocoa.menu.edit": "Edición", "cocoa.menu.hide": "Ocultar", "cocoa.menu.hideOthers": "Ocultar otros",
    "cocoa.menu.showAll": "Mostrar todo", "cocoa.menu.quit": "Salir de", "cocoa.menu.fullscreen": "Pantalla completa",
    "cocoa.menu.cut": "Cortar", "cocoa.menu.copy": "Copiar", "cocoa.menu.paste": "Pegar",
    "cocoa.menu.selectAll": "Seleccionar todo",
}


def _mac_app_name() -> None:
    """Run from the code (not the .app), macOS calls the app «Python» in the menu bar: name it Coralis.
    It has to be set before the window library starts the app."""
    if sys.platform != "darwin":
        return
    try:
        from Foundation import NSBundle

        bundle = NSBundle.mainBundle()
        for info in (bundle.localizedInfoDictionary(), bundle.infoDictionary()):
            if info is not None:
                info["CFBundleName"] = APP_NAME
        import AppKit

        AppKit.NSWindow.setAllowsAutomaticWindowTabbing_(False)   # one window: no «Mostrar barra de pestañas»
    except Exception:  # noqa: BLE001  (only the name in the menu bar)
        traceback.print_exc()


if __name__ == "__main__":
    sys.exit(main())
