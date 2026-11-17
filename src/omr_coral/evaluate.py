"""Compare results with a hand-made correct MusicXML, measure by measure.

A note is correct when both its pitch and its duration match (notes of each voice
are aligned in order, so one missing note does not ruin the rest of the measure).
Syllables are compared ignoring punctuation and elision marks.

"Before" = each single reading (one engine on one image variant), written out
verse by verse like the final file. "After" = the final file of the run.
"""

from __future__ import annotations

import html
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

from .model.score import VOICES, ChoralScore, build_choral_score
from .model.verses import expand_verses, merge_split_measures
from .voting.align import align


def _notes(m, v):
    return [(e.pitch, e.duration) for e in m.voices.get(v, []) if not e.is_rest]


def _syllables(m, v):
    out = []
    for e in m.voices.get(v, []):
        if 1 in e.lyrics:
            t = re.sub(r"[.,;:!?¡¿\"'’“”«»]", "", e.lyrics[1][0])
            out.append(re.sub(r"\s+", " ", t.replace("‿", " ").replace("", " ")).strip().lower())
    return out


def _matches(a, b) -> int:
    return sum(x.size for x in SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks())


def score_against(rec: ChoralScore, gt: ChoralScore) -> dict:
    mapping = ({i: i for i in range(len(gt.measures))} if len(rec.measures) == len(gt.measures)
               else align(gt.measures, rec.measures))
    rows = []
    for k, g in enumerate(gt.measures):
        j = mapping.get(k)
        r = rec.measures[j] if j is not None else None
        n_tot = sum(len(_notes(g, v)) for v in VOICES)
        n_ok = sum(_matches(_notes(r, v), _notes(g, v)) for v in VOICES) if r else 0
        s_tot = sum(len(_syllables(g, v)) for v in VOICES)
        s_ok = sum(_matches(_syllables(r, v), _syllables(g, v)) for v in VOICES) if r else 0
        rows.append({"measure": k + 1, "notes": n_tot, "notes_ok": n_ok, "syllables": s_tot, "syllables_ok": s_ok})
    n = sum(r["notes"] for r in rows)
    s = sum(r["syllables"] for r in rows)
    return {
        "rows": rows,
        "notes_pct": 100 * sum(r["notes_ok"] for r in rows) / n if n else 100.0,
        "syllables_pct": 100 * sum(r["syllables_ok"] for r in rows) / s if s else 100.0,
        "measures_perfect": sum(1 for r in rows if r["notes_ok"] == r["notes"]),
        "measures": len(rows),
    }


def find_ground_truth(run_dir: Path, folder: Path = Path("ground_truth")) -> Path | None:
    summary = run_dir / "summary.json"
    if not summary.exists():
        return None
    stem = Path(json.loads(summary.read_text(encoding="utf-8"))["input"]).stem
    for ext in (".mxl", ".musicxml", ".xml"):
        if (folder / f"{stem}{ext}").exists():
            return folder / f"{stem}{ext}"
    return None


def evaluate_run(run_dir: Path, gt_path: Path, final_path: Path, cfg: dict) -> dict:
    from .pipeline import load_candidates

    gt = build_choral_score(gt_path)
    final = build_choral_score(final_path)
    n_verses = max(1, _verse_blocks(final))
    result = {"ground_truth": str(gt_path), "final": score_against(final, gt), "readings": {}}
    for c in load_candidates(run_dir, cfg):
        result["readings"][c.label] = score_against(expand_verses(merge_split_measures(c.score), n_verses), gt)
    (run_dir / "evaluacion.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    (run_dir / "evaluacion.html").write_text(_html(result, run_dir.name), encoding="utf-8")
    return result


def _verse_blocks(cs: ChoralScore) -> int:
    """Verses in a written-out file = silent bars between blocks + 1."""
    silent = sum(1 for m in cs.measures if all(not _notes(m, v) for v in VOICES))
    return silent + 1


def summary_lines(result: dict) -> list[str]:
    lines = []
    readings = result["readings"]
    if readings:
        best = max(readings.items(), key=lambda kv: kv[1]["notes_pct"])
        worst = min(readings.items(), key=lambda kv: kv[1]["notes_pct"])
        lines.append(f"  Antes (un solo motor): notas correctas entre {worst[1]['notes_pct']:.1f}% ({worst[0]}) "
                     f"y {best[1]['notes_pct']:.1f}% ({best[0]})")
    f = result["final"]
    lines.append(f"  Después (resultado final): {f['notes_pct']:.1f}% de notas correctas, "
                 f"{f['measures_perfect']}/{f['measures']} compases perfectos, "
                 f"{f['syllables_pct']:.1f}% de sílabas correctas")
    return lines


def _html(result: dict, name: str) -> str:
    final = result["final"]["rows"]
    readings = sorted(result["readings"].items())
    head = "".join(f"<th>{html.escape(k)}</th>" for k, _ in readings)

    def cell(ok, tot):
        pct = 100 * ok / tot if tot else 100
        cls = "ok" if pct == 100 else "mid" if pct >= 75 else "bad"
        return f"<td class='{cls}'>{ok}/{tot}</td>"

    body = []
    for i, row in enumerate(final):
        cells = "".join(cell(r["rows"][i]["notes_ok"], r["rows"][i]["notes"]) for _, r in readings)
        body.append(f"<tr><td>{row['measure']}</td>{cells}{cell(row['notes_ok'], row['notes'])}"
                    f"{cell(row['syllables_ok'], row['syllables'])}</tr>")
    totals = "".join(f"<td><b>{r['notes_pct']:.1f}%</b></td>" for _, r in readings)
    f = result["final"]
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Evaluación · {html.escape(name)}</title>
<style>
:root {{ --bg:#f6f5f2; --text:#1d1d1b; --muted:#6b6a66; --border:#e3e1dc; --ok:#e6f4ea; --mid:#fff4d6; --bad:#fdecea; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#161615; --text:#ecebe8; --muted:#a3a19c; --border:#33322f;
  --ok:#173323; --mid:#362d14; --bad:#3a1d1b; }} }}
body {{ margin:0; background:var(--bg); color:var(--text); font:14px/1.5 system-ui, sans-serif; }}
main {{ max-width:1200px; margin:0 auto; padding:24px 16px; }}
.wrap {{ overflow-x:auto; }} table {{ border-collapse:collapse; font-variant-numeric:tabular-nums; }}
th, td {{ border:1px solid var(--border); padding:4px 8px; text-align:center; white-space:nowrap; }}
td.ok {{ background:var(--ok); }} td.mid {{ background:var(--mid); }} td.bad {{ background:var(--bad); }}
.muted {{ color:var(--muted); }}
</style></head><body><main>
<h1>Evaluación</h1>
<p class="muted">Comparado con {html.escape(result['ground_truth'])}. Notas correctas (altura y duración) por compás.</p>
<p><b>Resultado final:</b> {f['notes_pct']:.1f}% de notas correctas · {f['measures_perfect']}/{f['measures']} compases
perfectos · {f['syllables_pct']:.1f}% de sílabas correctas.</p>
<div class="wrap"><table>
<tr><th>Compás</th>{head}<th>Final: notas</th><th>Final: sílabas</th></tr>
{''.join(body)}
<tr><td><b>Total</b></td>{totals}<td><b>{f['notes_pct']:.1f}%</b></td><td><b>{f['syllables_pct']:.1f}%</b></td></tr>
</table></div></main></body></html>"""
