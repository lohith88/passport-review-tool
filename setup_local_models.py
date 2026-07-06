from __future__ import annotations

import argparse
import os
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw

from passport_review.config import ReviewConfig
from passport_review.ocr import create_ocr_engine


MODEL_URLS = {
    "face_landmarker.task": "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task",
    "hand_landmarker.task": "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task",
}


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    print(f"Downloading {destination.name}...")
    with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as output:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
    temporary.replace(destination)
    print(f"Saved: {destination}")


def warm_paddle(config: ReviewConfig) -> None:
    print("Initialising PaddleOCR and downloading its local OCR models if needed...")
    os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "BOS")
    engine, warnings = create_ocr_engine(config, "paddle")
    for warning in warnings:
        print(f"WARNING: {warning}")
    image = Image.new("RGB", (900, 220), "white")
    draw = ImageDraw.Draw(image)
    draw.text((40, 70), "PASSPORT P1234567 PAGE 12", fill="black")
    result = engine.recognize(image, "P1234567")
    if result.error:
        raise RuntimeError(result.error)
    print(f"PaddleOCR local model check completed. OCR confidence: {result.confidence:.1f}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download only the local models used by the review tool.")
    parser.add_argument("--config", type=Path, default=Path("config.example.json"))
    parser.add_argument("--skip-mediapipe", action="store_true")
    parser.add_argument("--skip-paddle", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    config = ReviewConfig.from_json(args.config)
    if not args.skip_mediapipe:
        for filename, url in MODEL_URLS.items():
            destination = config.resolve_model_path(filename)
            if destination.exists() and destination.stat().st_size > 100_000 and not args.force:
                print(f"Already present: {destination}")
            else:
                download(url, destination)

    if not args.skip_paddle:
        warm_paddle(config)

    print("\nLocal model setup is complete. You can disconnect the machine from the internet before reviewing PII.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"Setup failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
