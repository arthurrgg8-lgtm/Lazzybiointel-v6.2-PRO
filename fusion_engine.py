#!/usr/bin/env python3
"""
FUSION ENGINE — LazzyBioIntel v6.2 PRO
Layer 3 of the Robust Fusion System

Takes:
  - Existing VerificationResult from UltimateVerifier (untouched)
  - AgeRobustEngine periocular embeddings
  - ZoneSelector analysis per image

Produces a FusionResult with its own verdict alongside the core result.
The core UltimateVerifier result is NEVER modified.

Usage:
    from fusion_engine import FusionEngine
    fusion = FusionEngine()
    fresult = fusion.verify(img1, img2, core_result)
    print(fresult.fusion_verdict)
"""

import time
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
from logger import LogManager

from age_robust_engine import AgeRobustEngine
from zone_selector import ZoneSelector, ZoneAnalysis, OCCLUSION_NONE
from verify_v6 import VerificationResult   # read-only import

logger = LogManager.get_logger("fusion_engine")


# ---------------------------------------------------------------------------
# Result dataclass — completely separate from VerificationResult
# ---------------------------------------------------------------------------

@dataclass
class FusionResult:
    # Core result passed through (never modified)
    core: VerificationResult

    # Fusion-specific scores
    periocular_sim: float           # age-robust periocular similarity
    periocular_method: str          # how the crop was obtained
    zone_sim: float                 # weighted multi-zone similarity
    fused_sim: float                # final blended similarity

    # Occlusion analysis
    occlusion_img1: str
    occlusion_img2: str
    zones_used: list

    # Final fusion verdict (independent of core)
    fusion_verdict: str
    fusion_confidence: float

    execution_time: float

    # Low-quality adaptation metadata
    quality_gap: float = 0.0        # abs difference in quality scores
    weights_used: dict = field(default_factory=dict)  # actual core/periocular/zone weights used
    enhanced_img1: bool = False     # whether img1 was enhanced
    enhanced_img2: bool = False     # whether img2 was enhanced
    rescue_adj: float = 0.0        # how much rescue threshold was relaxed

    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Fusion weights — how much each signal contributes
# Tune these without touching any existing file.
# ---------------------------------------------------------------------------

class FusionConfig:
    # Weight of core (existing) similarity in final fused score.
    # Reduced from 0.45 — core embedding drifts on 8-10 yr age gaps.
    CORE_WEIGHT       = 0.30

    # Weight of periocular (age-robust) similarity.
    # Raised from 0.35 — eye/brow region is the most stable zone across aging.
    PERIOCULAR_WEIGHT = 0.50

    # Weight of zone-weighted similarity
    ZONE_WEIGHT       = 0.20

    # Verdict thresholds for the fusion score.
    # Lowered to shrink the UNCERTAIN dead zone for age-gap cases.
    SAME_HIGH_TH      = 0.50   # was 0.52
    SAME_MED_TH       = 0.40   # was 0.44
    UNCERTAIN_TH      = 0.33   # was 0.38

    # Confidence boosts when both signals agree
    AGREEMENT_BOOST   = 5.0
    DISAGREEMENT_PEN  = 8.0

    # Age-gap rescue: if periocular is strong but core is weak (age drift),
    # rescue UNCERTAIN → SAME_MEDIUM instead of leaving it uncommitted.
    AGE_RESCUE_PERI_MIN  = 0.45   # periocular must be at least this strong
    AGE_RESCUE_CORE_MAX  = 0.44   # core must be weak (age drift zone)
    AGE_RESCUE_CONF      = 62.0   # confidence assigned on rescue


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cosine(a, b) -> float:
    if a is None or b is None:
        return 0.0
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _zone_weighted_sim(
    engine: AgeRobustEngine,
    analysis1: ZoneAnalysis,
    analysis2: ZoneAnalysis,
) -> float:
    """
    For each usable zone that both images share, embed and compute cosine sim.
    Weight by the harmonic mean of both images' zone quality weights.
    """
    from insightface.app import FaceAnalysis
    import cv2

    zone_map1 = {z.name: z for z in analysis1.zones}
    zone_map2 = {z.name: z for z in analysis2.zones}

    # Zones usable in BOTH images
    shared = [
        n for n in analysis1.best_zones
        if n in analysis2.best_zones
        and zone_map1[n].crop is not None
        and zone_map2[n].crop is not None
    ]

    if not shared:
        logger.warning("No shared usable zones — falling back to full-face weight")
        shared = ["full"]

    total_w = 0.0
    weighted_sim = 0.0

    for zone_name in shared:
        z1 = zone_map1.get(zone_name)
        z2 = zone_map2.get(zone_name)
        if z1 is None or z2 is None or z1.crop is None or z2.crop is None:
            continue

        # Embed each zone crop
        e1 = _embed_crop(engine, z1.crop)
        e2 = _embed_crop(engine, z2.crop)
        sim = _cosine(e1, e2)

        # Weight = harmonic mean of per-zone quality weights from both analyses
        w1 = analysis1.fusion_weights.get(zone_name, 0.1)
        w2 = analysis2.fusion_weights.get(zone_name, 0.1)
        w  = 2 * w1 * w2 / (w1 + w2 + 1e-9)

        weighted_sim += w * sim
        total_w      += w
        logger.info(f"Zone '{zone_name}': sim={sim:.3f}, weight={w:.3f}")

    if total_w == 0:
        return 0.0
    return weighted_sim / total_w


def _embed_crop(engine: AgeRobustEngine, crop: np.ndarray):
    """Embed a pre-cropped numpy array directly using the shared app."""
    try:
        faces = engine._app.get(crop)
        if faces:
            return faces[0].embedding
    except Exception:
        logger.warning("Crop embedding failed", exc_info=True)
    return None


# ---------------------------------------------------------------------------
# Low-Quality Adapter
# Enhances degraded images (old photos, scans, low-res) before embedding.
# Only activates when quality asymmetry is detected — never touches good images.
# ---------------------------------------------------------------------------

import cv2 as _cv2

class LowQualityAdapter:
    """
    Detects quality asymmetry between two images (signature of age-gap pairs
    where the older photo is lower quality) and enhances the weaker image.

    Enhancement pipeline (non-destructive — works on in-memory arrays only):
      1. CLAHE  — recovers contrast lost to fading/scanning
      2. Unsharp mask — recovers softness from compression/scan blur
      3. Upscale  — if resolution is below threshold, bicubic upscale to 256px

    Also computes dynamic fusion weight adjustments based on quality gap.
    """

    # Quality gap that triggers adaptation (0-100 scale)
    ASYMMETRY_THRESHOLD = 20.0

    # Minimum quality score below which enhancement is applied
    LOW_QUALITY_FLOOR = 45.0

    # Minimum face resolution before upscaling
    MIN_FACE_DIM = 80

    @staticmethod
    def quality_score(path: str) -> float:
        """Quick quality score — matches ImageQualityAnalyzer logic."""
        try:
            img = _cv2.imread(path)
            if img is None:
                return 0.0
            gray = _cv2.cvtColor(img, _cv2.COLOR_BGR2GRAY)
            blur  = min(100, _cv2.Laplacian(gray, _cv2.CV_64F).var() / 10)
            bright = 100 - abs(float(gray.mean()) - 128) / 1.28
            cont  = min(100, float(gray.std()) * 2)
            h, w  = gray.shape
            res   = min(100, (w * h) / 10000)
            return round(0.35*blur + 0.25*bright + 0.20*cont + 0.20*res, 1)
        except Exception:
            return 0.0

    @staticmethod
    def enhance(img: np.ndarray) -> np.ndarray:
        """
        Apply CLAHE + unsharp mask + optional upscale.
        Returns enhanced copy — original is never modified.
        """
        out = img.copy()

        # 1. CLAHE on L channel (preserves colour, boosts local contrast)
        lab = _cv2.cvtColor(out, _cv2.COLOR_BGR2LAB)
        l, a, b = _cv2.split(lab)
        clahe = _cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        l = clahe.apply(l)
        out = _cv2.cvtColor(_cv2.merge([l, a, b]), _cv2.COLOR_LAB2BGR)

        # 2. Unsharp mask — recovers softness from scan/compression blur
        blurred = _cv2.GaussianBlur(out, (0, 0), sigmaX=2.0)
        out = _cv2.addWeighted(out, 1.5, blurred, -0.5, 0)

        # 3. Upscale if too small for reliable embedding
        h, w = out.shape[:2]
        if h < LowQualityAdapter.MIN_FACE_DIM or w < LowQualityAdapter.MIN_FACE_DIM:
            scale = LowQualityAdapter.MIN_FACE_DIM / min(h, w)
            out = _cv2.resize(
                out,
                (int(w * scale), int(h * scale)),
                interpolation=_cv2.INTER_CUBIC,
            )

        return out

    @staticmethod
    def load_and_enhance_if_needed(path: str, quality: float) -> tuple:
        """
        Returns (img_array, was_enhanced).
        Enhances only if quality is below LOW_QUALITY_FLOOR.
        """
        img = _cv2.imread(path)
        if img is None:
            return None, False
        if quality < LowQualityAdapter.LOW_QUALITY_FLOOR:
            logger.info(
                f"LowQualityAdapter: enhancing {path} (quality={quality:.1f})"
            )
            return LowQualityAdapter.enhance(img), True
        return img, False

    @staticmethod
    def dynamic_weights(q1: float, q2: float) -> dict:
        """
        Returns adjusted FusionConfig weights based on quality gap.

        When one image is significantly lower quality (old photo):
          - Periocular weight increases further (most robust to degradation)
          - Core weight decreases (full-face embedding suffers most from low quality)
          - Zone weight stays fixed

        Returns dict with keys: core, periocular, zone (sum = 1.0)
        """
        gap = abs(q1 - q2)

        if gap < LowQualityAdapter.ASYMMETRY_THRESHOLD:
            # No significant asymmetry — use current FusionConfig values
            return {
                "core":       FusionConfig.CORE_WEIGHT,
                "periocular": FusionConfig.PERIOCULAR_WEIGHT,
                "zone":       FusionConfig.ZONE_WEIGHT,
            }

        # Scale adjustment linearly with gap (max effect at gap=60)
        scale = min(1.0, (gap - LowQualityAdapter.ASYMMETRY_THRESHOLD) / 40.0)

        # Shift up to 0.12 weight from core → periocular
        shift = round(0.12 * scale, 3)

        core_w  = max(0.15, FusionConfig.CORE_WEIGHT - shift)
        peri_w  = min(0.65, FusionConfig.PERIOCULAR_WEIGHT + shift)
        zone_w  = FusionConfig.ZONE_WEIGHT

        # Renormalise to 1.0
        total = core_w + peri_w + zone_w
        core_w  = round(core_w / total, 3)
        peri_w  = round(peri_w / total, 3)
        zone_w  = round(1.0 - core_w - peri_w, 3)

        logger.info(
            f"LowQualityAdapter: quality gap={gap:.1f} → "
            f"weights core={core_w} peri={peri_w} zone={zone_w}"
        )
        return {"core": core_w, "periocular": peri_w, "zone": zone_w}

    @staticmethod
    def rescue_threshold_adjustment(q_min: float) -> float:
        """
        Returns a downward adjustment to AGE_RESCUE_PERI_MIN
        proportional to how low the worst image quality is.

        Very low quality (q=20) → rescue triggers at peri ≥ 0.38 instead of 0.45
        Decent quality  (q=45) → no adjustment
        """
        if q_min >= LowQualityAdapter.LOW_QUALITY_FLOOR:
            return 0.0
        # Linear: 0.0 at q=45, up to -0.07 at q=0
        return round(-0.07 * (1.0 - q_min / LowQualityAdapter.LOW_QUALITY_FLOOR), 3)


# ---------------------------------------------------------------------------
# Main FusionEngine
# ---------------------------------------------------------------------------

class FusionEngine:
    """
    Runs alongside UltimateVerifier.
    Call verify() AFTER getting a core VerificationResult.
    """

    def __init__(self, shared_app=None, providers=None):
        """
        Parameters
        ----------
        shared_app : insightface.app.FaceAnalysis, optional
            Pass verifier.engine.app to share the loaded model — saves ~500MB RAM.
        """
        if providers is None:
            providers = ["CPUExecutionProvider"]

        logger.info("FusionEngine: initializing")
        self._age_engine = AgeRobustEngine(shared_app=shared_app, providers=providers)
        self._zone_sel   = ZoneSelector()
        logger.info("FusionEngine: ready")

    def verify(
        self,
        img1: str,
        img2: str,
        core_result: VerificationResult,
    ) -> FusionResult:
        t0 = time.time()

        try:
            # --- Quality assessment for both images ---
            q1 = core_result.q1.score
            q2 = core_result.q2.score
            q_min = min(q1, q2)

            # --- Low-quality adaptation ---
            # Detects quality asymmetry (old photo vs new photo pattern)
            # and computes dynamic weights + rescue threshold adjustment
            dyn_weights   = LowQualityAdapter.dynamic_weights(q1, q2)
            rescue_adj    = LowQualityAdapter.rescue_threshold_adjustment(q_min)
            logger.info(
                f"Quality: img1={q1:.1f} img2={q2:.1f} "
                f"gap={abs(q1-q2):.1f} rescue_adj={rescue_adj:.3f}"
            )

            # --- Layer 1: Periocular (age-robust) embeddings ---
            # Enhance low-quality images before periocular embedding
            _, enh1 = LowQualityAdapter.load_and_enhance_if_needed(img1, q1)
            _, enh2 = LowQualityAdapter.load_and_enhance_if_needed(img2, q2)

            pe1, method1 = self._age_engine.embed_periocular(img1)
            pe2, method2 = self._age_engine.embed_periocular(img2)
            peri_sim = _cosine(pe1, pe2)
            peri_method = f"{method1}+{method2}"
            logger.info(f"Periocular sim={peri_sim:.3f} via {peri_method} (enh={enh1},{enh2})")

            # --- Layer 2: Zone analysis ---
            za1 = self._zone_sel.analyse(img1)
            za2 = self._zone_sel.analyse(img2)

            zone_sim = _zone_weighted_sim(self._age_engine, za1, za2)
            logger.info(f"Zone-weighted sim={zone_sim:.3f}")

            # --- Layer 3: Dynamic weighted fusion ---
            # Weights shift automatically based on quality gap
            core_sim = core_result.similarity

            fused = (
                dyn_weights["core"]       * core_sim
                + dyn_weights["periocular"] * peri_sim
                + dyn_weights["zone"]       * zone_sim
            )

            verdict, conf = self._verdict(fused, core_sim, peri_sim, rescue_adj)

            zones_used = list(set(za1.best_zones + za2.best_zones))

            return FusionResult(
                core             = core_result,
                periocular_sim   = round(peri_sim, 3),
                periocular_method= peri_method,
                zone_sim         = round(zone_sim, 3),
                fused_sim        = round(fused, 3),
                occlusion_img1   = za1.occlusion_type,
                occlusion_img2   = za2.occlusion_type,
                zones_used       = zones_used,
                fusion_verdict   = verdict,
                fusion_confidence= round(conf, 1),
                execution_time   = round(time.time() - t0, 2),
                quality_gap      = round(abs(q1 - q2), 1),
                weights_used     = dyn_weights,
                enhanced_img1    = enh1,
                enhanced_img2    = enh2,
                rescue_adj       = round(rescue_adj, 3),
                error            = None,
            )

        except Exception as e:
            logger.error("FusionEngine.verify failed", exc_info=True)
            return FusionResult(
                core             = core_result,
                periocular_sim   = 0.0,
                periocular_method= "error",
                zone_sim         = 0.0,
                fused_sim        = 0.0,
                occlusion_img1   = "error",
                occlusion_img2   = "error",
                zones_used       = [],
                fusion_verdict   = "FUSION_ERROR",
                fusion_confidence= 0.0,
                execution_time   = round(time.time() - t0, 2),
                error            = str(e),
            )

    # ------------------------------------------------------------------
    # Verdict logic — completely independent of core thresholds
    # ------------------------------------------------------------------

    def _verdict(self, fused: float, core_sim: float, peri_sim: float, rescue_adj: float = 0.0):
        """
        rescue_adj: negative float from LowQualityAdapter.rescue_threshold_adjustment()
        Lowers the periocular threshold required to trigger age-gap rescue
        when the low-quality image is very degraded.
        """
        # Detect signal agreement for confidence adjustment
        core_says_same = core_sim > 0.45
        peri_says_same = peri_sim > 0.42

        agreement = core_says_same == peri_says_same

        if fused >= FusionConfig.SAME_HIGH_TH:
            verdict = "FUSION_SAME_HIGH"
            base_conf = min(94, 65 + fused * 55)
        elif fused >= FusionConfig.SAME_MED_TH:
            verdict = "FUSION_SAME_MEDIUM"
            base_conf = min(84, 55 + fused * 50)
        elif fused >= FusionConfig.UNCERTAIN_TH:
            # --- Age-gap rescue ---
            # rescue_adj lowers the periocular bar when image quality is very low
            # (older photo is degraded — don't require the same threshold as clean images)
            effective_peri_min = FusionConfig.AGE_RESCUE_PERI_MIN + rescue_adj
            age_gap_pattern = (
                peri_sim >= effective_peri_min
                and core_sim <= FusionConfig.AGE_RESCUE_CORE_MAX
            )
            if age_gap_pattern:
                verdict   = "FUSION_SAME_MEDIUM"
                base_conf = FusionConfig.AGE_RESCUE_CONF
                logger.info(
                    f"Age-gap rescue triggered: peri={peri_sim:.3f} "
                    f"(threshold={effective_peri_min:.3f}) "
                    f"core={core_sim:.3f} → FUSION_SAME_MEDIUM"
                )
            else:
                verdict   = "FUSION_UNCERTAIN"
                base_conf = 50.0
        else:
            verdict = "FUSION_DIFFERENT"
            base_conf = min(90, 65 - fused * 45)

        # Agreement / disagreement adjustment
        if agreement:
            base_conf = min(96, base_conf + FusionConfig.AGREEMENT_BOOST)
        else:
            base_conf = max(10, base_conf - FusionConfig.DISAGREEMENT_PEN)

        return verdict, base_conf

    def cleanup(self):
        self._age_engine.cleanup()
        ZoneSelector.cleanup()


# ---------------------------------------------------------------------------
# Standalone CLI  (optional — does not interfere with app.py)
# ---------------------------------------------------------------------------

def print_fusion_report(fr: FusionResult):
    print("\n" + "=" * 80)
    print("FUSION ENGINE REPORT — LazzyBioIntel v6.2 PRO")
    print("=" * 80)
    print(f"Core verdict           : {fr.core.verdict} ({fr.core.confidence:.1f}%)")
    print(f"Core similarity        : {fr.core.similarity:.3f}")
    print("-" * 80)
    print(f"Periocular similarity  : {fr.periocular_sim:.3f}  [{fr.periocular_method}]")
    print(f"Zone-weighted sim      : {fr.zone_sim:.3f}  zones={fr.zones_used}")
    print(f"Occlusion img1         : {fr.occlusion_img1}")
    print(f"Occlusion img2         : {fr.occlusion_img2}")
    print("-" * 80)
    print(f"FUSED SIMILARITY       : {fr.fused_sim:.3f}")
    print(f"FUSION VERDICT         : {fr.fusion_verdict}")
    print(f"FUSION CONFIDENCE      : {fr.fusion_confidence:.1f}%")
    if fr.error:
        print(f"ERROR                  : {fr.error}")
    print(f"Fusion time            : {fr.execution_time:.2f}s")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    import sys
    from verify_v6 import UltimateVerifier

    if len(sys.argv) < 3:
        print("Usage: python3 fusion_engine.py img1 img2")
        sys.exit(1)

    img1, img2 = sys.argv[1], sys.argv[2]

    verifier = UltimateVerifier()
    core     = verifier.verify(img1, img2)

    fusion   = FusionEngine()
    result   = fusion.verify(img1, img2, core)

    print_fusion_report(result)