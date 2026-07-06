from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ReviewConfig:
    exact_photo_width: int = 390
    exact_photo_height: int = 567
    required_photo_dpi: int = 300
    minimum_blur_score: float = 70.0
    minimum_contrast: float = 22.0
    minimum_white_border_ratio: float = 0.70
    minimum_ocr_confidence: float = 42.0
    folder_fuzzy_cutoff: float = 0.86
    image_render_dpi: int = 220
    recursive_file_search: bool = True

    ocr_engine: str = "auto"
    tesseract_cmd: str = ""
    paddle_ocr_version: str = "PP-OCRv5"
    paddle_detection_model_name: str = "PP-OCRv5_mobile_det"
    paddle_recognition_model_name: str = "PP-OCRv5_mobile_rec"

    model_directory: str = "models"
    face_landmarker_model: str = "face_landmarker.task"
    hand_landmarker_model: str = "hand_landmarker.task"
    minimum_face_detection_confidence: float = 0.55
    minimum_hand_detection_confidence: float = 0.55
    # MediaPipe's native models can crash on very large images; cap the longest side.
    max_vision_image_side: int = 1600
    maximum_face_center_offset_ratio: float = 0.12
    minimum_face_height_ratio: float = 0.42
    maximum_face_height_ratio: float = 0.86
    maximum_eye_tilt_degrees: float = 8.0
    near_duplicate_hash_distance: int = 1

    manual_subjective_photo_checks: bool = True
    manual_object_check_when_no_hand_detected: bool = True

    # Every submitted document/photo should be a JPG/JPEG. PNG is not eligible but is
    # converted to JPG when copied to the output. PDF and any other format are not
    # eligible either and are copied as-is (never rendered). All are noted in comments.
    jpeg_extensions: list[str] = field(default_factory=lambda: [".jpg", ".jpeg"])
    convert_png_to_jpeg: bool = True

    # Files that are not part of the 4 documents we review (voter ID, China visa
    # form, ...). Matched by file name or by OCR content, and completely ignored:
    # never classified, renamed, or copied to the output.
    exclude_filename_keywords: list[str] = field(default_factory=lambda: [
        "voter id", "voterid", "voter", "epic",
        "election id", "election card", "election commission", "election",
        "china visa form", "china visa", "chinese visa", "visa china",
        "visa form", "visa application", "visa copy",
    ])
    exclude_content_terms: list[str] = field(default_factory=lambda: [
        "ELECTION COMMISSION", "ELECTORAL", "EPIC NO", "ELECTORS PHOTO",
        "VISA APPLICATION FORM", "APPLICATION FOR CHINESE VISA", "CHINESE VISA", "VISA APPLICATION",
    ])
    # Passport numbers are masked in reports/comments unless this is disabled
    # (the spreadsheet flow shows full numbers because the workbook stays local).
    mask_passport_numbers: bool = True

    # Filename labels are authoritative when the standalone words front, back,
    # blank or photo occur in the filename. Longer phrases remain available for
    # compatibility with older naming conventions and content-scoring fallback.
    front_keywords: list[str] = field(default_factory=lambda: [
        "front", "passport front", "front page", "first page", "biodata", "bio data", "data page", "passport_front"
    ])
    back_keywords: list[str] = field(default_factory=lambda: [
        "back", "passport back", "passport last", "last page", "address page", "back page", "passport_back"
    ])
    blank_keywords: list[str] = field(default_factory=lambda: [
        "blank", "blank page", "blank pages", "black page", "visa pages", "empty pages", "passport blank", "passport_blank"
    ])
    photo_keywords: list[str] = field(default_factory=lambda: [
        "photo", "photograph", "passport photo", "passport size", "passport_photo", "profile pic"
    ])
    _base_dir: Path = field(default_factory=lambda: Path.cwd(), repr=False)

    @classmethod
    def from_json(cls, path: Path | None) -> "ReviewConfig":
        config = cls()
        if path is None:
            return config
        path = path.resolve()
        data = json.loads(path.read_text(encoding="utf-8"))
        for key, value in data.items():
            if key.startswith("_") or not hasattr(config, key):
                raise ValueError(f"Unknown configuration field: {key}")
            setattr(config, key, value)
        config._base_dir = path.parent
        return config

    def resolve_model_path(self, filename: str) -> Path:
        model_dir = Path(self.model_directory)
        if not model_dir.is_absolute():
            model_dir = self._base_dir / model_dir
        path = Path(filename)
        return path if path.is_absolute() else model_dir / path
