"""Turn the input (PDF, image, or folder of images) into one PNG per page at the target DPI."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


def _pdf_to_pngs(pdf: Path, out_dir: Path, dpi: int) -> list[Path]:
    import pypdfium2 as pdfium

    pages = []
    doc = pdfium.PdfDocument(str(pdf))
    try:
        for i in range(len(doc)):
            img = doc[i].render(scale=dpi / 72).to_pil().convert("L")
            p = out_dir / f"page_{i + 1:03d}.png"
            img.save(p, dpi=(dpi, dpi))
            pages.append(p)
    finally:
        doc.close()
    return pages


def _image_to_png(src: Path, dest: Path, dpi: int) -> Path:
    img = Image.open(src)
    img = ImageOps.exif_transpose(img).convert("L")  # phone photos carry rotation in EXIF
    img.info.pop("icc_profile", None)  # an RGB colour profile on a gray PNG makes libpng complain
    img.save(dest, dpi=(dpi, dpi))
    return dest


def extract_pages(source: Path, out_dir: Path, dpi: int = 300) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        imgs = sorted(p for p in source.iterdir() if p.suffix.lower() in IMAGE_EXTS)
        if not imgs:
            raise ValueError(f"La carpeta {source} no contiene imágenes.")
        return [_image_to_png(p, out_dir / f"page_{i + 1:03d}.png", dpi) for i, p in enumerate(imgs)]
    ext = source.suffix.lower()
    if ext == ".pdf":
        return _pdf_to_pngs(source, out_dir, dpi)
    if ext in IMAGE_EXTS:
        return [_image_to_png(source, out_dir / "page_001.png", dpi)]
    raise ValueError(f"Formato no soportado: {source.name} (usa PDF o imagen)")
