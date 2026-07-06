from __future__ import annotations

import importlib
import shutil
import sys
from pathlib import Path

from passport_review.config import ReviewConfig
from passport_review.local_vision import create_visual_analyzer
from passport_review.network_guard import enable_strict_offline_mode
from passport_review.ocr import create_ocr_engine


def check_import(name: str) -> bool:
    try:
        module = importlib.import_module(name)
        version = getattr(module, "__version__", "installed")
        print(f"[OK] {name}: {version}")
        return True
    except Exception as exc:
        print(f"[FAIL] {name}: {exc}")
        return False


def main() -> int:
    print("Passport Review Tool - local setup verification\n")
    ok = True
    for package in ("PIL", "cv2", "pypdfium2", "pytesseract", "mediapipe"):
        ok = check_import(package) and ok

    if shutil.which("tesseract"):
        print(f"[OK] Tesseract executable: {shutil.which('tesseract')}")
    else:
        print("[WARN] Tesseract executable not found on PATH. PaddleOCR can still be used.")

    config = ReviewConfig.from_json(Path("config.example.json"))
    enable_strict_offline_mode()
    try:
        engine, warnings = create_ocr_engine(config, "auto")
        print(f"[OK] Offline OCR initialised: {engine.name}")
        for warning in warnings:
            print(f"[WARN] {warning}")
    except Exception as exc:
        print(f"[FAIL] Offline OCR: {exc}")
        ok = False

    analyzer, warnings = create_visual_analyzer(config)
    for warning in warnings:
        print(f"[WARN] {warning}")
    if analyzer:
        print("[OK] MediaPipe face and hand models loaded from local files.")
        analyzer.close()
    else:
        ok = False

    print("\nVerification " + ("passed." if ok else "completed with problems."))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
