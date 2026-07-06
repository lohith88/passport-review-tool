from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image

from .config import ReviewConfig
from .models import LocalVisualResult


class MediaPipeVisionAnalyzer:
    """Runs downloaded MediaPipe face and hand models entirely on-device."""

    def __init__(self, config: ReviewConfig) -> None:
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision

        face_path = config.resolve_model_path(config.face_landmarker_model)
        hand_path = config.resolve_model_path(config.hand_landmarker_model)
        missing = [str(path) for path in (face_path, hand_path) if not path.exists()]
        if missing:
            raise FileNotFoundError("Missing MediaPipe model files: " + ", ".join(missing))

        self.mp = mp
        face_options = vision.FaceLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(face_path)),
            running_mode=vision.RunningMode.IMAGE,
            num_faces=3,
            min_face_detection_confidence=config.minimum_face_detection_confidence,
            min_face_presence_confidence=config.minimum_face_detection_confidence,
        )
        hand_options = vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(hand_path)),
            running_mode=vision.RunningMode.IMAGE,
            num_hands=2,
            min_hand_detection_confidence=config.minimum_hand_detection_confidence,
            min_hand_presence_confidence=config.minimum_hand_detection_confidence,
        )
        self.face_landmarker = vision.FaceLandmarker.create_from_options(face_options)
        self.hand_landmarker = vision.HandLandmarker.create_from_options(hand_options)
        self.max_side = max(256, int(getattr(config, "max_vision_image_side", 1600)))

    @staticmethod
    def _average_point(landmarks: list, indexes: list[int]) -> tuple[float, float]:
        points = [landmarks[index] for index in indexes]
        return (
            sum(point.x for point in points) / len(points),
            sum(point.y for point in points) / len(points),
        )

    def analyze(self, image: Image.Image) -> LocalVisualResult:
        try:
            # MediaPipe's native models can segfault on very large frames. Downscale
            # first; the models return normalized (0-1) coordinates, so every metric
            # (face size/position/tilt) is unaffected by the resize.
            if max(image.size) > self.max_side:
                scale = self.max_side / max(image.size)
                image = image.resize(
                    (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                    Image.Resampling.LANCZOS,
                )
            rgb = np.ascontiguousarray(np.asarray(image.convert("RGB"), dtype=np.uint8))
            mp_image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb)
            face_result = self.face_landmarker.detect(mp_image)
            hand_result = self.hand_landmarker.detect(mp_image)
            faces = list(face_result.face_landmarks or [])
            hands = list(hand_result.hand_landmarks or [])

            result = LocalVisualResult(available=True, face_count=len(faces), hand_count=len(hands))
            if len(faces) == 1:
                landmarks = faces[0]
                xs = [point.x for point in landmarks]
                ys = [point.y for point in landmarks]
                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)
                center_x = (min_x + max_x) / 2.0
                center_y = (min_y + max_y) / 2.0
                result.face_center_offset_x = abs(center_x - 0.5)
                result.face_center_offset_y = abs(center_y - 0.5)
                result.face_width_ratio = max_x - min_x
                result.face_height_ratio = max_y - min_y

                left_eye = self._average_point(landmarks, [33, 133, 159, 145])
                right_eye = self._average_point(landmarks, [362, 263, 386, 374])
                dx = right_eye[0] - left_eye[0]
                dy = right_eye[1] - left_eye[1]
                angle = math.degrees(math.atan2(dy, dx))
                if angle > 90.0:
                    angle -= 180.0
                elif angle < -90.0:
                    angle += 180.0
                result.eye_tilt_degrees = abs(angle)
            return result
        except Exception as exc:
            return LocalVisualResult(error=f"MediaPipe review failed: {exc}")

    def close(self) -> None:
        self.face_landmarker.close()
        self.hand_landmarker.close()


def create_visual_analyzer(config: ReviewConfig) -> tuple[MediaPipeVisionAnalyzer | None, list[str]]:
    try:
        return MediaPipeVisionAnalyzer(config), []
    except Exception as exc:
        return None, [f"Local MediaPipe checks unavailable: {exc}"]
