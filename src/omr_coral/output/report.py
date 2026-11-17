"""HTML report of doubtful measures: original crop next to the rendered interpretation."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from importlib import resources
from pathlib import Path

import cv2
import numpy as np
from jinja2 import Environment
from PIL import Image

from ..model.issues import Issue
from ..model.score import ChoralScore
from ..rules import RULE_LABELS
from .render import render_measures_svg


def _crop(pages_dir: Path, m, out: Path) -> str | None:
    if m.bbox is None or m.page is None:
        return None
    page = (m.image_dir or pages_dir) / f"page_{m.page:03d}.png"
    if not page.exists():
        return None
    img = Image.open(page)
    x0, y0, x1, y1 = m.bbox
    img.crop((max(0, x0), max(0, y0), min(img.width, x1), min(img.height, y1))).save(out)
    return out.name


def _verification(m, out: Path) -> str | None:
    """The image with the comparison drawn on it: green = head found where expected,
    red = expected head not printed, blue = printed head the version does not explain."""
    from ..synthesis.refine import geometry_of

    geom = geometry_of(m)
    if geom is None or m.synth is None:
        return None
    img = cv2.imdecode(np.fromfile(str(geom.image), dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None
    il = sum(s[1] for s in geom.staves) / len(geom.staves)
    r = max(4, int(0.65 * il))
    th = max(2, int(il / 8))
    for h in m.synth.found:
        cv2.circle(img, (int(h.x), int(h.y)), r, (40, 160, 40), th)
    for h in m.synth.extra:
        cv2.circle(img, (int(h.x), int(h.y)), r, (220, 120, 0), th)
    for st, step, x, _ in m.synth.missing:
        top, sil = geom.staves[st]
        cv2.drawMarker(img, (int(x), int(top + step * sil / 2)), (30, 30, 220), cv2.MARKER_TILTED_CROSS,
                       2 * r, th)
    x0, x1 = int(max(0, geom.x0 - il)), int(min(img.shape[1], geom.x1 + il))
    y0 = int(max(0, geom.staves[0][0] - 3 * il))
    y1 = int(min(img.shape[0], geom.staves[-1][0] + 7 * il))
    ok, buf = cv2.imencode(".png", img[y0:y1, x0:x1])
    if not ok:
        return None
    buf.tofile(str(out))
    return out.name


def write_report(cs: ChoralScore, issues: list[Issue], cfg: dict, run_dir: Path, engine: str,
                 files: dict[str, str]) -> Path:
    report_dir = run_dir / "report"
    img_dir = report_dir / "img"
    img_dir.mkdir(parents=True, exist_ok=True)

    by_measure: dict[int, list[Issue]] = defaultdict(list)
    for i in issues:
        if i.severity != "info" and i.measure is not None:
            by_measure[i.measure].append(i)

    cards = []
    for m in cs.measures:
        idx = m.index
        its = sorted(by_measure.get(idx, []), key=lambda i: (i.severity != "error", i.rule))
        crop = _crop(run_dir / "pages", m, img_dir / f"m{idx:03d}.png")
        verif = _verification(m, img_dir / f"v{idx:03d}.png")
        try:
            svg = render_measures_svg(cs, cfg, [idx])
        except Exception as e:  # noqa: BLE001
            svg = f"<p class='muted'>No se pudo renderizar: {e}</p>"
        if not its:
            severity = "ok"
        else:
            severity = "error" if any(i.severity == "error" for i in its) else "aviso"
        cards.append({
            "idx": idx,
            "label": m.label,
            "system": m.system,
            "page": m.page,
            "severity": severity,
            "rules": sorted({i.rule for i in its}),
            "issues": its,
            "crop": f"img/{crop}" if crop else None,
            "verif": f"img/{verif}" if verif else None,
            "similarity": m.synth.similarity if m.synth is not None else None,
            "svg": svg,
            "votes": [
                {"voice": cfg["output"]["parts"][v]["name"], "weight": d["weight"], "total": d["total"],
                 "ratio": d["weight"] / d["total"] if d["total"] else 0, "versions": d["versions"]}
                for v, d in m.votes.items()
            ],
        })

    rule_counts = Counter(r for c in cards for r in c["rules"])
    env = Environment(autoescape=True)
    tpl = env.from_string(resources.files("omr_coral.output").joinpath("report.html.j2").read_text(encoding="utf-8"))
    html = tpl.render(
        title=cs.title or run_dir.name.rsplit("_", 2)[0],
        engine=engine,
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        total=len(cs.measures),
        n_error=sum(1 for c in cards if c["severity"] == "error"),
        n_aviso=sum(1 for c in cards if c["severity"] == "aviso"),
        infos=[i for i in issues if i.severity == "info"],
        cards=cards,
        rule_counts=sorted(rule_counts.items(), key=lambda kv: -kv[1]),
        rule_labels=RULE_LABELS,
        files=files,
    )
    out = report_dir / "index.html"
    out.write_text(html, encoding="utf-8")
    return out
