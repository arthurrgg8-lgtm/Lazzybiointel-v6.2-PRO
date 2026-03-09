#!/usr/bin/env python3
"""
AGE ROBUST ENGINE — LazzyBioIntel v6.2 PRO
Layer 1 of the Robust Fusion System

Strategy:
  - Periocular crop (eye + brow region) — most stable zone across 5–10 year aging
  - Uses InsightFace buffalo_sc for a lighter, occlusion-tolerant pass
  - Falls back to full-face buffalo_l embedding if periocular crop fails detection
  - Does NOT modify UltimateVerifier or any existing engine

Drop-in alongside existing system. No shared state with verify_v6.py.
"""

import cv2
import numpy as np
import mediapipe as mp
from insightface.app import FaceAnalysis
from typing import Optional, Tuple
from logger import LogManager

logger = LogManager.get_logger("age_robust_engine")

# ---------------------------------------------------------------------------
# Landmark indices for periocular region (MediaPipe FaceMesh 468-point model)
# Left eye outer→inner: 33, 7, 163, 144, 145, 153, 154, 155, 133
# Right eye outer→inner: 362, 382, 381, 380, 374, 373, 390, 249, 263
# Brow region top anchors: 70, 63, 105, 66, 107 (L), 336, 296, 334, 293, 300 (R)
# ---------------------------------------------------------------------------
_L_EYE = [33, 7, 163, 144, 145, 153, 154, 155, 133]
_R_EYE = [362, 382, 381, 380, 374, 373, 390, 249, 263]
_L_BROW = [70, 63, 105, 66, 107]
_R_BROW = [336, 296, 334, 293, 300]
_PERIOCULAR_IDX = _L_EYE + _R_EYE + _L_BROW + _R_BROW


class PeriocularCropper:
    """
    Extracts a tight bounding box around both eyes + brows using MediaPipe.
    Falls back to a fixed upper-face band if landmarks unavailable.
    """

    _mesh = None

    @classmethod
    def _get_mesh(cls):
        if cls._mesh is None:
            cls._mesh = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=True,
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5,
            )
        return cls._mesh

    @classmethod
    def cleanup(cls):
        if cls._mesh:
            cls._mesh.close()
            cls._mesh = None

    @staticmethod
    def crop(img: np.ndarray) -> Tuple[Optional[np.ndarray], str]:
        """
        Returns (cropped_img, method_used).
        method_used: "periocular" | "upper_band_fallback"
        """
        h, w = img.shape[:2]
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        try:
            mesh = PeriocularCropper._get_mesh()
            res = mesh.process(rgb)

            if res.multi_face_landmarks:
                lm = res.multi_face_landmarks[0].landmark

                xs = [lm[i].x * w for i in _PERIOCULAR_IDX]
                ys = [lm[i].y * h for i in _PERIOCULAR_IDX]

                pad_x = int((max(xs) - min(xs)) * 0.40)
                pad_y = int((max(ys) - min(ys)) * 0.55)

                x0 = max(0, int(min(xs)) - pad_x)
                x1 = min(w, int(max(xs)) + pad_x)
                y0 = max(0, int(min(ys)) - pad_y)
                y1 = min(h, int(max(ys)) + pad_y)

                crop = img[y0:y1, x0:x1]
                if crop.shape[0] >= 32 and crop.shape[1] >= 32:
                    return crop, "periocular"

        except Exception:
            logger.warning("MediaPipe periocular crop failed, using fallback", exc_info=True)

        # Fallback: upper 45% of the image (eye + forehead band)
        y1 = int(h * 0.45)
        return img[0:y1, :], "upper_band_fallback"


class AgeRobustEngine:
    """
    Produces age-stable embeddings using a periocular crop.

    MEMORY-EFFICIENT: accepts a shared FaceAnalysis instance from the
    already-loaded UltimateVerifier — zero extra model copies in RAM.

    Usage:
        verifier = UltimateVerifier()
        age_eng  = AgeRobustEngine(shared_app=verifier.engine.app)
    """

    def __init__(self, shared_app=None, providers=None):
        if shared_app is not None:
            logger.info("AgeRobustEngine: using shared FaceAnalysis — no extra RAM")
            self._app = shared_app
            self._owns_app = False
        else:
            if providers is None:
                providers = ["CPUExecutionProvider"]
            logger.info("AgeRobustEngine: loading own FaceAnalysis (no shared app given)")
            self._app = FaceAnalysis(name="buffalo_l", providers=providers)
            self._app.prepare(ctx_id=0, det_size=(640, 640))
            self._owns_app = True
        logger.info("AgeRobustEngine: ready")

    def embed_periocular(self, path: str) -> Tuple[Optional[np.ndarray], str]:
        """
        Returns (embedding, method).
        Crops to periocular region first; falls back to full face on failure.
        """
        img = cv2.imread(path)
        if img is None:
            return None, "load_error"

        crop, method = PeriocularCropper.crop(img)

        try:
            faces = self._app.get(crop)
            if faces:
                return faces[0].embedding, method
        except Exception:
            logger.warning("Periocular embed failed, trying full-face", exc_info=True)

        try:
            faces = self._app.get(img)
            if faces:
                return faces[0].embedding, "full_face_fallback"
        except Exception:
            logger.error("Full-face fallback also failed", exc_info=True)

        return None, "failed"

    def cleanup(self):
        PeriocularCropper.cleanup()
        if self._owns_app:
            self._app = None