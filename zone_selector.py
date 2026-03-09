#!/usr/bin/env python3
"""
ZONE SELECTOR — LazzyBioIntel v6.2 PRO
Layer 2 of the Robust Fusion System

Strategy:
  Computes quality scores for 4 facial zones independently:
    - FULL       : entire face
    - UPPER      : forehead + eyes + nose bridge (resistant to mask)
    - PERIOCULAR : eye + brow region only (resistant to sunglasses? no — see logic)
    - LOWER      : nose + mouth + chin (resistant to sunglasses/hat)

  Then classifies the likely occlusion type and returns a priority-ordered
  list of usable zones with their quality weights.

  Does NOT touch UltimateVerifier or any existing file.
"""

import cv2
import numpy as np
import mediapipe as mp
from dataclasses import dataclass
from typing import List, Tuple, Optional
from logger import LogManager

logger = LogManager.get_logger("zone_selector")

# ---------------------------------------------------------------------------
# Occlusion Types
# ---------------------------------------------------------------------------
OCCLUSION_NONE         = "none"
OCCLUSION_SUNGLASSES   = "sunglasses"
OCCLUSION_MASK         = "mask_covering"
OCCLUSION_HAT          = "hat_forehead"
OCCLUSION_UNKNOWN      = "unknown"


@dataclass
class ZoneResult:
    name: str               # "full" | "upper" | "periocular" | "lower"
    usable: bool
    quality: float          # 0–100
    occlusion_detected: bool
    crop: Optional[np.ndarray]  # actual pixel crop for embedding


@dataclass
class ZoneAnalysis:
    zones: List[ZoneResult]
    occlusion_type: str
    best_zones: List[str]           # ordered list of zone names to use
    fusion_weights: dict            # zone_name → float weight (sum = 1.0)


# ---------------------------------------------------------------------------
# Landmark index groups (MediaPipe 468-point)
# ---------------------------------------------------------------------------
_EYE_INDICES     = list(range(33, 42)) + list(range(362, 371))
_NOSE_INDICES    = [1, 2, 3, 4, 5, 6, 168, 197, 195, 5]
_MOUTH_INDICES   = list(range(61, 88))
_FOREHEAD_Y_FRAC = 0.20   # top 20% of face bbox = forehead


class ZoneSelector:
    """
    Analyses both images and decides which facial zones are clean enough
    to contribute to a robust fusion score.
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse(self, path: str) -> ZoneAnalysis:
        img = cv2.imread(path)
        if img is None:
            return self._fallback_analysis()

        h, w = img.shape[:2]
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        landmarks = self._get_landmarks(rgb, w, h)

        zones = []
        zones.append(self._zone_full(img))
        zones.append(self._zone_upper(img, h, landmarks))
        zones.append(self._zone_periocular(img, w, h, landmarks))
        zones.append(self._zone_lower(img, h, landmarks))

        occlusion = self._detect_occlusion(img, landmarks, w, h)
        best, weights = self._rank_zones(zones, occlusion)

        return ZoneAnalysis(
            zones=zones,
            occlusion_type=occlusion,
            best_zones=best,
            fusion_weights=weights,
        )

    # ------------------------------------------------------------------
    # Zone extractors
    # ------------------------------------------------------------------

    def _zone_full(self, img: np.ndarray) -> ZoneResult:
        q = self._quality(img)
        return ZoneResult("full", q >= 20, q, False, img)

    def _zone_upper(self, img: np.ndarray, h: int, lm) -> ZoneResult:
        y1 = int(h * 0.58)
        crop = img[0:y1, :]
        q = self._quality(crop)
        return ZoneResult("upper", q >= 15, q, False, crop)

    def _zone_periocular(self, img: np.ndarray, w: int, h: int, lm) -> ZoneResult:
        if lm is None:
            # Rough fixed band: 20%–48% height
            y0, y1 = int(h * 0.20), int(h * 0.48)
            crop = img[y0:y1, :]
            q = self._quality(crop)
            return ZoneResult("periocular", q >= 15, q, False, crop)

        eye_idx = _EYE_INDICES
        xs = [lm[i].x * w for i in eye_idx if i < len(lm)]
        ys = [lm[i].y * h for i in eye_idx if i < len(lm)]
        if not xs:
            return ZoneResult("periocular", False, 0, True, None)

        pad_x = int((max(xs) - min(xs)) * 0.5)
        pad_y = int((max(ys) - min(ys)) * 0.8)
        x0 = max(0, int(min(xs)) - pad_x)
        x1 = min(w, int(max(xs)) + pad_x)
        y0 = max(0, int(min(ys)) - pad_y)
        y1 = min(h, int(max(ys)) + pad_y)

        crop = img[y0:y1, x0:x1]
        q = self._quality(crop)

        # Detect sunglasses: darkness + low edge variance in eye zone
        occluded = self._detect_sunglasses_in_crop(crop)
        return ZoneResult("periocular", q >= 15 and not occluded, q, occluded, crop)

    def _zone_lower(self, img: np.ndarray, h: int, lm) -> ZoneResult:
        if lm is None:
            y0 = int(h * 0.52)
            crop = img[y0:, :]
            q = self._quality(crop)
            return ZoneResult("lower", q >= 15, q, False, crop)

        mouth_idx = _MOUTH_INDICES
        ys = [lm[i].y * h for i in mouth_idx if i < len(lm)]
        if not ys:
            y0 = int(h * 0.52)
        else:
            y0 = max(0, int(min(ys)) - int(h * 0.10))

        crop = img[y0:, :]
        q = self._quality(crop)

        # Detect mask: large uniform region over lower face
        occluded = self._detect_mask_in_crop(crop)
        return ZoneResult("lower", q >= 15 and not occluded, q, occluded, crop)

    # ------------------------------------------------------------------
    # Occlusion classifier
    # ------------------------------------------------------------------

    def _detect_occlusion(self, img, lm, w: int, h: int) -> str:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Check eye region brightness/variance → sunglasses
        eye_band = gray[int(h*0.20):int(h*0.45), :]
        eye_var  = float(eye_band.var())

        # Check lower face region variance → mask
        lower_band = gray[int(h*0.55):int(h*0.80), :]
        lower_var  = float(lower_band.var())

        # Heuristic thresholds (tuned empirically)
        if eye_var < 180 and lower_var > 300:
            return OCCLUSION_SUNGLASSES
        if lower_var < 150 and eye_var > 250:
            return OCCLUSION_MASK
        if eye_var < 120 and lower_var < 120:
            return OCCLUSION_UNKNOWN

        return OCCLUSION_NONE

    def _detect_sunglasses_in_crop(self, crop: np.ndarray) -> bool:
        if crop is None or crop.size == 0:
            return False
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        return float(gray.var()) < 160   # very low variance = uniform dark lens

    def _detect_mask_in_crop(self, crop: np.ndarray) -> bool:
        if crop is None or crop.size == 0:
            return False
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        return float(gray.var()) < 130   # very low variance = uniform mask surface

    # ------------------------------------------------------------------
    # Zone ranker — decides weights based on what's clean
    # ------------------------------------------------------------------

    def _rank_zones(
        self, zones: List[ZoneResult], occlusion: str
    ) -> Tuple[List[str], dict]:

        zone_map = {z.name: z for z in zones}

        if occlusion == OCCLUSION_SUNGLASSES:
            # Eyes hidden → rely on lower face + full face
            priority = ["lower", "full", "upper"]
        elif occlusion == OCCLUSION_MASK:
            # Lower face hidden → rely on periocular + upper
            priority = ["periocular", "upper", "full"]
        else:
            # Default: full face first, periocular for age robustness
            priority = ["full", "periocular", "upper", "lower"]

        usable = [n for n in priority if zone_map.get(n, ZoneResult(n, False, 0, False, None)).usable]

        if not usable:
            usable = ["full"]   # always have a fallback

        # Weight proportional to quality score
        total_q = sum(zone_map[n].quality for n in usable if n in zone_map)
        if total_q == 0:
            weights = {n: 1.0 / len(usable) for n in usable}
        else:
            weights = {
                n: zone_map[n].quality / total_q
                for n in usable if n in zone_map
            }

        logger.info(
            f"ZoneSelector: occlusion={occlusion}, usable={usable}, weights={weights}"
        )
        return usable, weights

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_landmarks(self, rgb, w, h):
        try:
            mesh = ZoneSelector._get_mesh()
            res = mesh.process(rgb)
            if res.multi_face_landmarks:
                return res.multi_face_landmarks[0].landmark
        except Exception:
            pass
        return None

    @staticmethod
    def _quality(img: np.ndarray) -> float:
        if img is None or img.size == 0:
            return 0.0
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            blur  = min(100, cv2.Laplacian(gray, cv2.CV_64F).var() / 10)
            bright = 100 - abs(float(gray.mean()) - 128) / 1.28
            cont  = min(100, float(gray.std()) * 2)
            h, w  = gray.shape
            res   = min(100, (w * h) / 5000)
            return round(0.35*blur + 0.25*bright + 0.20*cont + 0.20*res, 1)
        except Exception:
            return 0.0

    def _fallback_analysis(self) -> ZoneAnalysis:
        dummy = ZoneResult("full", False, 0, False, None)
        return ZoneAnalysis([dummy], OCCLUSION_UNKNOWN, ["full"], {"full": 1.0})
