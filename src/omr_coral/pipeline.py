"""High-level steps shared by the CLI commands.

    recognize: pages -> image variants -> every engine on every variant
    validate:  readings -> vote -> rules -> 4-voice MusicXML + report
"""

from __future__ import annotations

import json
from fractions import Fraction
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from .engines import get_engine
from .model.digital import to_two_staves
from .model.export import to_music21
from .model.layout import read_audiveris_layout
from .model.lyrics_fix import fix_ocr_lyrics, merge_elisions, split_glued_syllables
from .model.lyrics_text import apply_lyrics_text, read_lyrics_file
from .model.verses import expand_verses, merge_split_measures
from .model.merge import merge_pages
from .model import corrections
from .model.issues import Issue
from .model.repeats import performance_order
from .model.score import build_choral_score
from .output.report import write_report
from .preprocess.pages import extract_pages
from .preprocess.variants import make_variants
from .rules import run_rules
from .synthesis.refine import refine
from .voting.vote import Candidate, _fix_endings as fix_endings, vote

RESULT_STEM = "resultado"
LYRICS_FILE = "letra.txt"
TITLE_FILE = "titulo.txt"  # name chosen by the user (overrides the title read from the image)


def _safe_name(name: str) -> str:
    return "".join(c for c in name if c not in '<>:"/\\|?*').strip() or "resultado"


# --------------------------------------------------------------------------- recognition


def recognize(src: Path, cfg: dict, runs_dir: Path, lyrics_path: str | None = None,
              title: str | None = None, progress=None) -> Path:
    """Read `src` with every engine on every image variant.

    progress(message, fraction): optional callback for a GUI; fraction in 0..0.9 (validation is the rest).
    """
    def say(msg: str, frac: float | None = None) -> None:
        print(msg)
        if progress:
            progress(msg.strip(), frac)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = runs_dir / f"{_safe_name(title) if title else src.stem}_{stamp}"
    say(f"Carpeta de trabajo: {run_dir}", 0.0)

    pages = extract_pages(src, run_dir / "pages", dpi=cfg["preprocess"]["dpi"])
    if title:
        (run_dir / TITLE_FILE).write_text(title.strip(), encoding="utf-8")
    lyrics = Path(lyrics_path) if lyrics_path else src.with_suffix(".txt")
    if lyrics.is_file():
        shutil.copyfile(lyrics, run_dir / LYRICS_FILE)
        say(f"Letra tomada de {lyrics}")
    say(f"{len(pages)} página(s) a {cfg['preprocess']['dpi']} dpi", 0.03)

    # image variants: {variant: [page paths in order]}
    names = cfg["preprocess"].get("variants") or ["original"]
    if "original" not in names:
        names = ["original", *names]
    variants: dict[str, list[Path]] = {}
    for page in pages:
        for name, path in make_variants(page, run_dir / "variants", names,
                                        cfg["preprocess"].get("target_interline", 22)).items():
            variants.setdefault(name, []).append(path)
    # a variant is usable only if it exists for every page
    variants = {n: ps for n, ps in variants.items() if len(ps) == len(pages)}
    say(f"Variantes de imagen: {', '.join(variants)}", 0.08)

    engines = cfg["recognition"]["engines"]
    for name in engines:  # install missing engines before starting parallel work
        say(f"Preparando {name}...", 0.1)
        get_engine(name, cfg).ensure()

    jobs = [(e, v) for v in variants for e in engines]
    say(f"Leyendo: {len(jobs)} lecturas ({len(engines)} motor(es) × {len(variants)} variante(s))...", 0.12)
    summary = {"input": str(src), "pages": [p.name for p in pages], "readings": []}
    t0 = time.time()

    def run(job):
        engine_name, variant = job
        out_dir = run_dir / "engines" / engine_name / variant
        res = get_engine(engine_name, cfg).recognize(variants[variant], out_dir)
        if res.musicxml:
            merge_pages(res.musicxml, out_dir / RESULT_STEM)
        return job, res

    with ThreadPoolExecutor(max_workers=max(1, int(cfg["tools"].get("parallel_jobs", 2)))) as pool:
        futures = [pool.submit(run, j) for j in jobs]
        for done, fut in enumerate(as_completed(futures), start=1):
            (engine_name, variant), res = fut.result()
            status = "OK" if res.ok else f"FALLÓ ({res.error})"
            say(f"  [{done}/{len(jobs)}] {engine_name} / {variant}: {status}  ({time.time() - t0:.0f} s)",
                0.12 + 0.78 * done / len(jobs))
            summary["readings"].append({"engine": engine_name, "variant": variant, "ok": res.ok,
                                        "error": res.error, "warnings": res.warnings})

    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    if not any(r["ok"] for r in summary["readings"]):
        raise RuntimeError("Ningún motor pudo leer la partitura.")
    return run_dir


# --------------------------------------------------------------------------- readings


def _reading_file(d: Path) -> Path | None:
    for stem in (RESULT_STEM, "book"):  # "book": runs made before voting existed
        for ext in (".mxl", ".musicxml", ".xml"):
            if (d / f"{stem}{ext}").exists():
                return d / f"{stem}{ext}"
    return None


def _spanish_lyrics(cfg: dict) -> bool:
    langs = (cfg.get("recognition", {}).get("lyrics_languages") or "spa").split("+")
    return langs[0] == "spa"


def load_candidates(run_dir: Path, cfg: dict) -> list[Candidate]:
    weights = cfg.get("voting", {}).get("weights", {})
    cands = []
    for engine_dir in sorted((run_dir / "engines").glob("*")):
        for vdir in sorted(engine_dir.glob("*")):
            xml = _reading_file(vdir)
            if not xml:
                continue
            omr = vdir / "book.omr"
            layout = read_audiveris_layout(omr) if omr.exists() else None
            try:
                cs = build_choral_score(xml, layout)
                fix_ocr_lyrics(cs, spanish=_spanish_lyrics(cfg))
                if _spanish_lyrics(cfg):
                    split_glued_syllables(cs)
            except Exception as e:  # noqa: BLE001  (a broken reading must not stop the vote)
                print(f"  Lectura {engine_dir.name}/{vdir.name} descartada: {e}")
                continue
            image_dir = run_dir / "variants" / vdir.name
            if not image_dir.exists():
                image_dir = run_dir / "pages"
            cands.append(Candidate(engine_dir.name, vdir.name, cs, image_dir,
                                   float(weights.get(engine_dir.name, 1.0))))
    _octave_treble_clef(cands, set(cfg.get("voting", {}).get("marks_engines", ["audiveris"])))
    return cands


def _octave_treble_clef(cands: list[Candidate], clef_engines: set) -> None:
    """Men's quartets print the tenors in a treble clef with a small 8 below (an octave lower).
    homr does not see the 8 and reads those notes an octave too high; Audiveris sees it. When
    most Audiveris measures have that clef on the upper staff, homr's upper voices go down."""
    seen = [m.staves[0].clef for c in cands if c.engine in clef_engines for m in c.score.measures if m.staves]
    if not seen or seen.count("G8vb") < len(seen) / 2:
        return
    from music21 import pitch as m21pitch

    for c in cands:
        if c.engine in clef_engines:
            continue
        for m in c.score.measures:
            if not m.staves or m.staves[0].clef != "G":
                continue
            m.staves[0].clef = "G8vb"
            for v in ("soprano", "alto"):
                for e in m.voices.get(v, []):
                    if e.pitch:
                        p = m21pitch.Pitch(e.pitch)
                        p.octave -= 1
                        e.pitch = p.nameWithOctave
                        if e.midi is not None:
                            e.midi -= 12


# --------------------------------------------------------------------------- validation


def final_file(run_dir: Path) -> Path | None:
    marker = run_dir / "final.txt"
    if marker.exists():
        p = run_dir / marker.read_text(encoding="utf-8").strip()
        return p if p.exists() else None
    return None


_STEP_ES = {"C": "do", "D": "re", "E": "mi", "F": "fa", "G": "sol", "A": "la", "B": "si"}
_DUR_ES = {4: "redonda", 3: "blanca con puntillo", 2: "blanca", 1.5: "negra con puntillo", 1: "negra",
           0.75: "corchea con puntillo", 0.5: "corchea", 0.25: "semicorchea", 0.125: "fusa"}
_DUR_ES_FRAC = {Fraction(1, 3): "corchea de tresillo", Fraction(2, 3): "negra de tresillo",
                Fraction(1, 6): "semicorchea de tresillo", Fraction(4, 3): "blanca de tresillo"}


def _describe(events) -> str:
    """'la4 blanca con puntillo, ligada a la siguiente · silencio de negra' (so that versions that
    only differ in a tie or a duration can be told apart)."""
    parts = []
    for e in events:
        if e.filled:
            continue
        dur = _DUR_ES_FRAC.get(Fraction(e.duration)) or _DUR_ES.get(float(e.duration), f"{float(e.duration):g} tiempos")
        if e.is_rest:
            parts.append(f"silencio de {dur}")
            continue
        name = _STEP_ES.get(e.pitch[0], e.pitch[0]) + e.pitch[1:].replace("#", "♯").replace("-", "♭")
        tie = {"start": ", ligada a la siguiente", "stop": ", viene ligada", "continue": ", ligada"}.get(e.tie, "")
        parts.append(f"{name} {dur}{tie}")
    return " · ".join(parts) or "solo silencio"


def _write_versions(run_dir: Path, voted, doubtful: list[int], cfg: dict) -> None:
    """For the review window: in each doubtful measure, every version the readings gave of each
    disputed voice, drawn on its own staff, with how many readings saw it."""
    from .model.score import VOICES
    from .output.render import render_voice_svg

    names = cfg["output"]["parts"]
    out = []
    for k in doubtful:
        m = voted.measures[k]
        voices = {}
        for v in VOICES:
            alts = m.alternatives.get(v, [])
            if len(alts) < 2:
                continue
            current = corrections.version_key(m.voices.get(v, []))
            options = []
            for a in sorted(alts, key=lambda a: -a["weight"]):
                try:
                    svg = render_voice_svg(m, v, a["events"], cfg)
                except Exception:  # noqa: BLE001  (a version that cannot be drawn is still selectable)
                    svg = None
                vk = corrections.version_key(a["events"])
                options.append({"key": vk, "votes": a["weight"], "total": sum(x["weight"] for x in alts),
                                "readings": a["sources"], "svg": svg, "chosen": vk == current,
                                "desc": _describe(a["events"])})
            voices[v] = {"name": names[v]["name"], "options": options}
        if voices:
            out.append({"index": m.index, "label": m.label, "crop": f"report/img/m{m.index:03d}.png",
                        "voices": voices})
    (run_dir / "versiones.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")


def validate_run(run_dir: Path, cfg: dict) -> dict:
    cands = load_candidates(run_dir, cfg)
    if not cands:
        raise FileNotFoundError(f"No hay lecturas en {run_dir / 'engines'}")

    voted, vote_issues, details = vote(cands, cfg)
    vote_issues += refine(voted, cfg)
    # the user's answers in the review (signs the engines missed): they win over the vote
    answers = corrections.load(run_dir)
    vote_issues += corrections.apply(voted, answers)
    fix_endings(voted)  # an ending marked "1.-6." by hand: the rest of it, and the next one is the 7th
    # notes chosen by the user: no longer "readings disagree" / "does not match the image"
    decided = corrections.apply_voices(voted, answers)
    vote_issues = [i for i in vote_issues if not (i.measure in decided and i.rule in ("votacion", "sintesis"))]
    lyrics_file = run_dir / LYRICS_FILE
    if lyrics_file.exists():
        vote_issues += apply_lyrics_text(voted, read_lyrics_file(lyrics_file))
    else:
        vote_issues += merge_elisions(voted)
    # Readings disagreed, but the image confirms the chosen version: not doubtful anymore.
    confirmed = {m.index for m in voted.measures
                 if m.synth is not None and m.synth.similarity >= cfg.get("synthesis", {}).get("confirm", 0.95)}
    vote_issues = [i for i in vote_issues if not (i.rule == "votacion" and i.measure in confirmed)]
    for m, md in zip(voted.measures, details["measures"]):
        if m.synth is not None:
            md["image_similarity"] = round(m.synth.similarity, 3)
    issues = vote_issues + [i for i in run_rules(voted, cfg) if i.severity != "info"]
    # repeats and jumps: a D.S./D.C. whose target sign was not read cannot be written out
    issues += [Issue("repeticion", "aviso", msg, k) for k, msg in performance_order(voted)[1]]

    # the final file: the 4 voices, one verse after another (or stacked, if so configured)
    joined = merge_split_measures(voted)  # a measure cut by a system break is one measure
    final = expand_verses(joined) if cfg["output"].get("verses_separate", True) else joined
    title_file = run_dir / TITLE_FILE
    if title_file.exists() and title_file.read_text(encoding="utf-8").strip():
        voted.title = joined.title = final.title = title_file.read_text(encoding="utf-8").strip()
    voices_xml = run_dir / f"{_safe_name(voted.title or run_dir.name.rsplit('_', 2)[0])}.musicxml"
    to_music21(final, cfg).write("musicxml", fp=str(voices_xml))
    # the same music as printed: 2 staves, verses stacked, repeats and signs kept
    digital_xml = voices_xml.with_name(f"{voices_xml.stem} (copia digital).musicxml")
    to_two_staves(joined, cfg).write("musicxml", fp=str(digital_xml))
    (run_dir / "votacion.json").write_text(json.dumps(details, indent=2, ensure_ascii=False), encoding="utf-8")

    doubtful = sorted({i.measure for i in issues if i.severity != "info" and i.measure is not None})
    _write_versions(run_dir, voted, sorted(set(doubtful) | decided), cfg)  # decided: can be changed again
    result = {
        "readings": [c.label for c in cands],
        "measures": len(voted.measures),
        "verses": voted.verses,
        "doubtful_measures": [voted.measures[i].label for i in doubtful],
        "issues": [{**i.to_dict(),
                    "measure_label": voted.measures[i.measure].label if i.measure is not None else None}
                   for i in issues],
    }
    (run_dir / "validation.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    by_engine: dict[str, int] = {}
    for c in cands:
        by_engine[c.engine] = by_engine.get(c.engine, 0) + 1
    source = ", ".join(f"{e} ×{n}" for e, n in by_engine.items())
    report = write_report(
        voted, issues, cfg, run_dir, f"votación entre {len(cands)} lecturas ({source})",
        files={"Partitura final en 4 voces (MusicXML)": f"../{voices_xml.name}",
               "Copia digital en 2 pentagramas (MusicXML)": f"../{digital_xml.name}",
               "Detalle de la votación (JSON)": "../votacion.json"},
    )
    result["report"] = str(report)
    result["voices_xml"] = str(voices_xml)
    # what the review window shows: every measure with its signs and its crop of the image
    (run_dir / "compases.json").write_text(json.dumps([
        {"index": m.index, "label": m.label, "system": m.system,
         "crop": f"report/img/m{m.index:03d}.png", "marks": corrections.marks_json(m.marks)}
        for m in voted.measures], ensure_ascii=False), encoding="utf-8")
    result["digital_xml"] = str(digital_xml)
    (run_dir / "final.txt").write_text(voices_xml.name, encoding="utf-8")
    return result

