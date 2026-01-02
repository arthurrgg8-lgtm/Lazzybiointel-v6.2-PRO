#!/usr/bin/env python3
"""
ULTIMATE FACE VERIFICATION v6.2
Enhanced Professional Edition

"""
import os
import sys
import time
import json
import logging 
from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np
import mediapipe as mp
from insightface.app import FaceAnalysis

from lz_validators import validate_image_file   

# =============================================================================
# Configuration
# =============================================================================

class Config:
    """Centralized configuration"""

    BASE_THRESHOLD = 0.45
    HIGH_CONF_DELTA = 0.08
    UNCERTAIN_DELTA = 0.05

    LOW_QUALITY_THRESHOLD = 50
    HIGH_GEOMETRY_THRESHOLD = 70
    QUALITY_ADJUSTMENT = 0.03
    GEOMETRY_ADJUSTMENT = 0.03

    BLUR_WEIGHT = 0.35
    BRIGHTNESS_WEIGHT = 0.25
    CONTRAST_WEIGHT = 0.20
    RESOLUTION_WEIGHT = 0.20

    DET_SIZE = (640, 640)
    MIN_DETECTION_CONFIDENCE = 0.5

    JSON_OUTPUT = False
    VERBOSE = True


# =============================================================================
# Logging
# =============================================================================

from logger import LogManager
logger = LogManager.get_logger(__name__)

import random  # <-- required for jitter

def _retry(op_name, fn, tries=3, base_delay=0.25):
    last = None
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except Exception as e:
            last = e
            logger.warning(
                f"{op_name} failed (attempt {attempt}/{tries})",
                extra={"op": op_name, "attempt": attempt, "tries": tries},
                exc_info=True,
            )
            if attempt < tries:
                time.sleep(base_delay * (2 ** (attempt - 1)) + random.uniform(0,
0.05))
    raise last

# =============================================================================
# Phase 1: Dependency Check (Fail fast, no algorithm change)
# =============================================================================

def check_dependencies() -> None:
    if not hasattr(mp, "solutions") or not hasattr(mp.solutions, "face_mesh"):
        raise RuntimeError(
            "MediaPipe API mismatch: mp.solutions.face_mesh missing. "
            "Use Python 3.11 venv and mediapipe==0.10.14."
        )
    logger.info("Dependencies validated: MediaPipe solutions OK")

check_dependencies()


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ImageQuality:
    blur: float
    brightness: float
    contrast: float
    resolution: Tuple[int, int]
    score: float
    valid: bool = True
    error: Optional[str] = None


@dataclass
class VerificationResult:
    verdict: str
    confidence: float
    similarity: float
    geometry_sim: float
    quality_avg: float
    execution_time: float
    q1: ImageQuality
    q2: ImageQuality
    error: Optional[str] = None


# =============================================================================
# Image Quality Analyzer
# =============================================================================

class ImageQualityAnalyzer:

    @staticmethod
    def analyze(path: str) -> ImageQuality:
        try:
            if not os.path.exists(path):
                return ImageQuality(0, 0, 0, (0, 0), 0, False, "File not found")

            img = cv2.imread(path)
            if img is None:
                return ImageQuality(0, 0, 0, (0, 0), 0, False, "Unreadable image")

            if img.shape[0] < 50 or img.shape[1] < 50:
                return ImageQuality(0, 0, 0, img.shape[:2][::-1], 0, False, "Image too small")

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            blur = cv2.Laplacian(gray, cv2.CV_64F).var()
            brightness = gray.mean()
            contrast = gray.std()
            h, w = gray.shape

            blur_s = min(100, blur / 10)
            bright_s = 100 - abs(brightness - 128) / 1.28
            cont_s = min(100, contrast * 2)
            res_s = min(100, (w * h) / 10000)

            score = (
                Config.BLUR_WEIGHT * blur_s
                + Config.BRIGHTNESS_WEIGHT * bright_s
                + Config.CONTRAST_WEIGHT * cont_s
                + Config.RESOLUTION_WEIGHT * res_s
           )

            return ImageQuality(
                round(blur_s, 1),
                round(brightness, 1),
                round(contrast, 1),
                (w, h),
                round(score, 1),
                True,
                None,
            )

        except Exception as e:
            logger.error("Quality analysis failed", exc_info=True)
            return ImageQuality(0, 0, 0, (0, 0), 0, False, str(e))


# =============================================================================
# Geometry
# =============================================================================

class Geometry:
    _mesh = None

    @classmethod
    def get_mesh(cls):
        if cls._mesh is None:
            cls._mesh = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=True,
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=Config.MIN_DETECTION_CONFIDENCE,
            )
        return cls._mesh

    @classmethod
    def cleanup(cls):
        if cls._mesh:
            cls._mesh.close()
            cls._mesh = None

    @staticmethod
    def extract(path: str) -> Optional[np.ndarray]:
        try:
            img = cv2.imread(path)
            if img is None:
                return None

            h, w, _ = img.shape
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            mesh = Geometry.get_mesh()
            res = _retry("mediapipe.mesh.process", lambda: mesh.process(rgb), tries=2)

            if not res.multi_face_landmarks:
                return None

            lm = res.multi_face_landmarks[0].landmark

            def p(i):
                return np.array([lm[i].x * w, lm[i].y * h])

            eye_dist = np.linalg.norm(p(33) - p(263))
            nose_mouth = np.linalg.norm(p(1) - p(13))
            ratio = eye_dist / (nose_mouth + 1e-6)

            xs = [p(i)[0] for i in range(468)]
            ys = [p(i)[1] for i in range(468)]
            wh = (max(xs) - min(xs)) / (max(ys) - min(ys) + 1e-6)

            symmetry = 1 - abs(np.mean(xs) - w / 2) / (w / 2)

            return np.array([eye_dist, ratio, wh, symmetry])

        except Exception:
            logger.error("Geometry extraction failed", exc_info=True)
            return None


def geometry_similarity(g1, g2) -> float:
    if g1 is None or g2 is None:
        return 50.0
    diff = np.abs(g1 - g2)
    sim = 100 - np.mean(diff / (np.abs(g1) + 1e-6)) * 100
    return float(np.clip(sim, 0, 100))


# =============================================================================
# InsightFace Engine
# =============================================================================

class InsightEngine:
    def __init__(self):
        logger.info("Initializing InsightFace engine")
        self.app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        # Optional: det_thresh can be tuned, but left unchanged here.
        _retry("insightface.prepare", lambda: self.app.prepare(ctx_id=0, 
        det_size=Config.DET_SIZE), tries=3)

    def embed(self, path: str):
        img = cv2.imread(path)
        if img is None:
            return None

        faces = _retry("insightface.get", lambda: self.app.get(img), tries=2)
        if not faces:
            return None
        return faces[0].embedding


# =============================================================================
# Verifier
# =============================================================================
def cosine_sim(a, b) -> float:
    if a is None or b is None:
        return 0.0
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))

class UltimateVerifier:

    def __init__(self):
        logger.info("ULTIMATE FACE VERIFICATION v6.2")
        self.engine = InsightEngine()

    def verify(self, img1: str, img2: str) -> VerificationResult:
        t0 = time.time()

        # ---------------------------------------------------------------------
        # Phase 2: Input validation (defensive only; algorithm unchanged)
        # ---------------------------------------------------------------------
        ok1, msg1 = validate_image_file(img1)
        ok2, msg2 = validate_image_file(img2)
        if not ok1 or not ok2:
            q1 = ImageQualityAnalyzer.analyze(img1)
            q2 = ImageQualityAnalyzer.analyze(img2)
            msg = f"Image invalid: img1={msg1}, img2={msg2}"
            return self._error(msg, t0, q1, q2)
        # ---------------------------------------------------------------------

        q1 = ImageQualityAnalyzer.analyze(img1)
        q2 = ImageQualityAnalyzer.analyze(img2)

        if not q1.valid or not q2.valid:
            return self._error("Quality failure", t0, q1, q2)

        e1 = self.engine.embed(img1)
        e2 = self.engine.embed(img2)
        if e1 is None or e2 is None:
            return self._error("Face not detected", t0, q1, q2)

        g1 = Geometry.extract(img1)
        g2 = Geometry.extract(img2)

        sim = cosine_sim(e1, e2)
        geo = geometry_similarity(g1, g2)
        quality = (q1.score + q2.score) / 2

        th = Config.BASE_THRESHOLD
        if quality < Config.LOW_QUALITY_THRESHOLD:
            th -= Config.QUALITY_ADJUSTMENT
        if geo > Config.HIGH_GEOMETRY_THRESHOLD:
            th += Config.GEOMETRY_ADJUSTMENT

        if sim > th + Config.HIGH_CONF_DELTA:
            verdict, conf = "SAME_HIGH", min(95, 70 + sim * 30)
        elif sim > th:
            verdict, conf = "SAME_MEDIUM", min(85, 60 + sim * 25)
        elif sim > th - Config.UNCERTAIN_DELTA:
            verdict, conf = "UNCERTAIN", 50
        else:
            verdict, conf = "DIFFERENT", min(90, 70 - sim * 40)

        return VerificationResult(
            verdict=verdict,
            confidence=round(conf, 1),
            similarity=sim,
            geometry_sim=geo,
            quality_avg=quality,
            execution_time=time.time() - t0,
            q1=q1,
            q2=q2,
            error=None,
        )

    def _error(self, msg, t0, q1, q2):
        return VerificationResult(
            verdict="ERROR",
            confidence=0,
            similarity=0,
            geometry_sim=0,
            quality_avg=0,
            execution_time=time.time() - t0,
            q1=q1,
            q2=q2,
            error=msg,
        )

    def __del__(self):
        try:
            Geometry.cleanup()
        except Exception:
            pass


# =============================================================================
# Output Formatting
# =============================================================================

def print_formatted(result: VerificationResult):
    print("\n" + "=" * 80)
    print("ULTIMATE FACE VERIFICATION v6.2 (ENHANCED STABLE)")
    print("=" * 80)

    if result.error:
        print(f"❌ ERROR: {result.error}")
    else:
        print(f"Image 1 Quality      : {result.q1.score}/100")
        print(f"Image 2 Quality      : {result.q2.score}/100")
        print(f"Embedding Similarity : {result.similarity:.3f}")
        print(f"Geometry Similarity  : {result.geometry_sim:.1f}%")
        print("-" * 80)
        print(f"VERDICT              : {result.verdict}")
        print(f"CONFIDENCE           : {result.confidence:.1f}%")

    print(f"TIME                 : {result.execution_time:.2f}s")
    print("=" * 80 + "\n")


def print_json(result: VerificationResult):
    output = {
        "verdict": result.verdict,
        "confidence": result.confidence,
        "similarity": round(result.similarity, 3),
        "geometry_similarity": round(result.geometry_sim, 1),
        "quality_average": round(result.quality_avg, 1),
        "execution_time": round(result.execution_time, 2),
        "image1_quality": result.q1.score,
        "image2_quality": result.q2.score,
        "error": result.error,
    }
    print(json.dumps(output, indent=2))


# =============================================================================
# Main
# =============================================================================

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 verify_v6.py img1 img2 [--json] [--quiet]")
        sys.exit(1)

    if "--json" in sys.argv:
        Config.JSON_OUTPUT = True
    if "--quiet" in sys.argv:
        Config.VERBOSE = False
        logger.setLevel(logging.WARNING)

    try:
        verifier = UltimateVerifier()
        result = verifier.verify(sys.argv[1], sys.argv[2])

        if Config.JSON_OUTPUT:
            print_json(result)
        elif Config.VERBOSE:
            print_formatted(result)
        else:
            print(f"{result.verdict} | {result.confidence:.1f}%")

        if result.error:
            sys.exit(1)
        elif result.verdict.startswith("SAME"):
            sys.exit(0)
        else:
            sys.exit(2)

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
