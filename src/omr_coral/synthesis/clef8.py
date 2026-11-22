"""Is there a small «8» under the treble clef of the upper staff? (the clef of tenors: sung an octave
lower). Audiveris misses it on some engravings and homr never sees it; then the upper voices come out
an octave high («Tengo un amigo», «Viene el día», «Al Rey adorad»). The page image tells: under the
clef, an «8» is a small figure with exactly two holes — the clef's tail, a «1.» or a letter has not.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def _figures_with_two_holes(gray: np.ndarray, il: float) -> int:
    """How many «8»-sized figures with two holes there are in this crop."""
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    contours, hierarchy = cv2.findContours(bw, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return 0
    found = 0
    for k, c in enumerate(contours):
        if hierarchy[0][k][3] != -1:      # a hole, not an outer shape
            continue
        x, y, w, h = cv2.boundingRect(c)
        if not (0.5 * il <= h <= 2.4 * il and 0.3 * il <= w <= 1.8 * il and h >= 0.9 * w):
            continue
        holes, child = 0, hierarchy[0][k][2]
        while child != -1:
            if cv2.contourArea(contours[child]) >= 0.01 * il * il:
                holes += 1
            child = hierarchy[0][child][0]
        if holes == 2:
            found += 1
    return found


def octave_eight(layout, image_dir: Path) -> bool | None:
    """True when most systems show an «8» under the upper staff's clef; None when it cannot tell."""
    seen = checked = 0
    pages: dict[int, np.ndarray] = {}
    for s in layout:
        if len(s.staves) not in (2, 4):
            continue
        il = s.interline or 20
        if s.page not in pages:
            f = image_dir / f"page_{s.page:03d}.png"
            if not f.exists():
                continue
            pages[s.page] = cv2.imdecode(np.fromfile(str(f), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        page = pages[s.page]
        if page is None:
            continue
        st = s.staves[0]
        # under the clef: from below its tail down to where a low-hanging «8» can sit
        x0, x1 = int(st.left), int(st.left + 4.5 * il)
        y0, y1 = int(st.bottom + 0.6 * il), int(st.bottom + 5.5 * il)
        crop = page[max(0, y0):max(0, y1), max(0, x0):max(0, x1)]
        if crop.size == 0:
            continue
        checked += 1
        seen += _figures_with_two_holes(crop, il) > 0
    if not checked:
        return None
    return seen * 2 > checked


def _full_height_strokes(gray: np.ndarray, top: int, bottom: int, x0: int, x1: int) -> list[tuple[int, int]]:
    """Columns (as runs) dark over almost the whole staff height, left to right."""
    band = gray[top:bottom, x0:x1] < 128
    if band.size == 0:
        return []
    full = band.mean(axis=0) >= 0.75   # the old clef's bars ~0.8; a treble clef's stem ≤ 0.7
    runs, start = [], None
    for k, on in enumerate(list(full) + [False]):
        if on and start is None:
            start = k
        elif not on and start is not None:
            runs.append((x0 + start, x0 + k))
            start = None
    return runs


def old_tenor_clef(layout, image_dir: Path) -> bool | None:
    """The old tenor clef of men's hymnals (Simmonds): two thick bars across the staff right after
    the system's opening barline, where a treble clef has a single stem. True when most systems'
    upper staff shows it."""
    seen = checked = 0
    pages: dict[int, np.ndarray] = {}
    for s in layout:
        if len(s.staves) < 2:
            continue
        il = s.interline or 20
        if s.page not in pages:
            f = image_dir / f"page_{s.page:03d}.png"
            if not f.exists():
                continue
            pages[s.page] = cv2.imdecode(np.fromfile(str(f), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        page = pages[s.page]
        if page is None:
            continue
        st = s.staves[0]
        top, bottom = int(st.top + 0.1 * il), int(st.bottom - 0.1 * il)
        runs = _full_height_strokes(page, top, bottom, int(st.left - 1.5 * il), int(st.left + 4 * il))
        if not runs:
            continue
        checked += 1
        after = runs[1:]   # after the opening barline
        bars = [r for r in after if r[1] - r[0] >= 0.15 * il and r[0] - runs[0][1] < 3 * il]
        twin = False
        for a1, a2 in zip(bars, bars[1:]):
            w1, w2 = a1[1] - a1[0], a2[1] - a2[0]
            # two bars of about the same weight, close together (a bracket and a thin barline are not)
            if 0.3 * il <= a2[0] - a1[1] <= 1.2 * il and max(w1, w2) <= 2 * min(w1, w2):
                twin = True
        seen += twin
    if not checked:
        return None
    # a treble clef with its «8» is not this clef (the bracket and barline before it look like two bars)
    return seen * 2 > checked and not octave_eight(layout, image_dir)
