#!/usr/bin/env python3
import sys
import time
from occlusion_engine import OcclusionEngine, cosine_sim
from verify_v6 import UltimateVerifier

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 verify_forensic.py img1 img2")
        sys.exit(1)

    img1, img2 = sys.argv[1], sys.argv[2]

    # 1) Normal full‑face verification (your existing core)
    verifier = UltimateVerifier()
    core_result = verifier.verify(img1, img2)

    # 2) Occlusion‑focused upper‑face verification
    occ_engine = OcclusionEngine()
    t0 = time.time()
    e1 = occ_engine.embed_upper_face(img1)
    e2 = occ_engine.embed_upper_face(img2)
    occ_sim = cosine_sim(e1, e2)
    occ_time = time.time() - t0

    print("\n================= FORENSIC COMBINED REPORT =================")
    print(f"Core similarity        : {core_result.similarity:.3f}")
    print(f"Core verdict           : {core_result.verdict}")
    print(f"Core confidence        : {core_result.confidence:.1f}%")
    print(f"Upper‑face similarity  : {occ_sim:.3f}")
    print(f"Upper‑face time        : {occ_time:.2f}s")
    print("------------------------------------------------------------")

    # Simple rigid combination rules
    if core_result.verdict.startswith("SAME") and occ_sim >= 0.55:
        combined = "STRONG_SUPPORT_SAME"
    elif core_result.verdict == "UNCERTAIN" and occ_sim >= 0.55:
        combined = "LIKELY_SAME_NEEDS_REVIEW"
    elif core_result.verdict == "DIFFERENT" and occ_sim < 0.40:
        combined = "STRONG_SUPPORT_DIFFERENT"
    else:
        combined = "INCONCLUSIVE_FORENSIC"

    print(f"COMBINED FORENSIC LABEL: {combined}")
    print("============================================================\n")

if __name__ == "__main__":
    main()
