"""Text lines of a page image, read by the operating system's own text recognizer.

macOS: Vision (VNRecognizeTextRequest). Windows: Windows.Media.Ocr (to come). Elsewhere, or if the
recognizer is missing, no lines: Coralis then keeps what Audiveris read.

Each line: {"text", "x0", "y0", "x1", "y1"} in pixels of the image, y growing downwards.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path


def available() -> bool:
    if sys.platform == "darwin":
        try:
            import Vision  # noqa: F401
            return True
        except ImportError:
            return False
    return False


def read_lines(image, languages: tuple[str, ...] = ("es-ES", "en-US")) -> list[dict]:
    """`image`: a path or a PIL image (a cropped band reads much better than a whole page)."""
    if sys.platform == "darwin":
        try:
            return _vision_lines(image, languages)
        except Exception:  # noqa: BLE001  (no recognizer: keep Audiveris' lyrics)
            return []
    return []


def _vision_lines(image, languages) -> list[dict]:
    import Vision
    from Foundation import NSData
    from PIL import Image

    img = (image if isinstance(image, Image.Image) else Image.open(image)).convert("L")
    w, h = img.size
    buf = io.BytesIO()
    img.save(buf, "PNG")
    data = NSData.dataWithBytes_length_(buf.getvalue(), len(buf.getvalue()))
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setRecognitionLanguages_(list(languages))
    req.setUsesLanguageCorrection_(True)   # «11-bro» → «li-bro»; the hyphenated syllables stay as printed
    handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(data, None)
    ok = handler.performRequests_error_([req], None)
    if isinstance(ok, tuple):
        ok = ok[0]
    out = []
    for r in (req.results() or []):
        cand = r.topCandidates_(1)
        if not cand or not len(cand):
            continue
        text = str(cand[0].string())
        box = r.boundingBox()   # normalized, origin at the bottom left
        x0 = box.origin.x * w
        x1 = (box.origin.x + box.size.width) * w
        y1 = (1 - box.origin.y) * h
        y0 = (1 - box.origin.y - box.size.height) * h
        out.append({"text": text, "x0": x0, "y0": y0, "x1": x1, "y1": y1})
    return out
