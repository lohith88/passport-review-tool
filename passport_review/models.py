from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Status(str, Enum):
    OK = "ok"
    ERROR = "Error"
    NOT_LEGIBLE = "Not legible"
    MANUAL_REVIEW = "Manual review"
    MISSING = "Missing"
    NOT_APPLICABLE = "Not applicable"


@dataclass(slots=True)
class ManifestRow:
    row_number: int
    booking_id: str
    tsf_id: str
    gender: str
    name: str
    expected_passport_no: str
    group: str
    assigned_to: str
    folder_name: str
    front_output_name: str
    back_output_name: str
    blank_output_name: str
    photo_output_name: str
    original: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class DocumentSource:
    path: Path
    page_indexes: tuple[int, ...] | None = None
    reason: str = ""

    @property
    def is_pdf(self) -> bool:
        return self.path.suffix.lower() == ".pdf"

    def display_name(self) -> str:
        if self.page_indexes is None:
            return self.path.name
        pages = ",".join(str(i + 1) for i in self.page_indexes)
        return f"{self.path.name} [pages {pages}]"


@dataclass(slots=True)
class DocumentBundle:
    folder: Path
    front: list[DocumentSource] = field(default_factory=list)
    back: list[DocumentSource] = field(default_factory=list)
    blank: list[DocumentSource] = field(default_factory=list)
    photo: list[DocumentSource] = field(default_factory=list)
    unclassified: list[Path] = field(default_factory=list)
    ineligible: list[Path] = field(default_factory=list)  # non-JPG/PNG/PDF: copied as-is
    excluded: list[Path] = field(default_factory=list)  # voter ID / visa / non-passport: ignored
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ImageMetrics:
    width: int
    height: int
    blur_score: float
    brightness: float
    contrast: float
    white_border_ratio: float
    face_count: int
    eye_count: int


@dataclass(slots=True)
class OCRResult:
    text: str = ""
    confidence: float = 0.0
    expected_number_found: bool = False
    observed_passport_numbers: list[str] = field(default_factory=list)
    page_number: str | None = None
    engine: str = ""
    error: str | None = None


@dataclass(slots=True)
class LocalVisualResult:
    available: bool = False
    face_count: int | None = None
    hand_count: int | None = None
    face_center_offset_x: float | None = None
    face_center_offset_y: float | None = None
    face_width_ratio: float | None = None
    face_height_ratio: float | None = None
    eye_tilt_degrees: float | None = None
    error: str | None = None


@dataclass(slots=True)
class CheckResult:
    status: Status
    comments: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def add(self, message: str) -> None:
        message = message.strip()
        if message and message not in self.comments:
            self.comments.append(message)


@dataclass(slots=True)
class PersonReview:
    manifest: ManifestRow
    folder_match_status: Status
    matched_folder: Path | None
    front: CheckResult
    back: CheckResult
    blank: CheckResult
    photo: CheckResult
    overall: Status
    detected_files: list[str] = field(default_factory=list)
    output_files: list[str] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)
    detected_passport_number: str = ""
    passport_number_confident: bool = False
    renamed_folder: Path | None = None
    rename_log: list[tuple[str, str]] = field(default_factory=list)
    bundle: "DocumentBundle | None" = None

    def all_comments(self) -> str:
        chunks: list[str] = []
        for prefix, result in (
            ("Front", self.front),
            ("Back", self.back),
            ("Blank pages", self.blank),
            ("Photo", self.photo),
        ):
            if result.comments:
                chunks.append(f"{prefix}: " + "; ".join(result.comments))
        chunks.extend(self.comments)
        return " | ".join(chunks)
