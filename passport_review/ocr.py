from __future__ import annotations

import json
import re
from dataclasses import dataclass
from statistics import mean
from typing import Protocol

import cv2
import numpy as np
from PIL import Image

from .config import ReviewConfig
from .models import OCRResult


PASSPORT_PATTERN = re.compile(r"\b[A-Z]{1,2}[0-9]{6,8}\b")
PAGE_PATTERNS = [
    re.compile(r"\bPAGE\s*[:#-]?\s*([0-9]{1,3})\b", re.IGNORECASE),
    re.compile(r"\bP\.?\s*([0-9]{1,3})\b", re.IGNORECASE),
]


class OCREngine(Protocol):
    name: str

    def recognize(self, image: Image.Image, expected_passport_no: str) -> OCRResult: ...


@dataclass(slots=True)
class _OCRAttempt:
    text: str
    confidence: float


def normalize_alphanumeric(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def mask_identifier(value: str) -> str:
    normalized = normalize_alphanumeric(value)
    if len(normalized) <= 4:
        return "*" * len(normalized)
    return normalized[:1] + "*" * (len(normalized) - 3) + normalized[-2:]


def _preprocess_variants(image: Image.Image) -> list[np.ndarray]:
    rgb = np.asarray(image.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if min(gray.shape[:2]) < 1400:
        scale = min(2.2, 1400 / max(min(gray.shape[:2]), 1))
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    denoised = cv2.bilateralFilter(gray, 7, 55, 55)
    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8)).apply(denoised)
    thresholded = cv2.adaptiveThreshold(
        clahe,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        41,
        13,
    )
    return [gray, clahe, thresholded]


def _extract_page_number(text: str) -> str | None:
    for pattern in PAGE_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def _build_result(attempts: list[_OCRAttempt], expected_passport_no: str, engine: str) -> OCRResult:
    if not attempts:
        return OCRResult(engine=engine, error=f"{engine} produced no OCR output.")
    normalized_expected = normalize_alphanumeric(expected_passport_no)
    matching = [
        attempt for attempt in attempts
        if normalized_expected and normalized_expected in normalize_alphanumeric(attempt.text)
    ]
    best = max(matching or attempts, key=lambda attempt: attempt.confidence)
    combined_text = "\n".join(attempt.text for attempt in attempts if attempt.text)
    normalized_combined = normalize_alphanumeric(combined_text)
    observed = sorted({normalize_alphanumeric(match) for match in PASSPORT_PATTERN.findall(combined_text.upper())})
    page_number = None
    for attempt in sorted(attempts, key=lambda item: item.confidence, reverse=True):
        page_number = _extract_page_number(attempt.text)
        if page_number:
            break
    return OCRResult(
        text=best.text,
        confidence=float(best.confidence),
        expected_number_found=bool(normalized_expected and normalized_expected in normalized_combined),
        observed_passport_numbers=observed,
        page_number=page_number,
        engine=engine,
    )


class TesseractOCREngine:
    name = "tesseract"

    def __init__(self, tesseract_cmd: str = "") -> None:
        import pytesseract

        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        try:
            pytesseract.get_tesseract_version()
        except Exception as exc:
            raise RuntimeError(f"Tesseract executable is unavailable: {exc}") from exc

    @staticmethod
    def _run_attempt(processed: np.ndarray, psm: int) -> _OCRAttempt:
        import pytesseract
        from pytesseract import Output

        data = pytesseract.image_to_data(processed, output_type=Output.DICT, config=f"--oem 3 --psm {psm}")
        text = " ".join(token for token in data.get("text", []) if token and token.strip())
        confidence_values: list[float] = []
        for raw in data.get("conf", []):
            try:
                value = float(raw)
                if value >= 0:
                    confidence_values.append(value)
            except (TypeError, ValueError):
                continue
        return _OCRAttempt(text=text, confidence=float(mean(confidence_values) if confidence_values else 0.0))

    def recognize(self, image: Image.Image, expected_passport_no: str) -> OCRResult:
        normalized_expected = normalize_alphanumeric(expected_passport_no)
        attempts: list[_OCRAttempt] = []
        try:
            for variant in _preprocess_variants(image):
                for psm in (6, 11):
                    attempt = self._run_attempt(variant, psm)
                    attempts.append(attempt)
                    if normalized_expected and normalized_expected in normalize_alphanumeric(attempt.text):
                        break
                if attempts and normalized_expected in normalize_alphanumeric(attempts[-1].text):
                    break
        except Exception as exc:
            return OCRResult(engine=self.name, error=f"Tesseract OCR failed: {exc}")
        return _build_result(attempts, expected_passport_no, self.name)


class PaddleOCREngine:
    name = "paddleocr"

    def __init__(self, config: ReviewConfig) -> None:
        from paddleocr import PaddleOCR

        kwargs = {
            "lang": "en",
            "device": "cpu",
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
            "ocr_version": config.paddle_ocr_version,
            "text_detection_model_name": config.paddle_detection_model_name,
            "text_recognition_model_name": config.paddle_recognition_model_name,
        }
        self.pipeline = PaddleOCR(**kwargs)

    @staticmethod
    def _payload_from_result(result: object) -> dict:
        payload = getattr(result, "json", None)
        if callable(payload):
            payload = payload()
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            return {}
        return payload.get("res", payload)

    def recognize(self, image: Image.Image, expected_passport_no: str) -> OCRResult:
        attempts: list[_OCRAttempt] = []
        try:
            rgb = np.ascontiguousarray(np.asarray(image.convert("RGB")))
            results = self.pipeline.predict(rgb)
            for result in results:
                payload = self._payload_from_result(result)
                texts = payload.get("rec_texts")
                scores = payload.get("rec_scores")
                if texts is None:
                    texts = []
                if scores is None:
                    scores = []
                score_values = [float(value) * 100.0 for value in list(scores)]
                confidence = float(mean(score_values) if score_values else 0.0)
                attempts.append(_OCRAttempt(text="\n".join(str(text) for text in texts), confidence=confidence))
        except Exception as exc:
            return OCRResult(engine=self.name, error=f"PaddleOCR failed: {exc}")
        return _build_result(attempts, expected_passport_no, self.name)


class FallbackOCREngine:
    def __init__(self, primary: OCREngine, fallback: OCREngine) -> None:
        self.primary = primary
        self.fallback = fallback
        self.name = f"{primary.name}+{fallback.name}"

    def recognize(self, image: Image.Image, expected_passport_no: str) -> OCRResult:
        first = self.primary.recognize(image, expected_passport_no)
        if first.expected_number_found:
            return first
        second = self.fallback.recognize(image, expected_passport_no)
        if second.expected_number_found:
            return second
        if first.error and not second.error:
            return second
        if second.error and not first.error:
            return first
        return first if first.confidence >= second.confidence else second


def create_ocr_engine(config: ReviewConfig, override: str | None = None) -> tuple[OCREngine, list[str]]:
    requested = (override or config.ocr_engine or "auto").strip().lower()
    warnings: list[str] = []

    tesseract: OCREngine | None = None
    paddle: OCREngine | None = None

    if requested in {"auto", "tesseract"}:
        try:
            tesseract = TesseractOCREngine(config.tesseract_cmd)
        except Exception as exc:
            warnings.append(str(exc))
            if requested == "tesseract":
                raise

    if requested in {"auto", "paddle"}:
        try:
            paddle = PaddleOCREngine(config)
        except Exception as exc:
            warnings.append(f"PaddleOCR unavailable: {exc}")
            if requested == "paddle":
                raise

    if requested == "paddle" and paddle:
        return paddle, warnings
    if requested == "tesseract" and tesseract:
        return tesseract, warnings
    if requested == "auto":
        if paddle and tesseract:
            return FallbackOCREngine(paddle, tesseract), warnings
        if paddle:
            return paddle, warnings
        if tesseract:
            return tesseract, warnings
    raise RuntimeError("No local OCR engine is available. Install Tesseract or PaddleOCR.")

class MemoizingOCREngine:
    """Cache local OCR by image content so dynamic classification and review do not OCR twice."""

    def __init__(self, wrapped: OCREngine) -> None:
        import hashlib

        self.wrapped = wrapped
        self.name = wrapped.name
        self._hashlib = hashlib
        self._cache: dict[str, OCRResult] = {}

    def _key(self, image: Image.Image) -> str:
        rgb = image.convert("RGB")
        digest = self._hashlib.sha256()
        digest.update(str(rgb.size).encode("ascii"))
        digest.update(rgb.tobytes())
        return digest.hexdigest()

    def recognize(self, image: Image.Image, expected_passport_no: str) -> OCRResult:
        key = self._key(image)
        base = self._cache.get(key)
        if base is None:
            base = self.wrapped.recognize(image, "")
            self._cache[key] = base

        expected = normalize_alphanumeric(expected_passport_no)
        observed = [normalize_alphanumeric(value) for value in base.observed_passport_numbers]
        found = bool(expected and (expected in observed or expected in normalize_alphanumeric(base.text)))
        return OCRResult(
            text=base.text,
            confidence=base.confidence,
            expected_number_found=found,
            observed_passport_numbers=list(base.observed_passport_numbers),
            page_number=base.page_number,
            engine=base.engine,
            error=base.error,
        )
