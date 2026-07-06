from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np
from PIL import Image, ImageOps

from .config import ReviewConfig
from .models import DocumentSource, ImageMetrics


_FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
_EYE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")


def load_pil_image(path: Path) -> Image.Image:
    with Image.open(path) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def read_image_dpi(path: Path) -> tuple[float, float] | None:
    """Return the (x, y) DPI stored in an image's metadata, or None if absent."""
    try:
        with Image.open(path) as image:
            dpi = image.info.get("dpi")
    except Exception:
        return None
    if not dpi:
        return None
    try:
        x, y = float(dpi[0]), float(dpi[1])
    except (TypeError, ValueError, IndexError):
        return None
    if x <= 0 or y <= 0:
        return None
    return x, y


def render_pdf_pages(path: Path, page_indexes: tuple[int, ...] | None, dpi: int) -> list[Image.Image]:
    import pypdfium2 as pdfium

    scale = dpi / 72.0
    images: list[Image.Image] = []
    document = pdfium.PdfDocument(str(path))
    try:
        indexes = page_indexes if page_indexes is not None else tuple(range(len(document)))
        for index in indexes:
            if index < 0 or index >= len(document):
                continue
            page = document[index]
            try:
                bitmap = page.render(scale=scale)
                images.append(bitmap.to_pil().convert("RGB"))
            finally:
                page.close()
    finally:
        document.close()
    return images


def iter_source_images(source: DocumentSource, config: ReviewConfig) -> Iterator[Image.Image]:
    if source.is_pdf:
        yield from render_pdf_pages(source.path, source.page_indexes, config.image_render_dpi)
    else:
        yield load_pil_image(source.path)


def _white_border_ratio(rgb: np.ndarray) -> float:
    """Fraction of near-white pixels along the top and side borders. The bottom edge
    is excluded on purpose: in a head-and-shoulders passport photo the bottom border
    is the subject's shoulders/clothing, not the background, so including it would
    understate a perfectly white background."""
    height, width = rgb.shape[:2]
    border = max(2, int(min(height, width) * 0.08))
    mask = np.zeros((height, width), dtype=bool)
    mask[:border, :] = True        # top
    mask[:, :border] = True        # left
    mask[:, -border:] = True       # right
    border_pixels = rgb[mask]
    white = np.all(border_pixels >= 235, axis=1)
    return float(white.mean()) if len(white) else 0.0


def analyze_image(image: Image.Image) -> ImageMetrics:
    rgb = np.asarray(image.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    contrast = float(gray.std())

    min_side = min(gray.shape[:2])
    detection_gray = gray
    if min_side > 900:
        scale = 900 / min_side
        detection_gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    faces = _FACE_CASCADE.detectMultiScale(
        detection_gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(40, 40),
    )
    eye_count = 0
    for x, y, width, height in faces:
        region = detection_gray[y : y + height, x : x + width]
        eyes = _EYE_CASCADE.detectMultiScale(region, scaleFactor=1.1, minNeighbors=6, minSize=(12, 12))
        eye_count = max(eye_count, len(eyes))

    return ImageMetrics(
        width=image.width,
        height=image.height,
        blur_score=blur_score,
        brightness=brightness,
        contrast=contrast,
        white_border_ratio=_white_border_ratio(rgb),
        face_count=len(faces),
        eye_count=eye_count,
    )


def difference_hash(image: Image.Image, hash_size: int = 8) -> int:
    gray = image.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
    pixels = np.asarray(gray)
    comparison = pixels[:, 1:] > pixels[:, :-1]
    value = 0
    for bit in comparison.flatten():
        value = (value << 1) | int(bit)
    return value


def hash_distance(first: int, second: int) -> int:
    return (first ^ second).bit_count()


def safe_target_path(directory: Path, base_name: str, suffix: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    sanitized = "".join(character for character in base_name if character not in '<>:"/\\|?*').strip().rstrip(".")
    if not sanitized:
        sanitized = "document"
    candidate = directory / f"{sanitized}{suffix.lower()}"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{sanitized}_{counter}{suffix.lower()}"
        counter += 1
    return candidate


def export_document_sources(
    sources: list[DocumentSource],
    output_directory: Path,
    output_base_name: str,
    config: ReviewConfig,
    prefer_pdf_for_multiple: bool = True,
) -> list[Path]:
    if not sources:
        return []
    if len(sources) == 1 and not sources[0].is_pdf and sources[0].page_indexes is None:
        suffix = sources[0].path.suffix.lower()
        if suffix != ".png" or not config.convert_png_to_jpeg:
            # JPG/JPEG (or conversion disabled): copy as-is, preserving the extension.
            target = safe_target_path(output_directory, output_base_name, sources[0].path.suffix)
            shutil.copy2(sources[0].path, target)
            return [target]
        # PNG -> JPG on copy, preserving DPI if present.
        target = safe_target_path(output_directory, output_base_name, ".jpg")
        with Image.open(sources[0].path) as opened:
            dpi = opened.info.get("dpi")
        image = load_pil_image(sources[0].path)
        save_kwargs = {"format": "JPEG", "quality": 95}
        if dpi:
            save_kwargs["dpi"] = dpi
        image.save(target, **save_kwargs)
        return [target]
    if len(sources) == 1 and sources[0].is_pdf and sources[0].page_indexes is None:
        # Extract the PDF page(s) to JPG rather than copying the PDF.
        images = list(iter_source_images(sources[0], config))
        if not images:
            return []
        if len(images) == 1:
            target = safe_target_path(output_directory, output_base_name, ".jpg")
            images[0].convert("RGB").save(target, format="JPEG", quality=95)
            return [target]
        outputs: list[Path] = []
        for index, image in enumerate(images, start=1):
            target = safe_target_path(output_directory, f"{output_base_name}_{index:02d}", ".jpg")
            image.convert("RGB").save(target, format="JPEG", quality=95)
            outputs.append(target)
        return outputs

    images: list[Image.Image] = []
    for source in sources:
        images.extend(list(iter_source_images(source, config)))
    if not images:
        return []
    if len(images) == 1 and not prefer_pdf_for_multiple:
        target = safe_target_path(output_directory, output_base_name, ".jpg")
        images[0].convert("RGB").save(target, format="JPEG", quality=95)
        return [target]
    target = safe_target_path(output_directory, output_base_name, ".pdf")
    rgb_images = [image.convert("RGB") for image in images]
    rgb_images[0].save(target, save_all=True, append_images=rgb_images[1:], resolution=config.image_render_dpi)
    return [target]
