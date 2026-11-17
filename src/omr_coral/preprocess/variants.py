"""Image variants of each page, so every engine gets several chances to read it.

    original    the page as extracted
    enderezada  deskewed (staff lines made horizontal)
    limpia      deskewed + background flattened + faint marks removed
                (bleed-through from the back page, paper texture, shadows)
    binaria     limpia, then pure black/white (Otsu)
    contraste   deskewed + local contrast boost (CLAHE), for faded prints
    escala      limpia, resized so the staff interline is ~target_interline px

Variants identical to another one (no skew, already at the right scale) are skipped.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

ALL_VARIANTS = ("original", "enderezada", "limpia", "binaria", "contraste", "escala")
MIN_INTERLINE = 11  # px; Audiveris refuses smaller interlines: only then enlarge the whole page


def _read(path: Path) -> np.ndarray:
    img = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)  # unicode-safe
    if img is None:
        raise ValueError(f"No se pudo leer la imagen {path}")
    return img


def _write(path: Path, img: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise ValueError(f"No se pudo escribir {path}")
    buf.tofile(str(path))


def estimate_skew(gray: np.ndarray, max_deg: float = 3.0, step: float = 0.1) -> float:
    """Angle (degrees) that makes staff lines horizontal: maximizes row-profile sharpness."""
    scale = 1000 / max(gray.shape)
    small = cv2.resize(gray, None, fx=min(1, scale), fy=min(1, scale), interpolation=cv2.INTER_AREA)
    _, bw = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    h, w = bw.shape
    center = (w / 2, h / 2)
    best, best_score = 0.0, -1.0
    for angle in np.arange(-max_deg, max_deg + step / 2, step):
        m = cv2.getRotationMatrix2D(center, angle, 1.0)
        rot = cv2.warpAffine(bw, m, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
        profile = rot.sum(axis=1, dtype=np.float64)
        score = float(np.sum(np.diff(profile) ** 2))
        if score > best_score:
            best, best_score = float(angle), score
    return best


def rotate(gray: np.ndarray, angle: float) -> np.ndarray:
    h, w = gray.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(gray, m, (w, h), flags=cv2.INTER_CUBIC, borderValue=255)


def flatten_background(gray: np.ndarray) -> np.ndarray:
    """Divide by the estimated paper background, then wash out faint marks."""
    k = max(15, (min(gray.shape) // 40) | 1)
    bg = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    bg = cv2.medianBlur(bg, 5)
    norm = cv2.divide(gray, bg, scale=255)
    # Ink is dark; bleed-through and texture end up light gray after normalization.
    t, _ = cv2.threshold(norm, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    cut = min(245, t + (255 - t) * 0.35)
    out = norm.copy()
    out[norm > cut] = 255
    return out


def binarize(gray: np.ndarray) -> np.ndarray:
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return bw


def contrast(gray: np.ndarray) -> np.ndarray:
    return cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)


def estimate_interline(gray: np.ndarray) -> float | None:
    """Distance between staff lines (px): most common black-run start-to-start gap in columns."""
    bw = binarize(gray) == 0  # True = ink
    h, w = bw.shape
    gaps = []
    for x in np.linspace(w * 0.1, w * 0.9, 60).astype(int):
        col = bw[:, x].astype(np.int8)
        starts = np.flatnonzero(np.diff(col) == 1)
        if len(starts) > 1:
            d = np.diff(starts)
            gaps.extend(d[(d >= 6) & (d <= 80)].tolist())
    if not gaps:
        return None
    hist = np.bincount(gaps)
    return float(np.argmax(hist))


def make_variants(page: Path, out_root: Path, names: list[str], target_interline: float = 22.0) -> dict[str, Path]:
    """Write the requested variants of one page. Returns {variant: path} (duplicates skipped)."""
    gray = _read(page)
    # Tiny images (screenshots, web downloads): Audiveris refuses staves with an interline
    # below ~10 px, so every variant would fail except "escala". Enlarge the page itself.
    il = estimate_interline(gray)
    if il and il < MIN_INTERLINE:
        f = target_interline / il
        gray = cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    out: dict[str, Path] = {}
    angle = estimate_skew(gray)
    straight = rotate(gray, angle) if abs(angle) >= 0.15 else gray
    clean = flatten_background(straight)
    produced = {}
    for name in names:
        if name == "original":
            produced[name] = gray
        elif name == "enderezada":
            if straight is gray:
                continue  # page already straight: identical to original
            produced[name] = straight
        elif name == "limpia":
            produced[name] = clean
        elif name == "binaria":
            produced[name] = binarize(clean)
        elif name == "contraste":
            produced[name] = contrast(straight)
        elif name == "escala":
            il = estimate_interline(clean)
            if not il:
                continue
            f = target_interline / il
            if abs(f - 1) < 0.15:
                continue  # already at a good scale
            interp = cv2.INTER_CUBIC if f > 1 else cv2.INTER_AREA
            produced[name] = cv2.resize(clean, None, fx=f, fy=f, interpolation=interp)
        else:
            raise ValueError(f"Variante desconocida: {name} (opciones: {', '.join(ALL_VARIANTS)})")
    for name, img in produced.items():
        p = out_root / name / page.name
        _write(p, img)
        out[name] = p
    return out
