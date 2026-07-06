from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from .models import PersonReview, Status
from .ocr import mask_identifier


RESULT_COLUMNS = [
    "Person Folder",
    "Detected Passport Number (Masked)",
    "Passport Number Confidence",
    "Passport Front File(s)",
    "Passport Last Page File(s)",
    "Passport Blank Page File(s)",
    "Photo File(s)",
    "Passport Front Review",
    "Passport Last Page Review",
    "Passport Blank Pages Review",
    "Photo Dimension (390 x 567)",
    "Photo Full Review",
    "Overall Review",
    "Review Comments",
    "Renamed Output Files",
    "Technical Details",
]


def _photo_dimension_status(review: PersonReview) -> str:
    width = review.photo.details.get("width")
    height = review.photo.details.get("height")
    if width is None or height is None:
        return Status.MISSING.value if review.photo.status == Status.MISSING else Status.MANUAL_REVIEW.value
    return Status.OK.value if (width, height) == (390, 567) else Status.ERROR.value


def _source_names(review: PersonReview, kind: str) -> str:
    details = getattr(review, kind).details
    names: list[str] = []
    direct_source = details.get("source")
    if direct_source:
        names.append(str(direct_source))
    pages = details.get("pages", [])
    for page in pages if isinstance(pages, list) else []:
        source = page.get("source") if isinstance(page, dict) else None
        if source and source not in names:
            names.append(str(source))
    return " | ".join(names)


def result_row(review: PersonReview) -> dict:
    details = {
        "front": review.front.details,
        "back": review.back.details,
        "blank": review.blank.details,
        "photo": review.photo.details,
    }
    return {
        "Person Folder": review.manifest.folder_name,
        "Detected Passport Number (Masked)": (
            mask_identifier(review.detected_passport_number) if review.detected_passport_number else ""
        ),
        "Passport Number Confidence": "confident" if review.passport_number_confident else "manual confirmation",
        "Passport Front File(s)": _source_names(review, "front"),
        "Passport Last Page File(s)": _source_names(review, "back"),
        "Passport Blank Page File(s)": _source_names(review, "blank"),
        "Photo File(s)": _source_names(review, "photo"),
        "Passport Front Review": review.front.status.value,
        "Passport Last Page Review": review.back.status.value,
        "Passport Blank Pages Review": review.blank.status.value,
        "Photo Dimension (390 x 567)": _photo_dimension_status(review),
        "Photo Full Review": review.photo.status.value,
        "Overall Review": review.overall.value,
        "Review Comments": review.all_comments(),
        "Renamed Output Files": " | ".join(review.output_files),
        "Technical Details": json.dumps(details, ensure_ascii=False, default=str),
    }


def append_result_row(path: Path, review: PersonReview) -> None:
    """Append one review to the results CSV (writing the header if new)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_COLUMNS)
        if is_new:
            writer.writeheader()
        writer.writerow(result_row(review))


def write_results(path: Path, reviews: list[PersonReview]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_COLUMNS)
        writer.writeheader()
        for review in reviews:
            writer.writerow(result_row(review))


def write_manual_queue(path: Path, reviews: list[PersonReview]) -> None:
    headers = [
        "Person Folder",
        "Detected Passport Number (Masked)",
        "Overall Review",
        "Front",
        "Back",
        "Blank Pages",
        "Photo",
        "Review Comments",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for review in reviews:
            if review.overall == Status.OK:
                continue
            writer.writerow({
                "Person Folder": review.manifest.folder_name,
                "Detected Passport Number (Masked)": (
                    mask_identifier(review.detected_passport_number) if review.detected_passport_number else ""
                ),
                "Overall Review": review.overall.value,
                "Front": review.front.status.value,
                "Back": review.back.status.value,
                "Blank Pages": review.blank.status.value,
                "Photo": review.photo.status.value,
                "Review Comments": review.all_comments(),
            })


def write_summary(path: Path, reviews: list[PersonReview], ocr_engine_name: str, offline_strict: bool) -> None:
    counts = Counter(review.overall.value for review in reviews)
    with path.open("w", encoding="utf-8") as handle:
        handle.write("Passport Review Summary\n")
        handle.write("=======================\n\n")
        handle.write(f"Total person folders: {len(reviews)}\n")
        handle.write("Input mode: dynamic folder scan; no manifest/spreadsheet metadata used\n")
        handle.write(f"OCR engine: {ocr_engine_name}\n")
        handle.write(f"Strict offline network block: {'enabled' if offline_strict else 'disabled'}\n")
        for status, count in sorted(counts.items()):
            handle.write(f"{status}: {count}\n")
        handle.write("\nManual-review folders are also written to manual_review_queue.csv.\n")
        handle.write("Full passport numbers are not written to reports; only masked values are shown.\n")
        handle.write("Files are copied/renamed regardless of review status when --copy-renamed is used.\n")
