from __future__ import annotations

import re


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}
DOCUMENT_EXTENSIONS = IMAGE_EXTENSIONS | {".pdf"}

# Only these formats are opened, OCR'd and reviewed. Everything else (PDF, WEBP,
# TIFF, BMP, ...) is reported as "not eligible" and copied as-is, never rendered
# (rendering some PDFs can crash the native libraries).
REVIEWABLE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
JPEG_EXTENSIONS = {".jpg", ".jpeg"}


def normalize_name(value: str) -> str:
    # Split camelCase ("PassportBack" -> "Passport Back") and letter/digit
    # boundaries ("Passport2" -> "Passport 2") so document-type words are matched
    # as whole words even when the source file name concatenates them.
    value = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value)
    value = re.sub(r"(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])", " ", value)
    value = value.casefold().replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", value).strip()
