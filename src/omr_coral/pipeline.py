"""High-level steps shared by the CLI commands.

    recognize: pages -> image variants -> every engine on every variant
    validate:  readings -> vote -> rules -> 4-voice MusicXML + report
"""

from __future__ import annotations

import json
import re
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
from .model.lyrics_fix import fix_ocr_lyrics, merge_elisions, split_glued_syllables, lower_ocr_capitals
from .model.lyrics_text import apply_lyrics_text, read_lyrics_file
from .model.structure import apply_signatures, apply_structure
from .model.verses import expand_verses, merge_split_measures
from .model.merge import merge_pages
from .model import corrections
from .model.issues import Issue
from .model.repeats import drop_echo_lines, performance_order, split_part_lines
from .model.score import build_choral_score
from .output.report import write_report
from .preprocess.pages import extract_pages
from .preprocess.variants import make_variants
from .rules import run_rules
from .synthesis.refine import refine
from .voting.vote import Candidate, _fix_endings as fix_endings, vote

RESULT_STEM = "resultado"
LYRICS_FILE = "letra.txt"
NAMES_FILE = "voces.json"  # the names the user gave the voices of this hymn («Primer tenor»…)
TITLE_FILE = "titulo.txt"  # name chosen by the user (overrides the title read from the image)


def _safe_name(name: str) -> str:
    # a title ending in a period («Vive.») would give «Vive..musicxml»; Windows drops trailing dots too
    return "".join(c for c in name if c not in '<>:"/\\|?*').strip().rstrip(". ") or "resultado"


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
            try:
                merge_pages(res.musicxml, out_dir / RESULT_STEM)
            except Exception as e:  # noqa: BLE001  (one reading that cannot be joined must not stop the rest)
                res.ok, res.error = False, f"no se pudieron unir las páginas: {e!r}"[:300]
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
    # how many staves a system has, as Audiveris saw it (homr sometimes reads a 4-staff open score
    # as pairs of 2-staff systems: «Paz es la voz»)
    seen = [len(st.staves) for d in (run_dir / "engines" / "audiveris").glob("*")
            if (d / "book.omr").exists() for st in (_safe_layout(d / "book.omr") or [])]
    staves = max(set(seen), key=seen.count) if seen else 0
    for engine_dir in sorted((run_dir / "engines").glob("*")):
        for vdir in sorted(engine_dir.glob("*")):
            xml = _reading_file(vdir)
            if not xml:
                continue
            omr = vdir / "book.omr"
            layout = read_audiveris_layout(omr) if omr.exists() else None
            try:
                cs = build_choral_score(xml, layout, staves_per_system=0 if layout else staves)
                fix_ocr_lyrics(cs, spanish=_spanish_lyrics(cfg))
                if _spanish_lyrics(cfg):
                    split_glued_syllables(cs)
                    lower_ocr_capitals(cs)
            except Exception as e:  # noqa: BLE001  (a broken reading must not stop the vote)
                print(f"  Lectura {engine_dir.name}/{vdir.name} descartada: {e}")
                continue
            image_dir = run_dir / "variants" / vdir.name
            if not image_dir.exists():
                image_dir = run_dir / "pages"
            cands.append(Candidate(engine_dir.name, vdir.name, cs, image_dir,
                                   float(weights.get(engine_dir.name, 1.0))))
    _old_tenor_clef(cands)
    _octave_treble_clef(cands, set(cfg.get("voting", {}).get("marks_engines", ["audiveris"])))
    return _drop_broken_systems(cands, staves)


def _old_tenor_clef(cands: list[Candidate]) -> None:
    """Men's quartet hymnals (Simmonds, «Para cuartetos varoniles») print the upper staff in an old
    tenor clef (two short bars) that no engine knows: each reading takes it for a G, F or C clef
    («El mundo no es mi hogar»). In an ordinary hymn every reading agrees on the upper clef; when
    some readings see G and others F or C over an F-clef lower staff, it is that clef: a treble
    clef an octave down. The readings that saw G get the octave (as G8vb); the upper voices of the
    others are wrong by a sixth or so and are ruled out of the vote (their words still count)."""
    def upper(m):
        return m.staves[0] if len(m.staves) == 2 and m.staves[1].clef == "F" else None

    per_cand = []
    for c in cands:
        clefs = [st.clef for m in c.score.measures for st in [upper(m)] if st is not None]
        if clefs:
            per_cand.append((c, max(set(clefs), key=clefs.count)))
    seen = {clef for _, clef in per_cand}
    g_like = [c for c, clef in per_cand if clef in ("G", "G8vb")]
    odd = [c for c, clef in per_cand if clef in ("F", "C")]
    if not (g_like and odd and len(g_like) >= 2 and seen <= {"G", "G8vb", "F", "C"}):
        return
    from music21 import pitch as m21pitch

    for c in cands:   # any upper staff read as a plain G, in any reading
        for m in c.score.measures:
            st = upper(m)
            if st is None or st.clef != "G":
                continue
            st.clef = "G8vb"
            clefs = (m.geometry or {}).get("clefs")
            if clefs and clefs[0] == "G":
                clefs[0] = "G8vb"
            for v in ("soprano", "alto"):
                for e in m.voices.get(v, []):
                    if e.pitch:
                        p = m21pitch.Pitch(e.pitch)
                        p.octave -= 1
                        e.pitch = p.nameWithOctave
                        if e.midi is not None:
                            e.midi -= 12
    for c in cands:   # measure by measure: a reading may see G on one system and F on the next
        for j, m in enumerate(c.score.measures):
            st = upper(m)
            if st is not None and st.clef in ("F", "C"):
                for v in ("soprano", "alto"):
                    c.issues.append(Issue("rango", "error", "Clave antigua de tenor leída como otra clave.", j, v))


def _drop_broken_systems(cands: list[Candidate], staves: int) -> list[Candidate]:
    """An open score (a staff per voice, as Audiveris saw it) that homr cut into loose 1- and
    2-staff systems («Paz es la voz»: 118-126 measures where there are 71, voices crossed): those
    readings would vote wrong voices, so they are left out when Audiveris' readings agree."""
    if staves < 4:
        return cands
    counts = sorted(len(c.score.measures) for c in cands if c.engine == "audiveris")
    if len(counts) < 2:
        return cands
    ref = counts[len(counts) // 2]
    keep = [c for c in cands if c.engine == "audiveris" or len(c.score.measures) <= 1.25 * ref]
    for c in cands:
        if c not in keep:
            print(f"  Lectura {c.engine}/{c.variant} descartada: partió los sistemas de {staves} pentagramas "
                  f"({len(c.score.measures)} compases donde Audiveris ve {ref}).")
    return keep


def _safe_layout(omr: Path):
    try:
        return read_audiveris_layout(omr)
    except Exception:  # noqa: BLE001
        return None


def _octave_treble_clef(cands: list[Candidate], clef_engines: set) -> None:
    """Men's quartets print the upper staff in a treble clef with a small 8 below (an octave
    lower). homr never sees the 8 and Audiveris misses it on some systems; a piece does not
    change that clef from one system to the next. When most of the upper staves Audiveris read
    have it, every upper staff read as a plain treble clef goes down an octave."""
    def upper_staves(m):
        """The staves of the upper voices with the voices each one carries: one staff for both
        (a hymnal's two staves, or an upper solo), or one staff per voice (an open score of four
        staves: «Venid a mí los tristes»)."""
        if len(m.staves) == 2 or (len(m.staves) == 1 and m.solo == "upper"):
            return [(0, m.staves[0], ("soprano", "alto"))]
        if len(m.staves) == 4:
            return [(0, m.staves[0], ("soprano",)), (1, m.staves[1], ("alto",))]
        return []

    seen = [st.clef for c in cands if c.engine in clef_engines for m in c.score.measures
            for _, st, _ in upper_staves(m) if st.clef in ("G", "G8vb")]
    if not seen or seen.count("G8vb") <= len(seen) / 2:
        return
    from music21 import pitch as m21pitch

    for c in cands:
        for m in c.score.measures:
            for k, st, voices in upper_staves(m):
                if st.clef != "G":
                    continue
                st.clef = "G8vb"
                clefs = (m.geometry or {}).get("clefs")
                if clefs and len(clefs) > k and clefs[k] == "G":
                    clefs[k] = "G8vb"  # where analysis by synthesis expects the heads
                for v in voices:
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


def _write_versions(run_dir: Path, voted, doubtful: list[int], cfg: dict, edits: dict | None = None) -> None:
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
            alts = m.alternatives.get(v, []) or [{"events": m.voices.get(v, []), "weight": 1, "sources": []}]
            if not any(not e.is_rest for a in alts for e in a["events"]):
                continue  # this voice rests: nothing to choose or fix
            current = corrections.version_key(m.voices.get(v, []))
            options = []
            fixed = ((edits or {}).get(str(m.index)) or {}).get(v)
            if fixed:  # the user fixed pitches by hand: that is what stands now
                try:
                    svg = render_voice_svg(m, v, m.voices.get(v, []), cfg)
                except Exception:  # noqa: BLE001
                    svg = None
                options.append({"key": current, "votes": 0, "total": 0, "readings": [], "svg": svg,
                                "chosen": True, "edited": True, "edits": fixed,
                                "desc": _describe(m.voices.get(v, [])), "events": _events_json(m.voices.get(v, []))})
            for a in sorted(alts, key=lambda a: -a["weight"]):
                try:
                    svg = render_voice_svg(m, v, a["events"], cfg)
                except Exception:  # noqa: BLE001  (a version that cannot be drawn is still selectable)
                    svg = None
                vk = corrections.version_key(a["events"])
                options.append({"key": vk, "votes": a["weight"], "total": sum(x["weight"] for x in alts),
                                "readings": a["sources"], "svg": svg, "chosen": vk == current and not fixed,
                                "base": bool(fixed) and a.get("chosen", False),
                                "desc": _describe(a["events"]), "events": _events_json(a["events"])})
            voices[v] = {"name": names[v]["name"], "options": options}
        if voices:
            out.append({"index": m.index, "label": m.label, "crop": f"report/img/m{m.index:03d}.png",
                        "voices": voices})
    (run_dir / "versiones.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")


def _events_json(events) -> list[dict]:
    return [{"offset": str(e.offset), "duration": str(e.duration), "pitch": e.pitch, "tie": e.tie,
             "filled": e.filled, "slur": e.slur_cont} for e in events]


def _write_notes(run_dir: Path, voted) -> None:
    """Every measure as it stands (for «Ir al compás…» and the note editor of the window)."""
    from .model.score import VOICES

    from .model.score import lyric_voice

    def vwords(m, v) -> dict:
        out: dict = {}
        for e in m.voices.get(v, []):
            for n, (text, syl) in sorted(e.lyrics.items()):
                out.setdefault(str(n), []).append([str(e.offset), text, syl])
        return out

    def words(m) -> dict:
        out: dict = {}
        for e in m.voices.get(lyric_voice(m), []):
            for n, (text, syl) in sorted(e.lyrics.items()):
                out.setdefault(str(n), []).append([str(e.offset), text, syl])
        return out

    out = [{"index": m.index, "label": m.label, "number": m.number, "time": list(m.time),
            "key": m.key_fifths, "pickup": m.pickup, "bar_length": str(m.bar_length),
            "duration": str(m.duration), "crop": f"report/img/m{m.index:03d}.png",
            "voices": {v: _events_json(m.voices.get(v, [])) for v in VOICES},
            "words": words(m), "lyric_voice": lyric_voice(m), "own_words": m.own_words,
            "vwords": {v: vwords(m, v) for v in VOICES}} for m in voted.measures]
    (run_dir / "notas.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")


def voice_names(run_dir: Path, cfg: dict) -> dict:
    """{voice: name} for this hymn: the configured names, or the ones the user gave it."""
    names = {v: p["name"] for v, p in cfg["output"]["parts"].items()}
    f = run_dir / NAMES_FILE
    if f.exists():
        try:
            mine = json.loads(f.read_text(encoding="utf-8"))
            names.update({v: str(n).strip() for v, n in mine.items() if v in names and str(n).strip()})
        except (OSError, ValueError):
            pass
    return names


def cfg_for(run_dir: Path, cfg: dict) -> dict:
    """The configuration with this hymn's voice names (the parts of every file it writes)."""
    import copy

    out = copy.deepcopy(cfg)
    for v, n in voice_names(run_dir, cfg).items():
        out["output"]["parts"][v]["name"] = n
    return out


def validate_run(run_dir: Path, cfg: dict) -> dict:
    cfg = cfg_for(run_dir, cfg)
    cands = load_candidates(run_dir, cfg)
    if not cands:
        raise FileNotFoundError(f"No hay lecturas en {run_dir / 'engines'}")

    voted, vote_issues, details = vote(cands, cfg)
    vote_issues += refine(voted, cfg)
    # the user's answers in the review (signs the engines missed): they win over the vote
    answers = corrections.load(run_dir)
    # measures added or removed by hand: everything else the user saved refers to the measures after that
    where = apply_structure(voted, answers)
    if len(where) != len(voted.measures) or any(o != n for o, n in where.items()):
        vote_issues = [i for i in vote_issues if i.measure is None or where.get(i.measure) is not None]
        for i in vote_issues:
            if i.measure is not None:
                i.measure = where[i.measure]
        by_new = {n: md for o, md in enumerate(details["measures"]) if (n := where.get(o)) is not None}
        details["measures"] = [by_new.get(k, {"index": k, "added_by_hand": True}) for k in range(len(voted.measures))]
    vote_issues += corrections.apply(voted, answers)
    fix_endings(voted)  # an ending marked "1.-6." by hand: the rest of it, and the next one is the 7th
    apply_signatures(voted, answers)  # time / key signatures given by hand (before the rhythm)
    # notes chosen by the user: no longer "readings disagree" / "does not match the image"
    decided = corrections.apply_voices(voted, answers)
    decided |= corrections.apply_rhythm(voted, answers)  # notes moved by hand (rhythm), after the version chosen
    decided |= corrections.apply_edits(voted, answers)  # pitches fixed by hand, after the version chosen
    vote_issues = [i for i in vote_issues if not (i.measure in decided and i.rule in ("votacion", "sintesis"))]
    if split_part_lines(voted):
        vote_issues.append(Issue("estructura", "info",
                                 "Las líneas de letra que empiezan a mitad de la pieza son de otras voces (los "
                                 "hombres responden con su propia letra), no estrofas: van en esas voces."))
    for n in drop_echo_lines(voted):
        vote_issues.append(Issue("estructura", "info",
                                 f"La línea de letra {n} repite la línea 1 (letra de otras voces en el coro): "
                                 "no se cuenta como estrofa."))
    lyrics_file = run_dir / LYRICS_FILE
    own = None
    if not lyrics_file.exists() and cfg.get("recognition", {}).get("own_lyrics_ocr", True):
        from .model.lyrics_text import verse_syllables
        from .ocr.lyrics_ocr import (audiveris_stanzas, complete, correct, coverage, drop_verses, lyric_slots,
                                      rows_for, skipped_words, stanzas)

        # Coralis' own reading of the lyrics lines, matched with the stanzas the vote found
        rows = rows_for(run_dir)
        theirs = audiveris_stanzas(voted)
        found = stanzas(rows, theirs) if rows else None
        slots = lyric_slots(voted)
        if found:
            noise = {n for n, t in enumerate(found, start=1) if t is None}
            if noise:   # a «stanza» that was only a speck read by Audiveris
                drop_verses(voted, noise)
                vote_issues.append(Issue("letra", "info", f"Se quitó {len(noise)} renglón(es) de letra que "
                                                          "Audiveris leyó de una mancha (casi sin texto)."))
                theirs = audiveris_stanzas(voted)
                found = [t for t in found if t is not None]
            own = [complete(verse_syllables(t), th) for t, th in zip(found, theirs)]
    if lyrics_file.exists():
        vote_issues += apply_lyrics_text(voted, read_lyrics_file(lyrics_file))
    elif own and (len(own) >= 2 or min(coverage(o, th) for o, th in zip(own, theirs)) < 0.8):
        # stanzas stacked under the same notes (clean lines), or Audiveris lost much of the words:
        # Coralis' text is placed whole (as if the user gave a .txt). In a long through-composed
        # piece Audiveris read well, placing it all again only risks shifting it (see correct).
        # a stanza where Coralis read clearly fewer syllables than Audiveris skipped words («Sublime
        # gracia» lost «per-di-do fui, mi Dios me ha-lló»): it keeps Audiveris' words, mended
        short = skipped_words(own, theirs)
        kept = {v: [(t, syl, e) for t, syl, e in theirs[v - 1]] for v in short}
        placed = apply_lyrics_text(voted, own)
        for v in short:
            for m in voted.measures:
                for evs in m.voices.values():
                    for e in evs:
                        e.lyrics.pop(v, None)
            for t, syl, e in kept[v]:
                e.lyrics[v] = (t, syl)
        # a stanza that does not fit on the notes (other voices' words read on the same line…): its
        # Audiveris words stay, with the misread syllables mended
        failed = {int(m.group(1)) for i in placed if i.severity == "error"
                  for m in [re.match(r"La estrofa (\d+) del archivo", i.message)] if m} | short
        vote_issues += [i for i in placed if not (i.severity == "error" and i.message.startswith("La estrofa "))]
        mended = sum(correct(own[v - 1], theirs[v - 1], v, slots) for v in sorted(failed))
        vote_issues += merge_elisions(voted) if failed else []
        vote_issues.append(Issue("letra", "info", f"Letra leída por Coralis en la imagen ({len(own)} estrofa(s)), "
                                                  "colocada guiándose por lo que leyó Audiveris."
                                 + (f" La estrofa {', '.join(map(str, sorted(failed)))} no cabía en las notas: se dejó "
                                    f"la de Audiveris corrigiendo {mended} sílaba(s)." if failed else "")))
    elif own:
        # Audiveris read nearly everything: its words stay where they are, misread syllables are mended
        n = sum(correct(o, th, v, slots) for v, (o, th) in enumerate(zip(own, theirs), start=1))
        vote_issues += merge_elisions(voted)
        if n:
            vote_issues.append(Issue("letra", "info", f"Coralis volvió a leer la letra en la imagen y corrigió {n} sílaba(s) "
                                                      "que Audiveris había leído mal."))
    else:
        vote_issues += merge_elisions(voted)
    corrections.apply_lyrics(voted, answers)  # words typed note by note: they have the last word
    corrections.apply_voice_lyrics(voted, answers)  # a voice that sings other words, typed for it
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

    # The notehead check alone seldom tells a right measure from a wrong one: in the 9 hand-made
    # hymns, 91 % of the measures it alone flagged had every note right — as many as the measures
    # with no warning at all (90 %) (2026-11-21). Its telling sign is a note in the wrong place: an
    # expected head missing AND a printed head unexplained, with low similarity (a tenor an octave
    # high, «Mi Dios majestuoso» c.17-18: 2 of 6 such measures were wrong, 1 of 10 otherwise).
    # Otherwise it stays in the report, and the measure is doubtful only if something else is.
    if cfg.get("synthesis", {}).get("alone_is_doubtful", False) is False:
        by_index = {m.index: m for m in voted.measures}
        other = {i.measure for i in issues
                 if i.severity != "info" and i.rule not in ("sintesis", "letra") and i.measure is not None}
        for i in issues:
            if i.rule != "sintesis" or i.severity == "info" or i.measure in other:
                continue
            r = getattr(by_index.get(i.measure), "synth", None)
            if not (r and r.missing and r.extra and r.similarity < 0.75):
                i.severity = "info"
    doubtful = sorted({i.measure for i in issues if i.severity != "info" and i.measure is not None})
    _write_versions(run_dir, voted, sorted(set(doubtful) | decided), cfg,  # decided: can be changed again
                    answers.get("edits"))
    _write_notes(run_dir, voted)
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

