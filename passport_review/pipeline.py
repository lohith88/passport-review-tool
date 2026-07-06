from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol

from PIL import Image

from .config import ReviewConfig
from .documents import normalize_name
from .dynamic_discovery import discover_documents_dynamic
from .imaging import (
    analyze_image,
    difference_hash,
    export_document_sources,
    hash_distance,
    iter_source_images,
    read_image_dpi,
    safe_target_path,
)
from .models import (
    CheckResult,
    DocumentBundle,
    DocumentSource,
    LocalVisualResult,
    ManifestRow,
    PersonReview,
    Status,
)
from .ocr import OCREngine, mask_identifier, normalize_alphanumeric


class VisualAnalyzer(Protocol):
    def analyze(self, image: Image.Image) -> LocalVisualResult: ...


_STATUS_RANK = {
    Status.OK: 0,
    Status.NOT_APPLICABLE: 0,
    Status.MANUAL_REVIEW: 1,
    Status.NOT_LEGIBLE: 2,
    Status.ERROR: 3,
    Status.MISSING: 4,
}


def _worse(current: Status, candidate: Status) -> Status:
    return candidate if _STATUS_RANK[candidate] > _STATUS_RANK[current] else current


def _fmt_number(value: str, config: ReviewConfig) -> str:
    """Show a passport number in full or masked, per configuration."""
    return mask_identifier(value) if config.mask_passport_numbers else value


def _type_from_filename(path: Path, config: ReviewConfig) -> str | None:
    """Best-effort document type from the file name (used only to name copies of
    non-reviewable files); returns 'front'/'back'/'blank'/'photo' or None."""
    stem = f" {normalize_name(path.stem)} "
    for label, keywords in (
        ("photo", config.photo_keywords),
        ("front", config.front_keywords),
        ("back", config.back_keywords),
        ("blank", config.blank_keywords),
    ):
        for keyword in keywords:
            normalized = normalize_name(keyword)
            if normalized and f" {normalized} " in stem:
                return label
    return None


def _format_notes(bundle: DocumentBundle, config: ReviewConfig) -> list[str]:
    """Human-readable notes about non-eligible file formats in this folder."""
    notes: list[str] = []
    png_types: list[str] = []
    for label, sources in (
        ("front", bundle.front),
        ("last", bundle.back),
        ("blank", bundle.blank),
        ("photo", bundle.photo),
    ):
        if any(source.path.suffix.lower() == ".png" for source in sources):
            png_types.append(label)
    if png_types:
        notes.append(
            "PNG is not an eligible format (only JPG/JPEG); converted to JPG in the output for: "
            + ", ".join(sorted(set(png_types))) + "."
        )
    if bundle.ineligible:
        extensions = sorted({(path.suffix.lower().lstrip(".") or "unknown") for path in bundle.ineligible})
        types = sorted({(_type_from_filename(path, config) or "document") for path in bundle.ineligible})
        notes.append(
            f"{len(bundle.ineligible)} non-eligible file(s) found ({', '.join(extensions)}) - not reviewed, "
            f"copied as-is with the new name: {', '.join(types)}. Only JPG/JPEG is allowed."
        )
    return notes


def _passport_page_check(
    image: Image.Image,
    document_type: str,
    expected_passport_no: str,
    config: ReviewConfig,
    ocr_engine: OCREngine,
    visual_analyzer: VisualAnalyzer | None,
) -> tuple[Status, list[str], str | None, dict[str, object], int]:
    metrics = analyze_image(image)
    status = Status.OK
    comments: list[str] = []
    details: dict[str, object] = {
        "width": metrics.width,
        "height": metrics.height,
        "blur_score": round(metrics.blur_score, 1),
        "contrast": round(metrics.contrast, 1),
    }

    # Blank pages are naturally pale and low-detail (mostly empty), so blur/contrast
    # are not meaningful quality signals for them - they are verified manually. Skip
    # these checks for blank pages; only format / missing / the number matter.
    if document_type != "blank":
        if metrics.blur_score < config.minimum_blur_score:
            status = _worse(status, Status.NOT_LEGIBLE)
            comments.append(f"Image may be blurred (blur score {metrics.blur_score:.1f}).")
        if metrics.contrast < config.minimum_contrast:
            status = _worse(status, Status.NOT_LEGIBLE)
            comments.append(f"Image contrast is low ({metrics.contrast:.1f}).")

    ocr = ocr_engine.recognize(image, expected_passport_no)
    page_number = ocr.page_number
    details.update({
        "ocr_engine": ocr.engine,
        "ocr_confidence": round(ocr.confidence, 1),
        "passport_number_found": ocr.expected_number_found,
        "page_number": page_number or "",
    })
    if ocr.error:
        status = _worse(status, Status.MANUAL_REVIEW)
        comments.append(ocr.error)
    elif expected_passport_no and ocr.expected_number_found:
        # The front-page number is present on this page, so the check passes even if
        # another passport-like number (usually the old/previous passport, printed
        # above the current one) also appears. Note the extra number for clarity.
        others = [
            value for value in ocr.observed_passport_numbers
            if normalize_alphanumeric(value) != normalize_alphanumeric(expected_passport_no)
        ]
        if document_type in {"back", "blank"} and others:
            comments.append(
                "Current passport number matches the front page; another number is also present "
                f"(likely the previous/old passport): {', '.join(_fmt_number(value, config) for value in others)}."
            )
    elif expected_passport_no and not ocr.expected_number_found:
        observed = ", ".join(_fmt_number(value, config) for value in ocr.observed_passport_numbers)
        if document_type == "blank":
            # The number on blank pages is usually dot-printed and can appear
            # mirrored, so OCR frequently cannot read it. This is a "verify
            # manually" case, not an error or a re-upload request.
            status = _worse(status, Status.NOT_LEGIBLE)
            detail = f" Numbers read: {observed}." if ocr.observed_passport_numbers else ""
            comments.append(
                "Could not read the passport number on the blank page - it is often dot-printed and can "
                "appear mirrored, so OCR may fail; verify manually." + detail
            )
        elif document_type == "back" and ocr.observed_passport_numbers:
            # The address/last page normally also carries the OLD passport number
            # (printed above the current one, which sits below the barcode/MRZ), so a
            # non-matching number is not by itself an error.
            status = _worse(status, Status.NOT_LEGIBLE)
            comments.append(
                f"Could not confirm the current passport number on the address page (numbers read: {observed}); "
                "the old/previous passport number may be printed above the current one (below the barcode) - verify."
            )
        elif ocr.observed_passport_numbers:
            status = _worse(status, Status.ERROR)
            comments.append(f"A different passport-like number was detected: {observed}.")
        else:
            status = _worse(status, Status.NOT_LEGIBLE)
            comments.append(
                f"Expected passport number was not readable (OCR confidence {ocr.confidence:.0f}); no different passport-like number was confirmed."
            )
    elif not expected_passport_no:
        if ocr.observed_passport_numbers:
            status = _worse(status, Status.MANUAL_REVIEW)
            observed = ", ".join(_fmt_number(value, config) for value in ocr.observed_passport_numbers)
            comments.append(f"Passport-like number detected but no canonical front-page number was established: {observed}.")
        else:
            status = _worse(status, Status.NOT_LEGIBLE)
            comments.append("Passport number could not be established from the folder.")

    if visual_analyzer is None:
        status = _worse(status, Status.MANUAL_REVIEW)
        comments.append("Local hand detector is unavailable; check manually for fingers or objects.")
    else:
        visual = visual_analyzer.analyze(image)
        if visual.error or not visual.available:
            status = _worse(status, Status.MANUAL_REVIEW)
            comments.append(visual.error or "Local visual review produced no result.")
        else:
            details["hand_count"] = visual.hand_count
            if (visual.hand_count or 0) > 0:
                status = _worse(status, Status.ERROR)
                comments.append(f"Local hand detector found {visual.hand_count} hand(s)/finger region(s).")
            elif config.manual_object_check_when_no_hand_detected:
                status = _worse(status, Status.MANUAL_REVIEW)
                comments.append("No hand was detected; manually confirm there is no partial finger or other object.")

    return status, comments, page_number, details, difference_hash(image)


def check_passport_document(
    sources: list[DocumentSource],
    document_type: str,
    expected_passport_no: str,
    config: ReviewConfig,
    ocr_engine: OCREngine,
    visual_analyzer: VisualAnalyzer | None,
    require_unique_page_numbers: bool = False,
) -> CheckResult:
    if not sources:
        return CheckResult(Status.MISSING, [f"{document_type.title()} document was not found."])

    result = CheckResult(Status.OK)
    if document_type in {"front", "back"} and len(sources) > 1:
        result.status = Status.MANUAL_REVIEW
        result.add(f"Multiple {document_type} candidates were detected.")

    page_numbers: list[str] = []
    page_hashes: list[tuple[str, int, str | None]] = []
    page_details: list[dict[str, object]] = []
    total_pages = 0

    for source in sources:
        try:
            images = list(iter_source_images(source, config))
        except Exception as exc:
            result.status = _worse(result.status, Status.ERROR)
            result.add(f"Could not open {source.display_name()}: {exc}")
            continue
        if not images:
            result.status = _worse(result.status, Status.ERROR)
            result.add(f"No readable pages in {source.display_name()}.")
            continue

        for page_offset, image in enumerate(images, start=1):
            total_pages += 1
            label = source.display_name()
            if len(images) > 1:
                label += f" image {page_offset}"
            page_status, comments, page_number, details, page_hash = _passport_page_check(
                image=image,
                document_type=document_type,
                expected_passport_no=expected_passport_no,
                config=config,
                ocr_engine=ocr_engine,
                visual_analyzer=visual_analyzer,
            )
            result.status = _worse(result.status, page_status)
            for comment in comments:
                result.add(f"{label}: {comment}")
            if page_number:
                page_numbers.append(page_number)
            page_hashes.append((label, page_hash, page_number))
            details["source"] = label
            page_details.append(details)

    if total_pages == 0:
        result.status = Status.ERROR

    if require_unique_page_numbers and total_pages:
        if len(page_numbers) != total_pages:
            result.status = _worse(result.status, Status.MANUAL_REVIEW)
            result.add("Could not read the printed page number on every blank page; verify manually.")
        elif len(set(page_numbers)) != len(page_numbers):
            result.status = _worse(result.status, Status.ERROR)
            result.add("Duplicate printed blank-page numbers were detected.")
        else:
            result.details["page_numbers"] = page_numbers

        duplicate_pairs: list[str] = []
        for index, (label_a, hash_a, number_a) in enumerate(page_hashes):
            for label_b, hash_b, number_b in page_hashes[index + 1:]:
                # Different readable printed page numbers are stronger evidence than
                # visual similarity, because blank passport pages naturally look alike.
                if number_a and number_b and number_a != number_b:
                    continue
                distance = hash_distance(hash_a, hash_b)
                if distance <= config.near_duplicate_hash_distance:
                    duplicate_pairs.append(f"{label_a} <-> {label_b} (distance {distance})")
        if duplicate_pairs:
            result.status = _worse(result.status, Status.MANUAL_REVIEW)
            result.add("Visually near-identical blank pages need duplicate confirmation: " + "; ".join(duplicate_pairs))
            result.details["possible_duplicate_pairs"] = duplicate_pairs

    result.details["page_count"] = total_pages
    result.details["pages"] = page_details
    return result


def check_photo(
    sources: list[DocumentSource],
    config: ReviewConfig,
    visual_analyzer: VisualAnalyzer | None,
) -> CheckResult:
    if not sources:
        return CheckResult(Status.MISSING, ["Photo was not found."])

    result = CheckResult(Status.OK)
    if len(sources) > 1:
        result.status = Status.MANUAL_REVIEW
        result.add("Multiple photo candidates were detected.")

    source = sources[0]
    try:
        images = list(iter_source_images(source, config))
    except Exception as exc:
        return CheckResult(Status.ERROR, [f"Could not open photo: {exc}"])
    if len(images) != 1:
        return CheckResult(Status.ERROR, ["Photo candidate must contain exactly one image."])

    image = images[0]
    metrics = analyze_image(image)
    result.details.update({
        "source": source.display_name(),
        "width": metrics.width,
        "height": metrics.height,
        "blur_score": round(metrics.blur_score, 1),
        "contrast": round(metrics.contrast, 1),
        "white_border_ratio": round(metrics.white_border_ratio, 3),
        "haar_face_count": metrics.face_count,
        "haar_eye_count": metrics.eye_count,
    })

    width_cm = config.exact_photo_width / config.required_photo_dpi * 2.54
    height_cm = config.exact_photo_height / config.required_photo_dpi * 2.54
    physical = (
        f"{config.exact_photo_width} x {config.exact_photo_height} px at {config.required_photo_dpi} DPI "
        f"= {width_cm:.2f} x {height_cm:.2f} cm"
    )

    if (metrics.width, metrics.height) != (config.exact_photo_width, config.exact_photo_height):
        result.status = _worse(result.status, Status.ERROR)
        result.add(
            f"Photo dimensions are {metrics.width} x {metrics.height}; required {physical}."
        )

    dpi = read_image_dpi(source.path)
    result.details["dpi"] = dpi
    if dpi is None:
        result.status = _worse(result.status, Status.ERROR)
        result.add(f"Photo DPI could not be confirmed from the file; it should be {physical}.")
    elif round(dpi[0]) != config.required_photo_dpi or round(dpi[1]) != config.required_photo_dpi:
        result.status = _worse(result.status, Status.ERROR)
        result.add(
            f"Photo is {dpi[0]:.0f} x {dpi[1]:.0f} DPI; it should be {physical}."
        )
    else:
        result.add(f"Photo is {physical}.")
    if metrics.blur_score < config.minimum_blur_score:
        result.status = _worse(result.status, Status.ERROR)
        result.add(f"Photo appears blurred (blur score {metrics.blur_score:.1f}).")
    if metrics.contrast < config.minimum_contrast:
        result.status = _worse(result.status, Status.ERROR)
        result.add(f"Photo contrast is low ({metrics.contrast:.1f}).")
    if metrics.white_border_ratio < config.minimum_white_border_ratio:
        result.status = _worse(result.status, Status.ERROR)
        result.add(f"Background border is not sufficiently white ({metrics.white_border_ratio:.0%} white).")

    if visual_analyzer is None:
        result.status = _worse(result.status, Status.MANUAL_REVIEW)
        result.add("MediaPipe face/hand checks are unavailable; verify face and hands manually.")
    else:
        visual = visual_analyzer.analyze(image)
        if visual.error or not visual.available:
            result.status = _worse(result.status, Status.MANUAL_REVIEW)
            result.add(visual.error or "MediaPipe visual review produced no result.")
        else:
            result.details.update({
                "mediapipe_face_count": visual.face_count,
                "hand_count": visual.hand_count,
                "face_center_offset_x": visual.face_center_offset_x,
                "face_center_offset_y": visual.face_center_offset_y,
                "face_width_ratio": visual.face_width_ratio,
                "face_height_ratio": visual.face_height_ratio,
                "eye_tilt_degrees": visual.eye_tilt_degrees,
            })
            if visual.face_count == 0:
                result.status = _worse(result.status, Status.MANUAL_REVIEW)
                result.add("A face was not confidently detected; verify manually.")
            elif (visual.face_count or 0) > 1:
                result.status = _worse(result.status, Status.ERROR)
                result.add(f"More than one face was detected ({visual.face_count}).")
            else:
                if (visual.face_center_offset_x or 0.0) > config.maximum_face_center_offset_ratio:
                    result.status = _worse(result.status, Status.MANUAL_REVIEW)
                    result.add("Face appears horizontally off-centre.")
                if visual.face_height_ratio is not None and not (
                    config.minimum_face_height_ratio <= visual.face_height_ratio <= config.maximum_face_height_ratio
                ):
                    result.status = _worse(result.status, Status.MANUAL_REVIEW)
                    result.add(f"Face size may be unsuitable (height ratio {visual.face_height_ratio:.2f}).")
                if (visual.eye_tilt_degrees or 0.0) > config.maximum_eye_tilt_degrees:
                    result.status = _worse(result.status, Status.MANUAL_REVIEW)
                    result.add(f"Head/eye line may be tilted ({visual.eye_tilt_degrees:.1f} degrees).")
            if (visual.hand_count or 0) > 0:
                result.status = _worse(result.status, Status.ERROR)
                result.add(f"A hand or fingers may be visible ({visual.hand_count} detected).")

    # Jewellery, bindi, ear visibility and glasses glare cannot be judged automatically.
    # The reminder is always recorded; it only escalates the status when the caller
    # wants subjective items to force a manual-review outcome (standalone CSV mode).
    result.add(
        "Manually confirm: no jewellery/bindi, both ears uncovered, and no glasses glare/frame obstruction."
    )
    if config.manual_subjective_photo_checks:
        result.status = _worse(result.status, Status.MANUAL_REVIEW)
    return result


def determine_overall(*statuses: Status) -> Status:
    overall = Status.OK
    for status in statuses:
        overall = _worse(overall, status)
    return overall


def export_bundle(
    bundle: DocumentBundle,
    manifest: ManifestRow,
    output_root: Path,
    config: ReviewConfig,
) -> list[str]:
    output_directory = output_root / manifest.folder_name
    exported: list[Path] = []
    exported.extend(export_document_sources(bundle.front, output_directory, manifest.front_output_name, config))
    exported.extend(export_document_sources(bundle.back, output_directory, manifest.back_output_name, config))
    multiple_blank = len(bundle.blank) > 1
    for index, source in enumerate(bundle.blank, start=1):
        base_name = f"{manifest.blank_output_name}_{index:02d}" if multiple_blank else manifest.blank_output_name
        exported.extend(
            export_document_sources(
                [source],
                output_directory,
                base_name,
                config,
                prefer_pdf_for_multiple=False,
            )
        )
    exported.extend(export_document_sources(
        bundle.photo,
        output_directory,
        manifest.photo_output_name,
        config,
        prefer_pdf_for_multiple=False,
    ))

    # Copy PDF/other non-eligible files as-is (never rendered/converted), named by
    # their filename document type when known.
    type_names = {
        "front": manifest.front_output_name,
        "back": manifest.back_output_name,
        "blank": manifest.blank_output_name,
        "photo": manifest.photo_output_name,
    }
    for offset, path in enumerate(bundle.ineligible, start=1):
        label = _type_from_filename(path, config)
        base_name = type_names.get(label) or f"{manifest.folder_name}_document_{offset:02d}"
        try:
            output_directory.mkdir(parents=True, exist_ok=True)
            target = safe_target_path(output_directory, base_name, path.suffix)
            shutil.copy2(path, target)
            exported.append(target)
        except Exception:
            continue
    return [str(path) for path in exported]



def _sanitize_name(name: str) -> str:
    cleaned = "".join(character for character in name if character not in '<>:"/\\|?*').strip().rstrip(".")
    return cleaned


def rename_bundle_in_place(
    bundle: DocumentBundle,
    manifest: ManifestRow,
    config: ReviewConfig,
) -> tuple[Path, list[tuple[str, str]], list[str]]:
    """Rename the classified files to the spreadsheet names and the folder to the
    spreadsheet folder name, in place. Returns the (possibly new) folder path, an
    old-name -> new-name log, and any issues encountered.

    Renaming is staged (each source is first moved to a temporary name) so that
    swapping two files' names cannot destroy data.
    """
    folder = bundle.folder
    issues: list[str] = []
    rename_log: list[tuple[str, str]] = []

    targets: list[tuple[Path, str]] = []
    for source in bundle.front:
        targets.append((source.path, manifest.front_output_name))
    for source in bundle.back:
        targets.append((source.path, manifest.back_output_name))
    ordered_blank = sorted(bundle.blank, key=lambda item: item.path.name.casefold())
    for index, source in enumerate(ordered_blank, start=1):
        base = manifest.blank_output_name
        if len(ordered_blank) > 1:
            base = f"{base}_{index:02d}"
        targets.append((source.path, base))
    for source in bundle.photo:
        targets.append((source.path, manifest.photo_output_name))

    staged: list[tuple[Path, str, str, str]] = []  # (temp_path, base_name, suffix, original_name)
    for index, (source_path, base_name) in enumerate(targets):
        if not source_path.exists():
            issues.append(f"File missing during rename: {source_path.name}")
            continue
        temp_path = source_path.with_name(f"~stg{index:02d}{source_path.suffix}")
        try:
            source_path.rename(temp_path)
        except Exception as exc:
            issues.append(f"Could not stage {source_path.name}: {exc}")
            continue
        staged.append((temp_path, base_name, source_path.suffix, source_path.name))

    for temp_path, base_name, suffix, original_name in staged:
        target = safe_target_path(folder, base_name, suffix)
        try:
            temp_path.rename(target)
            rename_log.append((original_name, target.name))
        except Exception as exc:
            issues.append(f"Could not rename {original_name}: {exc}")
            try:
                temp_path.rename(temp_path.with_name(original_name))
            except Exception:
                issues.append(f"Left staged file in place: {temp_path.name}")

    new_folder = folder
    target_folder_name = _sanitize_name(manifest.folder_name)
    if target_folder_name and target_folder_name != folder.name:
        candidate = folder.parent / target_folder_name
        if candidate.exists():
            issues.append(f"Cannot rename folder; target already exists: {target_folder_name}")
        else:
            try:
                folder.rename(candidate)
                rename_log.append((folder.name + "\\", target_folder_name + "\\"))
                new_folder = candidate
            except Exception as exc:
                issues.append(f"Could not rename folder to {target_folder_name}: {exc}")

    return new_folder, rename_log, issues


def review_person_folder(
    folder: Path,
    row_number: int,
    output_root: Path,
    config: ReviewConfig,
    ocr_engine: OCREngine,
    visual_analyzer: VisualAnalyzer | None,
    copy_renamed: bool,
    manifest: ManifestRow | None = None,
    rename_in_place: bool = False,
) -> PersonReview:
    """Review one person folder.

    When ``manifest`` is supplied (for example from a spreadsheet row) its
    ``expected_passport_no`` is treated as the authoritative "first page" number
    that every other page is compared against, and its output names are used for
    the renamed copies. When it is ``None`` the folder is reviewed dynamically and
    the passport number is inferred from the images.
    """
    dynamic = manifest is None
    if manifest is None:
        safe_stem = folder.name.strip() or f"person_{row_number:03d}"
        manifest = ManifestRow(
            row_number=row_number,
            booking_id="",
            tsf_id="",
            gender="",
            name=folder.name,
            expected_passport_no="",
            group="",
            assigned_to="",
            folder_name=folder.name,
            front_output_name=f"{safe_stem}_passport_front",
            back_output_name=f"{safe_stem}_passport_back",
            blank_output_name=f"{safe_stem}_passport_blank",
            photo_output_name=f"{safe_stem}_photo",
            original={"Person Folder": folder.name},
        )

    reference_override = (manifest.expected_passport_no or "").strip()

    discovery = discover_documents_dynamic(folder, config, ocr_engine, visual_analyzer)
    bundle = discovery.bundle
    detected = discovery.detected_passport_number
    # The known first-page number (from the row) wins; otherwise fall back to what
    # was detected from the images.
    reference_number = reference_override or detected
    manifest.expected_passport_no = reference_number

    front = check_passport_document(
        bundle.front, "front", reference_number, config, ocr_engine, visual_analyzer
    )
    back = check_passport_document(
        bundle.back, "back", reference_number, config, ocr_engine, visual_analyzer
    )
    blank = check_passport_document(
        bundle.blank,
        "blank",
        reference_number,
        config,
        ocr_engine,
        visual_analyzer,
        require_unique_page_numbers=True,
    )
    photo = check_photo(bundle.photo, config, visual_analyzer)

    comments: list[str] = []
    if dynamic:
        comments.append("Dynamic folder scan; no manifest or spreadsheet metadata used.")
    comments.extend(bundle.notes)
    for note in _format_notes(bundle, config):
        comments.append("Format: " + note)
    if bundle.unclassified:
        comments.append("Unclassified files: " + ", ".join(path.name for path in bundle.unclassified))

    output_files: list[str] = []
    if copy_renamed:
        try:
            output_files = export_bundle(bundle, manifest, output_root, config)
        except Exception as exc:
            comments.append(f"Could not copy/rename output files: {exc}")

    renamed_folder: Path | None = None
    rename_log: list[tuple[str, str]] = []
    if rename_in_place:
        try:
            renamed_folder, rename_log, rename_issues = rename_bundle_in_place(bundle, manifest, config)
            for issue in rename_issues:
                comments.append(f"Rename: {issue}")
        except Exception as exc:
            comments.append(f"Could not rename in place: {exc}")

    detected_files = [
        *(source.display_name() for source in bundle.front),
        *(source.display_name() for source in bundle.back),
        *(source.display_name() for source in bundle.blank),
        *(source.display_name() for source in bundle.photo),
    ]
    folder_status = Status.OK

    if reference_override:
        # The row already tells us the true passport number. Verify that the
        # submitted images corroborate it rather than re-deriving it.
        if not detected:
            number_status = Status.MANUAL_REVIEW
            comments.append(
                "The passport number on record could not be independently confirmed from the images."
            )
        elif normalize_alphanumeric(detected) != normalize_alphanumeric(reference_override):
            number_status = Status.ERROR
            comments.append(
                f"Detected passport number ({_fmt_number(detected, config)}) does not match the number on "
                f"record ({_fmt_number(reference_override, config)})."
            )
        else:
            number_status = Status.OK
    else:
        number_status = Status.OK if discovery.passport_number_confident else Status.MANUAL_REVIEW
        if not detected:
            number_status = Status.NOT_LEGIBLE
        if detected and not discovery.passport_number_confident:
            comments.append("Detected passport number requires manual confirmation.")

    overall = determine_overall(folder_status, number_status, front.status, back.status, blank.status, photo.status)
    return PersonReview(
        manifest=manifest,
        folder_match_status=folder_status,
        matched_folder=folder,
        front=front,
        back=back,
        blank=blank,
        photo=photo,
        overall=overall,
        detected_files=detected_files,
        output_files=output_files,
        comments=comments,
        detected_passport_number=detected,
        passport_number_confident=discovery.passport_number_confident,
        renamed_folder=renamed_folder,
        rename_log=rename_log,
        bundle=bundle,
    )
