from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import ReviewConfig
from .dynamic_discovery import list_person_folders
from .local_vision import create_visual_analyzer
from .network_guard import enable_strict_offline_mode
from .ocr import MemoizingOCREngine, create_ocr_engine
from .pipeline import review_person_folder
from .reporting import write_manual_queue, write_results, write_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Dynamically scan person-wise passport/photo folders using local-only OCR and computer vision. "
            "No manifest or spreadsheet metadata is required."
        )
    )
    parser.add_argument(
        "--folders-root",
        type=Path,
        required=True,
        help="Root directory whose immediate subfolders are individual people.",
    )
    parser.add_argument("--output-root", type=Path, required=True, help="Directory for reports and renamed copies.")
    parser.add_argument("--config", type=Path, help="Optional JSON configuration file.")
    parser.add_argument("--copy-renamed", action="store_true", help="Create standardized copies; originals are untouched.")
    parser.add_argument(
        "--ocr-engine",
        choices=("auto", "paddle", "tesseract"),
        help="Local OCR engine. auto prefers PaddleOCR and falls back to Tesseract.",
    )
    parser.add_argument("--skip-local-vision", action="store_true", help="Skip MediaPipe face/hand models.")
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Do not install the process-level network block. Not recommended for real PII processing.",
    )
    parser.add_argument("--show-pii-in-console", action="store_true", help="Print person-folder names while processing.")
    parser.add_argument("--limit", type=int, help="Process only the first N person folders, alphabetically.")
    parser.add_argument("--start-folder", type=int, default=1, help="Start at the Nth folder, alphabetically (1-based).")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = ReviewConfig.from_json(args.config)
        folders = list_person_folders(args.folders_root, args.output_root)
    except Exception as exc:
        print(f"Configuration/folder error: {exc}", file=sys.stderr)
        return 2

    start = max(args.start_folder - 1, 0)
    folders = folders[start:]
    if args.limit is not None:
        folders = folders[: max(args.limit, 0)]
    if not folders:
        print(
            "No person folders were found. Expected structure: folders-root\\Person Name\\passport-images.jpg",
            file=sys.stderr,
        )
        return 2

    print(f"Person folders discovered dynamically: {len(folders)}")
    offline_strict = not args.allow_network
    if offline_strict:
        enable_strict_offline_mode()
        print("Strict offline mode enabled: outbound network connections are blocked for this process.")
    else:
        print("WARNING: network blocking is disabled. Do not process real PII unless explicitly approved.")

    try:
        base_ocr_engine, ocr_warnings = create_ocr_engine(config, args.ocr_engine)
        ocr_engine = MemoizingOCREngine(base_ocr_engine)
    except Exception as exc:
        print(f"Could not initialise a local OCR engine: {exc}", file=sys.stderr)
        return 2
    for warning in ocr_warnings:
        print(f"WARNING: {warning}")
    print(f"OCR engine: {ocr_engine.name}")

    visual_analyzer = None
    if not args.skip_local_vision:
        visual_analyzer, visual_warnings = create_visual_analyzer(config)
        for warning in visual_warnings:
            print(f"WARNING: {warning}")
        if visual_analyzer is not None:
            print("Local MediaPipe face/hand models loaded.")

    args.output_root.mkdir(parents=True, exist_ok=True)
    renamed_root = args.output_root / "renamed-documents"
    reviews = []
    try:
        for index, folder in enumerate(folders, start=1):
            label = folder.name if args.show_pii_in_console else f"person folder {index}"
            print(f"[{index}/{len(folders)}] Reviewing {label}...")
            try:
                review = review_person_folder(
                    folder=folder,
                    row_number=start + index,
                    output_root=renamed_root,
                    config=config,
                    ocr_engine=ocr_engine,
                    visual_analyzer=visual_analyzer,
                    copy_renamed=args.copy_renamed,
                )
                reviews.append(review)
                print(f"    {review.overall.value}")
            except KeyboardInterrupt:
                print("Interrupted by user.", file=sys.stderr)
                break
            except Exception as exc:
                print(f"    Unexpected error: {exc}", file=sys.stderr)
    finally:
        if visual_analyzer is not None:
            visual_analyzer.close()

    if not reviews:
        print("No completed reviews; no report written.", file=sys.stderr)
        return 1

    results_path = args.output_root / "review_results.csv"
    summary_path = args.output_root / "review_summary.txt"
    queue_path = args.output_root / "manual_review_queue.csv"
    write_results(results_path, reviews)
    write_manual_queue(queue_path, reviews)
    write_summary(summary_path, reviews, ocr_engine.name, offline_strict)
    print(f"\nResults: {results_path}")
    print(f"Manual queue: {queue_path}")
    print(f"Summary: {summary_path}")
    if args.copy_renamed:
        print(f"Renamed copies: {renamed_root}")
    return 0
