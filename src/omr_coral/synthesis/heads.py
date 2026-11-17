"""Notehead detection in the original image, staff by staff.

Steps, all scaled by the staff interline (distance between staff lines):
  1. binarize the staff band,
  2. erase staff lines and ledger lines, but only where the ink run is as thin as a
     line (so noteheads sitting on a line are kept),
  3. fill the inside of hollow heads (half and whole notes),
  4. open with an ellipse a bit smaller than a head: stems, flags, thin text and
     accidental strokes disappear, heads and beams remain,
  5. keep blobs with head proportions; a tall blob is a stack of heads (a chord of
     seconds/thirds) and is split by height.

Each head is returned with its staff step: 0 = top line, 1 = first space below,
2 = second line... (negative above the staff).
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Head:
    x: float      # page coordinates
    y: float
    step: int     # staff position: 0 top line, +1 per line/space downwards
    staff: int    # index of the staff inside the system (0 = top)


def _erase_lines(bw: np.ndarray, ys: list[float], thickness: int) -> None:
    """Erase horizontal lines at rows ys where the vertical ink run is line-thin."""
    h, w = bw.shape
    limit = thickness + 2
    for y in ys:
        yi = int(round(y))
        if not (0 <= yi < h):
            continue
        for x in np.flatnonzero(bw[yi]):
            # vertical run through (yi, x)
            y0 = yi
            while y0 > 0 and bw[y0 - 1, x]:
                y0 -= 1
            y1 = yi
            while y1 < h - 1 and bw[y1 + 1, x]:
                y1 += 1
            if y1 - y0 + 1 <= limit:
                bw[y0:y1 + 1, x] = 0


def _fill_holes(bw: np.ndarray, max_area: float) -> np.ndarray:
    contours, hier = cv2.findContours(bw, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    out = bw.copy()
    if hier is None:
        return out
    for i, c in enumerate(contours):
        if hier[0][i][3] != -1 and cv2.contourArea(c) <= max_area:  # an inner contour = a hole
            cv2.drawContours(out, [c], -1, 255, thickness=cv2.FILLED)
    return out


def detect_heads(gray: np.ndarray, staff_top: float, interline: float, x0: int, x1: int,
                 staff_index: int = 0, line_thickness: int = 3) -> list[Head]:
    il = interline
    # From 2.7 interlines above the staff to 2.5 below: room for two ledger lines, not for lyrics.
    y0 = int(max(0, staff_top - 2.7 * il))
    y1 = int(min(gray.shape[0], staff_top + 6.5 * il))
    x0, x1 = max(0, int(x0)), min(gray.shape[1], int(x1))
    if x1 - x0 < il or y1 - y0 < il:
        return []
    band = gray[y0:y1, x0:x1]
    _, bw = cv2.threshold(band, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    top = staff_top - y0
    # Fill hollow heads first, while their outline is still closed: erasing the staff
    # lines would cut it. The inside of a head is small (< ~0.7 il²); the gaps between
    # staff lines and stems are much larger and stay open.
    closed = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    bw = _fill_holes(closed, max_area=0.7 * il * il)
    line_ys = [top + k * il for k in range(-3, 8)]  # staff lines + up to 3 ledger lines each side
    _erase_lines(bw, line_ys, line_thickness)
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 3)))

    kw, kh = max(3, int(round(0.75 * il))), max(3, int(round(0.55 * il)))
    heads_only = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kw, kh)))

    n, labels, stats, _ = cv2.connectedComponentsWithStats(heads_only, connectivity=8)
    heads: list[Head] = []

    def add(cx: float, cy: float) -> None:
        step = int(round((cy - top) / (il / 2)))
        heads.append(Head(cx + x0, cy + y0, step, staff_index))

    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if w < 0.8 * il or w > 2.6 * il or h < 0.7 * il:
            continue  # too thin (stems, beams, accidentals) or too wide
        fill = area / float(w * h)
        if fill < 0.35:
            continue  # hollow leftovers / diagonal strokes
        if h > 2.0 * il and fill > 0.85 and w < 1.4 * il:
            continue  # a solid tall rectangle: thick (final) barline
        mask = labels[y:y + h, x:x + w] == i
        if w > 1.6 * il:
            # A chord with a second: heads on both sides of the stem. Treat each half
            # as its own vertical stack.
            half = w // 2
            for part, dx in ((mask[:, :half], 0), (mask[:, half:], half)):
                _stack(part, x + dx, y, il, add)
            continue
        _stack(mask, x, y, il, add)
    return heads


def _stack(mask: np.ndarray, x: int, y: int, il: float, add) -> None:
    """A vertical stack of k touching heads (a chord of thirds) is ~k interlines tall."""
    rows = np.flatnonzero(mask.any(axis=1))
    if len(rows) == 0 or mask.sum() < 0.25 * il * il:
        return
    top, bottom = rows[0], rows[-1] + 1
    k = max(1, int(round((bottom - top) / il)))
    cols = np.flatnonzero(mask.any(axis=0))
    cx = x + (cols[0] + cols[-1] + 1) / 2
    for j in range(k):
        add(cx, y + top + (j + 0.5) * (bottom - top) / k)
