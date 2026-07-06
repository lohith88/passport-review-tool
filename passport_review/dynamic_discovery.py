from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from PIL import Image

from .config import ReviewConfig
from .documents import DOCUMENT_EXTENSIONS, IMAGE_EXTENSIONS, REVIEWABLE_EXTENSIONS, normalize_name
from .imaging import analyze_image, iter_source_images
from .models import DocumentBundle, DocumentSource, ImageMetrics, LocalVisualResult, OCRResult
from .ocr import OCREngine, normalize_alphanumeric


class VisualAnalyzer(Protocol):
    def analyze(self, image: Image.Image) -> LocalVisualResult: ...


@dataclass(slots=True)
class CandidateAnalysis:
    source: DocumentSource
    ocr: OCRResult
    metrics: ImageMetrics
    visual: LocalVisualResult | None
    front_score: float = 0.0
    back_score: float = 0.0
    blank_score: float = 0.0
    photo_score: float = 0.0
    signals: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return self.ocr.text or ""

    @property
    def normalized_text(self) -> str:
        return re.sub(r"\s+", " ", self.text.upper()).strip()


@dataclass(slots=True)
class DynamicDiscoveryResult:
    bundle: DocumentBundle
    analyses: list[CandidateAnalysis]
    detected_passport_number: str = ""
    passport_number_confident: bool = False
    notes: list[str] = field(default_factory=list)


_FRONT_TERMS: dict[str, float] = {
    "PASSPORT": 2.0,
    "REPUBLIC OF INDIA": 4.0,
    "SURNAME": 2.0,
    "GIVEN NAME": 2.0,
    "NATIONALITY": 1.0,
    "DATE OF BIRTH": 1.5,
    "PLACE OF BIRTH": 1.5,
    "DATE OF ISSUE": 1.0,
    "DATE OF EXPIRY": 1.5,
    "PLACE OF ISSUE": 1.0,
    "TYPE": 0.5,
    "COUNTRY CODE": 1.0,
}

_BACK_TERMS: dict[str, float] = {
    "ADDRESS": 4.0,
    "FATHER": 2.0,
    "MOTHER": 2.0,
    "SPOUSE": 2.0,
    "LEGAL GUARDIAN": 1.5,
    "OLD PASSPORT": 2.0,
    "PREVIOUS PASSPORT": 2.0,
    "FILE NO": 2.0,
    "FILE NUMBER": 2.0,
    "EMIGRATION": 1.0,
    "PIN": 0.5,
}


def list_person_folders(root: Path, output_root: Path | None = None) -> list[Path]:
    """Return immediate child directories; each directory is one person's submission."""
    root = root.resolve()
    if not root.exists():
        raise FileNotFoundError(f"Passport folders root does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Passport folders root is not a directory: {root}")

    excluded = {".venv", "models", "__pycache__", "renamed-documents", "passports_output"}
    output_resolved = output_root.resolve() if output_root else None
    folders: list[Path] = []
    for child in root.iterdir():
        if not child.is_dir() or child.name.casefold() in excluded or child.name.startswith("."):
            continue
        if output_resolved is not None:
            try:
                if child.resolve() == output_resolved:
                    continue
            except OSError:
                pass
        folders.append(child)
    return sorted(folders, key=lambda path: path.name.casefold())


def _is_excluded_filename(path: Path, config: ReviewConfig) -> bool:
    """True when the file name marks it as a non-passport document (voter ID, China
    visa form, ...) that we must ignore entirely.

    Voter/election IDs are never one of the 4 passport documents, so they are always
    dropped. Visa markers are dropped only when the name has no passport-document word
    - "visa photo" / "china visa photo" is the passport photo (taken for a visa), and
    "visa page(s)" is a blank page, so those are kept.
    """
    normalized = normalize_name(path.stem)
    tokens = set(normalized.split())
    document_words = {"page", "pages", "blank", "photo", "front", "back", "first", "last"}
    has_document_word = bool(tokens & document_words)

    for keyword in config.exclude_filename_keywords:
        normalized_keyword = normalize_name(keyword)
        if not normalized_keyword or normalized_keyword not in normalized:
            continue
        if any(word in normalized_keyword for word in ("voter", "election", "epic")):
            return True
        if not has_document_word:
            return True

    # A standalone "visa" file is a visa document unless it is a passport document.
    if "visa" in tokens and not has_document_word:
        return True
    return False


def _collect_files(folder: Path, config: ReviewConfig) -> tuple[list[Path], list[Path], list[Path]]:
    """Return (reviewable_files, ineligible_files, excluded_files).

    Reviewable = JPG/JPEG/PNG (safe to open and OCR). Ineligible = PDF and other
    document formats (reported and copied as-is, never rendered). Excluded = files
    whose name marks them as non-passport documents (voter ID / China visa / ...),
    which are ignored completely.
    """
    iterator = folder.rglob("*") if config.recursive_file_search else folder.glob("*")
    reviewable: list[Path] = []
    ineligible: list[Path] = []
    excluded: list[Path] = []
    for path in iterator:
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in DOCUMENT_EXTENSIONS:
            continue
        if _is_excluded_filename(path, config):
            excluded.append(path)
        elif suffix in REVIEWABLE_EXTENSIONS or suffix == ".pdf":
            # PDFs are rendered to an image (extracted to JPG on copy) and reviewed.
            reviewable.append(path)
        else:
            ineligible.append(path)
    key = lambda path: str(path.relative_to(folder)).casefold()
    return sorted(reviewable, key=key), sorted(ineligible, key=key), sorted(excluded, key=key)


def _contains_any(text: str, terms: list[str]) -> bool:
    """Match filename words/phrases without accidental substrings.

    For example, the label ``back`` must not match ``background``. Underscores,
    hyphens and repeated spaces are normalized before matching.
    """
    normalized = normalize_name(Path(text).stem)
    padded = f" {normalized} "
    for term in terms:
        normalized_term = normalize_name(term)
        if normalized_term and f" {normalized_term} " in padded:
            return True
    return False


def _filename_document_labels(path: Path, config: ReviewConfig) -> list[str]:
    """Return authoritative document labels present in the filename.

    A single detected label is treated as the source of truth. Multiple labels
    are considered ambiguous and are left for content-based fallback plus a
    manual-review note.
    """
    labels: list[str] = []
    if _contains_any(path.name, config.front_keywords):
        labels.append("front")
    if _contains_any(path.name, config.back_keywords):
        labels.append("back")
    if _contains_any(path.name, config.blank_keywords):
        labels.append("blank")
    if _contains_any(path.name, config.photo_keywords):
        labels.append("photo")
    return labels


def _label_conflicts_with_content(label: str, item: "CandidateAnalysis", config: ReviewConfig) -> bool:
    """Return True when a file name label is contradicted by the page content, e.g. a
    data page whose file name happens to contain 'photo', or a standalone photograph
    whose file name contains a page word. In that case the label is not trusted and
    the file is classified by content (OCR + layout) instead."""
    text = item.normalized_text
    text_chars = len(re.sub(r"\s", "", text))
    compact = text.replace(" ", "")
    looks_like_page = (
        text_chars >= 120
        or "P<IND" in compact
        or any(term in text for term in (
            "SURNAME", "GIVEN NAME", "REPUBLIC OF INDIA", "DATE OF BIRTH",
            "ADDRESS", "FATHER", "MOTHER", "SPOUSE",
        ))
        or (item.metrics.face_count or 0) > 1
    )
    looks_like_photo = (
        (item.metrics.width, item.metrics.height) == (config.exact_photo_width, config.exact_photo_height)
        and text_chars < 20
    )
    if label == "photo" and looks_like_page:
        return True
    if label in {"front", "back", "blank"} and looks_like_photo:
        return True
    return False


def _score_candidate(
    path: Path,
    ocr: OCRResult,
    metrics: ImageMetrics,
    visual: LocalVisualResult | None,
    config: ReviewConfig,
) -> tuple[float, float, float, float, list[str]]:
    text = re.sub(r"\s+", " ", (ocr.text or "").upper()).strip()
    filename = path.name
    text_chars = len(re.sub(r"\s", "", text))
    ratio = metrics.height / max(metrics.width, 1)
    signals: list[str] = []

    front = 0.0
    back = 0.0
    blank = 0.0
    photo = 0.0

    for term, value in _FRONT_TERMS.items():
        if term in text:
            front += value
    for term, value in _BACK_TERMS.items():
        if term in text:
            back += value

    # Machine-readable-zone evidence is the strongest front-page signal.
    compact = text.replace(" ", "")
    if "P<IND" in compact or ("P<" in compact and "IND" in compact):
        front += 8.0
        signals.append("MRZ-like text")
    if text.count("<") >= 8:
        front += 4.0

    if ocr.observed_passport_numbers:
        front += 2.5
        back += 2.0
        blank += 2.5
        signals.append("passport-like number")
    if ocr.page_number:
        blank += 2.0
        signals.append("printed page number")

    if _contains_any(filename, config.photo_keywords):
        photo += 10.0
        signals.append("photo filename")
    if _contains_any(filename, config.front_keywords):
        front += 10.0
        signals.append("front filename")
    if _contains_any(filename, config.back_keywords):
        back += 10.0
        signals.append("back filename")
    if _contains_any(filename, config.blank_keywords):
        blank += 10.0
        signals.append("blank filename")

    if (metrics.width, metrics.height) == (config.exact_photo_width, config.exact_photo_height):
        photo += 14.0
        signals.append("exact photo dimensions")
    if 1.20 <= ratio <= 1.80:
        photo += 2.5
    elif ratio < 0.95:
        front += 0.5
        back += 0.5

    face_count = metrics.face_count
    face_height_ratio = None
    if visual and visual.available and not visual.error:
        face_count = visual.face_count or 0
        face_height_ratio = visual.face_height_ratio
    if face_count == 1:
        photo += 5.0
        if text_chars > 100:
            front += 1.5  # The passport data page normally contains a portrait.
    elif face_count and face_count > 1:
        photo -= 8.0
    else:
        photo -= 2.0
        blank += 0.5

    if face_height_ratio is not None and 0.35 <= face_height_ratio <= 0.90:
        photo += 3.0

    # A standalone photograph should normally have little or no OCR text.
    if text_chars <= 20:
        photo += 4.0
        blank += 2.0
    elif text_chars <= 70:
        photo += 1.0
        blank += 1.0
    elif text_chars >= 180:
        photo -= 6.0
        front += 1.0
        back += 1.0

    if any(term in text for term in ("SURNAME", "GIVEN NAME", "DATE OF BIRTH", "P<IND")):
        photo -= 10.0
        blank -= 5.0
    if any(term in text for term in ("ADDRESS", "FATHER", "MOTHER", "SPOUSE", "FILE NO")):
        blank -= 4.0

    # Blank pages are sparse and should not look like a standalone portrait.
    if text_chars < 120 and face_count == 0:
        blank += 1.5
    if text_chars > 350:
        blank -= 3.0

    return front, back, blank, photo, signals


def _analyze_source(
    path: Path,
    config: ReviewConfig,
    ocr_engine: OCREngine,
    visual_analyzer: VisualAnalyzer | None,
) -> CandidateAnalysis | None:
    source = DocumentSource(path, reason="Dynamic content scan")
    try:
        images = list(iter_source_images(source, config))
    except Exception:
        return None
    if not images:
        return None

    # JPEG/PNG submissions have one image. For a PDF, classification uses the first
    # rendered page while the original source remains available to the review stage.
    image = images[0]
    metrics = analyze_image(image)
    ocr = ocr_engine.recognize(image, "")

    visual: LocalVisualResult | None = None
    ratio = metrics.height / max(metrics.width, 1)
    likely_photo_shape = (
        path.suffix.lower() in IMAGE_EXTENSIONS
        and (
            (metrics.width, metrics.height) == (config.exact_photo_width, config.exact_photo_height)
            or 1.15 <= ratio <= 1.90
            or _contains_any(path.name, config.photo_keywords)
        )
    )
    if visual_analyzer is not None and likely_photo_shape:
        try:
            visual = visual_analyzer.analyze(image)
        except Exception as exc:
            visual = LocalVisualResult(available=False, error=f"Local visual classification failed: {exc}")

    front, back, blank, photo, signals = _score_candidate(path, ocr, metrics, visual, config)
    return CandidateAnalysis(
        source=source,
        ocr=ocr,
        metrics=metrics,
        visual=visual,
        front_score=front,
        back_score=back,
        blank_score=blank,
        photo_score=photo,
        signals=signals,
    )


def _choose_photo(analyses: list[CandidateAnalysis]) -> tuple[CandidateAnalysis | None, list[str]]:
    notes: list[str] = []
    if not analyses:
        return None, notes
    ranked = sorted(analyses, key=lambda item: (item.photo_score, -len(item.text)), reverse=True)
    best = ranked[0]
    if best.photo_score < 6.0:
        notes.append("No photograph candidate reached the automatic classification threshold.")
        return None, notes
    if len(ranked) > 1 and ranked[1].photo_score >= best.photo_score - 1.5 and ranked[1].photo_score >= 6.0:
        notes.append(
            f"Photo classification is ambiguous between {best.source.path.name} and {ranked[1].source.path.name}; "
            "the highest-scoring file was selected."
        )
    return best, notes


def _choose_front(analyses: list[CandidateAnalysis]) -> tuple[CandidateAnalysis | None, list[str]]:
    notes: list[str] = []
    if not analyses:
        return None, notes
    ranked = sorted(
        analyses,
        key=lambda item: (
            item.front_score,
            len(item.ocr.observed_passport_numbers),
            len(item.text),
        ),
        reverse=True,
    )
    best = ranked[0]
    if best.front_score < 3.0:
        notes.append(
            f"Front page was selected by fallback ranking ({best.source.path.name}); its content signals were weak."
        )
    if len(ranked) > 1 and ranked[1].front_score >= best.front_score - 1.0 and best.front_score < 8.0:
        notes.append(
            f"Front-page classification may be ambiguous between {best.source.path.name} and "
            f"{ranked[1].source.path.name}."
        )
    return best, notes


def _choose_back(analyses: list[CandidateAnalysis]) -> tuple[CandidateAnalysis | None, list[str]]:
    notes: list[str] = []
    if not analyses:
        return None, notes
    ranked = sorted(
        analyses,
        key=lambda item: (item.back_score, len(item.text)),
        reverse=True,
    )
    best = ranked[0]
    if best.back_score < 2.0:
        # If there are only two substantial passport pages, the remaining text-rich
        # page is still more likely to be the address/last page than a blank page.
        if len(best.text.replace(" ", "")) < 80 and best.blank_score > best.back_score:
            notes.append("No reliable address/last-page candidate was found.")
            return None, notes
        notes.append(
            f"Address/last page was selected by fallback ranking ({best.source.path.name}); its signals were weak."
        )
    if len(ranked) > 1 and ranked[1].back_score >= best.back_score - 1.0 and best.back_score < 7.0:
        notes.append(
            f"Address/last-page classification may be ambiguous between {best.source.path.name} and "
            f"{ranked[1].source.path.name}."
        )
    return best, notes


def _choose_passport_number(
    analyses: list[CandidateAnalysis],
    front: CandidateAnalysis | None,
    back: CandidateAnalysis | None,
) -> tuple[str, bool, list[str]]:
    notes: list[str] = []
    counts: Counter[str] = Counter()
    weighted: Counter[str] = Counter()

    for item in analyses:
        for raw in item.ocr.observed_passport_numbers:
            number = normalize_alphanumeric(raw)
            if not number:
                continue
            counts[number] += 1
            weighted[number] += 3
            if re.fullmatch(r"[A-Z][0-9]{7}", number):
                weighted[number] += 4
            elif re.fullmatch(r"[A-Z]{1,2}[0-9]{6,8}", number):
                weighted[number] += 1
            if item is front:
                weighted[number] += 7
            if item is back:
                weighted[number] += 3
            if "P<IND" in item.normalized_text.replace(" ", ""):
                weighted[number] += 4

    if not weighted:
        notes.append("No passport-like number could be read from the submitted images.")
        return "", False, notes

    ranked = weighted.most_common()
    chosen, chosen_score = ranked[0]
    confident = True
    if len(ranked) > 1 and ranked[1][1] >= chosen_score - 2:
        confident = False
        notes.append("More than one passport-like number was detected; verify the selected number manually.")
    if counts[chosen] == 1 and (front is None or chosen not in front.ocr.observed_passport_numbers):
        confident = False
        notes.append("The detected passport number appeared only once outside a confident front-page reading.")
    return chosen, confident, notes


def discover_documents_dynamic(
    folder: Path,
    config: ReviewConfig,
    ocr_engine: OCREngine,
    visual_analyzer: VisualAnalyzer | None,
) -> DynamicDiscoveryResult:
    bundle = DocumentBundle(folder=folder)
    files, ineligible, excluded = _collect_files(folder, config)
    bundle.ineligible = ineligible
    notes: list[str] = []
    analyses: list[CandidateAnalysis] = []

    for path in files:
        analysis = _analyze_source(path, config, ocr_engine, visual_analyzer)
        if analysis is None:
            bundle.unclassified.append(path)
            notes.append(f"Could not open or classify {path.name}.")
        else:
            analyses.append(analysis)

    # Content-based exclusion: drop files whose OCR content identifies them as a
    # non-passport document (voter ID / visa), even when the file name did not.
    if config.exclude_content_terms and analyses:
        kept: list[CandidateAnalysis] = []
        for item in analyses:
            text = item.normalized_text
            if any(term.upper() in text for term in config.exclude_content_terms):
                excluded.append(item.source.path)
            else:
                kept.append(item)
        analyses = kept

    bundle.excluded = list(excluded)
    if excluded:
        notes.append(
            f"Ignored {len(excluded)} non-passport file(s) (voter ID / China visa form / etc.); not reviewed or copied."
        )

    if not analyses:
        if ineligible:
            notes.append(
                f"No JPG/JPEG/PNG files to review; {len(ineligible)} non-eligible file(s) present (e.g. PDF)."
            )
        else:
            notes.append("No supported image files were found in this person folder.")
        bundle.notes.extend(notes)
        return DynamicDiscoveryResult(bundle=bundle, analyses=[], notes=notes)

    # Filename labels are authoritative. Content scoring is used only for files
    # that have no usable filename label, or for an ambiguous filename that
    # contains more than one document-type word.
    explicitly_labelled: dict[str, list[CandidateAnalysis]] = {
        "front": [],
        "back": [],
        "blank": [],
        "photo": [],
    }
    fallback_pool: list[CandidateAnalysis] = []

    for item in analyses:
        labels = _filename_document_labels(item.source.path, config)
        conflicting = [label for label in labels if _label_conflicts_with_content(label, item, config)]
        if len(labels) == 1 and not conflicting:
            label = labels[0]
            explicitly_labelled[label].append(item)
            item.signals.append(f"authoritative filename label: {label}")
            item.source.reason = f"Filename contains '{label}'"
            notes.append(f"Filename label used: {item.source.path.name} -> {label}.")
        elif conflicting:
            # The file name says one thing but the page content says another
            # (e.g. a data page named "...photo..."). Trust the content.
            fallback_pool.append(item)
            item.source.reason = "Filename label overridden by page content"
            notes.append(
                f"Filename label {conflicting} on {item.source.path.name} conflicts with the page content; "
                "classified by content (OCR/layout) instead."
            )
        elif len(labels) > 1:
            fallback_pool.append(item)
            notes.append(
                f"Filename {item.source.path.name} contains multiple document labels "
                f"({', '.join(labels)}); content-based fallback was used and manual confirmation is required."
            )
        else:
            fallback_pool.append(item)

    photo_items = list(explicitly_labelled["photo"])
    front_items = list(explicitly_labelled["front"])
    back_items = list(explicitly_labelled["back"])
    blank_items = list(explicitly_labelled["blank"])

    remaining = list(fallback_pool)

    if not photo_items:
        photo, selection_notes = _choose_photo(remaining)
        notes.extend(selection_notes)
        if photo is not None:
            photo.source.reason = f"Content fallback photo score {photo.photo_score:.1f}"
            photo_items.append(photo)
            remaining = [item for item in remaining if item is not photo]

    if not front_items:
        front, selection_notes = _choose_front(remaining)
        notes.extend(selection_notes)
        if front is not None:
            front.source.reason = f"Content fallback front score {front.front_score:.1f}"
            front_items.append(front)
            remaining = [item for item in remaining if item is not front]

    if not back_items:
        back, selection_notes = _choose_back(remaining)
        notes.extend(selection_notes)
        if back is not None:
            back.source.reason = f"Content fallback back score {back.back_score:.1f}"
            back_items.append(back)
            remaining = [item for item in remaining if item is not back]

    # Any still-unlabelled passport images are treated as additional blank/visa
    # pages, preserving the previous dynamic behaviour for imperfect submissions.
    for item in remaining:
        item.source.reason = f"Remaining passport page; blank score {item.blank_score:.1f}"
        blank_items.append(item)

    bundle.photo.extend(item.source for item in photo_items)
    bundle.front.extend(item.source for item in front_items)
    bundle.back.extend(item.source for item in back_items)
    bundle.blank.extend(
        item.source for item in sorted(blank_items, key=lambda value: value.source.path.name.casefold())
    )

    # Use the strongest explicitly/fallback-selected front and back candidates
    # when weighting the detected passport number. Multiple filename-labelled
    # candidates remain in the bundle so the review stage can flag them.
    front_for_number = max(front_items, key=lambda item: item.front_score, default=None)
    back_for_number = max(back_items, key=lambda item: item.back_score, default=None)
    photo_set = {id(item) for item in photo_items}
    passport_analyses = [item for item in analyses if id(item) not in photo_set]
    number, confident, number_notes = _choose_passport_number(
        passport_analyses, front_for_number, back_for_number
    )
    notes.extend(number_notes)

    if not bundle.front:
        notes.append("Passport front page was not identified.")
    if not bundle.back:
        notes.append("Passport address/last page was not identified.")
    if not bundle.photo:
        notes.append("Standalone photograph was not identified.")

    if len(bundle.front) > 1:
        notes.append("More than one filename/content candidate was classified as front; verify manually.")
    if len(bundle.back) > 1:
        notes.append("More than one filename/content candidate was classified as back; verify manually.")
    if len(bundle.photo) > 1:
        notes.append("More than one filename/content candidate was classified as photo; verify manually.")

    # Add compact classification evidence to the report without exposing OCR text.
    for item in analyses:
        notes.append(
            f"Classified {item.source.path.name}: front={item.front_score:.1f}, "
            f"back={item.back_score:.1f}, blank={item.blank_score:.1f}, photo={item.photo_score:.1f}."
        )

    bundle.notes.extend(notes)
    return DynamicDiscoveryResult(
        bundle=bundle,
        analyses=analyses,
        detected_passport_number=number,
        passport_number_confident=confident,
        notes=notes,
    )

