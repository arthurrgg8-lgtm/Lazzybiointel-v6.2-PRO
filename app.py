#!/usr/bin/env python3
"""
LazzyBioIntel v6.2 PRO
Enterprise Face Verification Dashboard (Streamlit UI)

Core verification logic is entirely in verify_v6.py (UltimateVerifier).
This UI only calls verifier.verify() and visualizes the result.
"""

import streamlit as st
import time
import tempfile
import os
import json
from verify_v6 import UltimateVerifier, VerificationResult

# =============================================================================
# Page Configuration
# =============================================================================

st.set_page_config(
    page_title="LazzyBioIntel v6.2 PRO",
    page_icon="🧠",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# =============================================================================
# Global CSS (Premium + Futuristic)
# =============================================================================

st.markdown(
    """
<style>
    .stApp {
        background: radial-gradient(circle at top, #020617 0%, #020617 40%, #020617 100%);
        color: #e5e7eb;
        font-family: -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
    }

    .lz-container {
        max-width: 950px;
        margin: 0 auto;
    }

    .lz-title {
        font-size: 2.8rem;
        font-weight: 800;
        text-align: center;
        letter-spacing: -0.04em;
        margin-bottom: 0.4rem;
        background: linear-gradient(135deg, #38bdf8, #6366f1, #a855f7);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }

    .lz-subtitle {
        text-align: center;
        color: #9ca3af;
        font-size: 1.02rem;
        margin-bottom: 0.4rem;
    }

    .lz-panel {
        background: rgba(15, 23, 42, 0.98);
        border-radius: 20px;
        padding: 1.9rem 1.7rem;
        border: 1px solid rgba(148, 163, 184, 0.4);
        box-shadow: 0 20px 45px rgba(0, 0, 0, 0.75);
        margin-bottom: 1.5rem;
    }

    .lz-panel-soft {
        background: rgba(15, 23, 42, 0.96);
        border-radius: 16px;
        padding: 1.5rem 1.5rem;
        border: 1px solid rgba(148, 163, 184, 0.25);
        margin-bottom: 1.1rem;
    }

    .lz-section-title {
        font-size: 1.15rem;
        font-weight: 600;
        margin-bottom: 0.7rem;
    }

    /* Glowing drag-and-drop cards */
    .lz-drop-card {
        border-radius: 18px;
        padding: 1.1rem 1rem;
        background: radial-gradient(circle at top left, #020617, #020617);
        border: 1px solid rgba(148, 163, 184, 0.55);
        box-shadow: 0 0 0 rgba(56, 189, 248, 0.0);
        transition: box-shadow 0.25s ease, border-color 0.25s ease, transform 0.15s ease;
    }

    .lz-drop-card:hover {
        border-color: rgba(56, 189, 248, 0.9);
        box-shadow: 0 0 28px rgba(56, 189, 248, 0.45);
        transform: translateY(-1px);
    }

    .lz-drop-label {
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #9ca3af;
        margin-bottom: 0.15rem;
    }

    .lz-drop-caption {
        font-size: 0.9rem;
        color: #e5e7eb;
        margin-bottom: 0.5rem;
    }

    .lz-metric {
        background: linear-gradient(145deg, #020617, #020617);
        border-radius: 16px;
        padding: 1rem 0.9rem;
        border: 1px solid rgba(148, 163, 184, 0.35);
        text-align: center;
    }

    .lz-metric-label {
        color: #9ca3af;
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }

    .lz-metric-value {
        font-size: 1.55rem;
        font-weight: 600;
        margin-top: 0.3rem;
    }

    .lz-verdict {
        margin-top: 1.5rem;
        padding: 1.1rem 1rem;
        border-radius: 18px;
        font-size: 1.5rem;
        font-weight: 700;
        text-align: center;
    }

    .lz-verdict-success {
        background: radial-gradient(circle at top left, #22c55e, #14532d);
        box-shadow: 0 0 34px rgba(34, 197, 94, 0.55);
    }

    .lz-verdict-warning {
        background: radial-gradient(circle at top left, #f97316, #78350f);
        box-shadow: 0 0 34px rgba(249, 115, 22, 0.55);
    }

    .lz-verdict-error {
        background: radial-gradient(circle at top left, #ef4444, #7f1d1d);
        box-shadow: 0 0 34px rgba(239, 68, 68, 0.55);
    }

    .lz-verdict-text {
        display: inline-block;
        margin-left: 0.45rem;
    }

    .lz-feed {
        font-family: SFMono-Regular, ui-monospace, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        font-size: 0.86rem;
        color: #e5e7eb;
        background: #020617;
        border-radius: 10px;
        padding: 0.75rem 0.9rem;
        border: 1px solid rgba(148, 163, 184, 0.35);
        min-height: 3rem;
    }

    .lz-footer {
        text-align: center;
        color: #6b7280;
        font-size: 0.8rem;
        margin-top: 1.6rem;
        padding-bottom: 0.8rem;
    }

    .stButton>button {
        width: 100%;
        border-radius: 999px;
        border: 1px solid rgba(56, 189, 248, 0.6);
        background: linear-gradient(135deg, #0ea5e9, #6366f1);
        color: white;
        font-weight: 600;
        padding: 0.7rem 0;
        box-shadow: 0 14px 30px rgba(37, 99, 235, 0.55);
    }

    .stButton>button:hover {
        border-color: #38bdf8;
        box-shadow: 0 16px 34px rgba(56, 189, 248, 0.65);
    }
</style>
""",
    unsafe_allow_html=True,
)

# =============================================================================
# Header
# =============================================================================

st.markdown('<div class="lz-container">', unsafe_allow_html=True)
st.markdown('<div class="lz-title">LazzyBioIntel v6.2 PRO</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="lz-subtitle">'
    'Reliable 1:1 face verification for real-world access control, onboarding and authentication.'
    '</div>',
    unsafe_allow_html=True,
)
st.caption("v6.2 · PRO · InsightFace buffalo_l · CPU-only · 1:1 face verification engine")

st.markdown(
    """
    <div style="display:flex; justify-content:center; gap:0.75rem; margin-bottom:1.7rem; flex-wrap:wrap;">
      <div style="
          display:flex; align-items:center; gap:0.4rem;
          padding:0.25rem 0.85rem;
          border-radius:999px;
          background:linear-gradient(135deg, rgba(56,189,248,0.16), rgba(37,99,235,0.12));
          border:1px solid rgba(56,189,248,0.8);
          box-shadow:0 0 18px rgba(56,189,248,0.55);
          font-size:0.8rem;
      ">
        <span>🎯</span>
        <span>High‑confidence decisions</span>
      </div>

      <div style="
          display:flex; align-items:center; gap:0.4rem;
          padding:0.25rem 0.85rem;
          border-radius:999px;
          background:linear-gradient(135deg, rgba(45,212,191,0.16), rgba(22,163,74,0.12));
          border:1px solid rgba(45,212,191,0.8);
          box-shadow:0 0 18px rgba(45,212,191,0.55);
          font-size:0.8rem;
      ">
        <span>🧮</span>
        <span>Quality & geometry aware</span>
      </div>

      <div style="
          display:flex; align-items:center; gap:0.4rem;
          padding:0.25rem 0.85rem;
          border-radius:999px;
          background:linear-gradient(135deg, rgba(244,114,182,0.18), rgba(139,92,246,0.14));
          border:1px solid rgba(244,114,182,0.9);
          box-shadow:0 0 18px rgba(244,114,182,0.6);
          font-size:0.8rem;
      ">
        <span>⚙️</span>
        <span>AI & Human MADE </span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# Upload Panel (Glowing drag & drop)
# =============================================================================

# =============================================================================
# Upload Panel (Scanner-style, non‑basic)
# =============================================================================

st.markdown('<div class="lz-panel">', unsafe_allow_html=True)
st.markdown('<div class="lz-section-title">Image input</div>', unsafe_allow_html=True)

st.markdown(
    """
    <div style="font-size:0.9rem; color:#9ca3af; margin-bottom:0.6rem;">
      Load two face images into the verification engine. Different captures of the same person give the most realistic result.
    </div>
    """,
    unsafe_allow_html=True,
)

left, right = st.columns(2)

with left:
    st.markdown(
        """
        <div style="margin-bottom:0.75rem;">
          <div style="font-size:0.8rem; text-transform:uppercase; letter-spacing:0.08em; color:#9ca3af;">
            REFERENCE
          </div>
          <div style="font-size:0.9rem; color:#e5e7eb;">Primary identity image</div>
        </div>
        <div style="
            border-radius:18px;
            padding:1rem 0.9rem;
            background: radial-gradient(circle at top left, #020617, #020617);
            border:1px solid rgba(56,189,248,0.7);
            box-shadow:0 0 24px rgba(56,189,248,0.4);
        ">
          <div style="display:flex; align-items:center; gap:0.7rem; margin-bottom:0.6rem;">
            <div style="
                width:32px; height:32px; border-radius:999px;
                background:radial-gradient(circle, #38bdf8, #0f172a);
                display:flex; align-items:center; justify-content:center;
                box-shadow:0 0 18px rgba(56,189,248,0.7);
                font-size:1.1rem;">
              📥
            </div>
            <div>
              <div style="font-size:0.9rem; color:#e5e7eb;">Drag & drop or browse</div>
              <div style="font-size:0.75rem; color:#9ca3af;">JPG · JPEG · PNG · up to 200 MB</div>
            </div>
          </div>
        """,
        unsafe_allow_html=True,
    )
    ref = st.file_uploader(
        "Drop or select reference image",
        type=["jpg", "jpeg", "png"],
        label_visibility="collapsed",
        key="ref_uploader",
    )
    st.markdown("</div>", unsafe_allow_html=True)

with right:
    st.markdown(
        """
        <div style="margin-bottom:0.75rem;">
          <div style="font-size:0.8rem; text-transform:uppercase; letter-spacing:0.08em; color:#9ca3af;">
            PROBE
          </div>
          <div style="font-size:0.9rem; color:#e5e7eb;">Image to verify against reference</div>
        </div>
        <div style="
            border-radius:18px;
            padding:1rem 0.9rem;
            background: radial-gradient(circle at top left, #020617, #020617);
            border:1px solid rgba(147,197,253,0.7);
            box-shadow:0 0 24px rgba(129,140,248,0.4);
        ">
          <div style="display:flex; align-items:center; gap:0.7rem; margin-bottom:0.6rem;">
            <div style="
                width:32px; height:32px; border-radius:999px;
                background:radial-gradient(circle, #6366f1, #0f172a);
                display:flex; align-items:center; justify-content:center;
                box-shadow:0 0 18px rgba(129,140,248,0.7);
                font-size:1.1rem;">
              📥
            </div>
            <div>
              <div style="font-size:0.9rem; color:#e5e7eb;">Drag & drop or browse</div>
              <div style="font-size:0.75rem; color:#9ca3af;">JPG · JPEG · PNG · up to 200 MB</div>
            </div>
          </div>
        """,
        unsafe_allow_html=True,
    )
    probe = st.file_uploader(
        "Drop or select probe image",
        type=["jpg", "jpeg", "png"],
        label_visibility="collapsed",
        key="probe_uploader",
    )
    st.markdown("</div>", unsafe_allow_html=True)

# Use ref/probe instead of img1/img2 below
img1, img2 = ref, probe

# Premium preview row (unchanged logic)
if img1 or img2:
    st.markdown(
        '<div style="margin-top:0.6rem; font-size:0.85rem; color:#9ca3af;">Preview</div>',
        unsafe_allow_html=True,
    )
    p1, p2 = st.columns(2)
    with p1:
        if img1:
            st.image(img1, caption="Reference", use_container_width=True)
        else:
            st.markdown(
                "<div style='border-radius:12px; border:1px dashed rgba(148,163,184,0.5); "
                "padding:1.6rem; text-align:center; font-size:0.8rem; color:#6b7280;'>"
                "Waiting for reference image…</div>",
                unsafe_allow_html=True,
            )
    with p2:
        if img2:
            st.image(img2, caption="Probe", use_container_width=True)
        else:
            st.markdown(
                "<div style='border-radius:12px; border:1px dashed rgba(148,163,184,0.5); "
                "padding:1.6rem; text-align:center; font-size:0.8rem; color:#6b7280;'>"
                "Waiting for probe image…</div>",
                unsafe_allow_html=True,
            )

st.markdown("</div>", unsafe_allow_html=True)

# =============================================================================
# Analysis Trigger
# =============================================================================

run_clicked = st.button("🔐 Verify identity now")

if run_clicked:
    if not img1 or not img2:
        st.error("Please provide both reference and probe images.")
    else:
        # Persist uploads to temporary files
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as f1, tempfile.NamedTemporaryFile(
            delete=False, suffix=".jpg"
        ) as f2:
            f1.write(img1.read())
            f2.write(img2.read())
            p1, p2 = f1.name, f2.name

        try:
            # Progress + feed
            st.markdown('<div class="lz-panel-soft">', unsafe_allow_html=True)
            st.markdown('<div class="lz-section-title">Analysis engine</div>', unsafe_allow_html=True)
            progress = st.progress(0)
            feed_placeholder = st.empty()

            def log(msg: str, pct: int):
                feed_placeholder.markdown(f'<div class="lz-feed">{msg}</div>', unsafe_allow_html=True)
                progress.progress(pct)
                time.sleep(0.25)

            log("Initializing verification engine…", 20)
            verifier = UltimateVerifier()  # core engine unchanged[file:43]

            log("Running full pipeline: quality, neural embeddings, geometry…", 65)
            result: VerificationResult = verifier.verify(p1, p2)  # unchanged[file:43]

            log("Finalizing decision and confidence metrics…", 100)
            st.markdown("</div>", unsafe_allow_html=True)

            # =============================================================================
            # Results Panel
            # =============================================================================

            st.markdown('<div class="lz-panel">', unsafe_allow_html=True)
            st.markdown("#### Trust indicators", unsafe_allow_html=True)

            mc1, mc2, mc3 = st.columns(3)
            with mc1:
                st.markdown(
                    f"""
                    <div class="lz-metric">
                        <div class="lz-metric-label">Neural match</div>
                        <div class="lz-metric-value">{result.similarity:.3f}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with mc2:
                st.markdown(
                    f"""
                    <div class="lz-metric">
                        <div class="lz-metric-label">Image quality (avg)</div>
                        <div class="lz-metric-value">{result.quality_avg:.1f}/100</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with mc3:
                st.markdown(
                    f"""
                    <div class="lz-metric">
                        <div class="lz-metric-label">Facial geometry</div>
                        <div class="lz-metric-value">{result.geometry_sim:.1f}%</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            # Verdict badge + explanation
            if result.error:
                v_class = "lz-verdict lz-verdict-error"
                v_icon = "⚠️"
                v_text = f"ERROR · {result.error}"
                explanation = "The engine could not complete a reliable verification. Check image quality or face visibility."
            elif result.verdict.startswith("SAME"):
                v_class = "lz-verdict lz-verdict-success"
                v_icon = "✅"
                v_text = "SAME PERSON CONFIRMED"
                explanation = (
                    "Neural similarity, image quality and facial geometry strongly support a same-person match."
                )
            elif result.verdict == "UNCERTAIN":
                v_class = "lz-verdict lz-verdict-warning"
                v_icon = "⚠️"
                v_text = "UNCERTAIN MATCH"
                explanation = (
                    "Signals are borderline or mixed. Re-capture both images in better lighting and verify again."
                )
            else:
                v_class = "lz-verdict lz-verdict-error"
                v_icon = "❌"
                v_text = "DIFFERENT PERSON"
                explanation = (
                    "Embeddings and geometry show clear differences, leading to a different-person decision."
                )

            st.markdown(
                f"""
                <div class="{v_class}">
                    {v_icon}<span class="lz-verdict-text">{v_text}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown(
                f"<p style='font-size:0.9rem; color:#e5e7eb; margin-top:0.45rem;'>{explanation}</p>",
                unsafe_allow_html=True,
            )

            kc1, kc2 = st.columns(2)
            kc1.metric("Confidence", f"{result.confidence:.1f} %")
            kc2.metric("Processing time", f"{result.execution_time:.2f} s")

            # Session analytics update (UI only)
            st.session_state.runs += 1
            st.session_state.times.append(result.execution_time)

            with st.expander("Where this engine fits"):
                st.markdown(
                    "- Secure workforce or admin login (1:1 verification)\n"
                    "- KYC / onboarding identity checks\n"
                    "- Access control for high-security areas\n"
                    "- Examination / remote proctoring identity verification\n"
                )

            with st.expander("How to get the most reliable verdicts"):
                st.markdown(
                    "- Use frontal faces with both eyes clearly visible.\n"
                    "- Avoid strong backlight, heavy shadows or very low resolution.\n"
                    "- Use different captures of the same person, not the same photo twice.\n"
                    "- For UNCERTAIN results, re-capture both images and verify again.\n"
                )

            with st.expander("Technical details"):
                qc1, qc2 = st.columns(2)
                with qc1:
                    st.write("**Image 1 quality**")
                    st.write(f"Score: {result.q1.score:.1f} / 100")
                    st.write(f"Resolution: {result.q1.resolution[0]} × {result.q1.resolution[1]}")
                with qc2:
                    st.write("**Image 2 quality**")
                    st.write(f"Score: {result.q2.score:.1f} / 100")
                    st.write(f"Resolution: {result.q2.resolution[0]} × {result.q2.resolution[1]}")

            with st.expander("Production JSON export (CLI identical)"):
                payload = {
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
                st.code(json.dumps(payload, indent=2), language="json")

            with st.expander("Session analytics"):
                if st.session_state.times:
                    total = st.session_state.runs
                    fastest = min(st.session_state.times)
                    slowest = max(st.session_state.times)
                    avg = sum(st.session_state.times) / len(st.session_state.times)
                    st.write(f"Total verifications this session: **{total}**")
                    st.write(
                        f"Fastest: **{fastest:.2f}s**, Slowest: **{slowest:.2f}s**, "
                        f"Average: **{avg:.2f}s**"
                    )

            st.success("Ready for the next pair. Upload new images to verify another identity.")
            st.markdown("</div>", unsafe_allow_html=True)

        finally:
            try:
                os.unlink(p1)
                os.unlink(p2)
            except Exception:
                pass

# =============================================================================
# Footer
# =============================================================================

st.markdown(
    """
<div class="lz-footer">
  LazzyBioIntel v6.2 PRO · Nepal · Streamlit interface using the same verification core as the CLI engine.
</div>
</div>
""",
    unsafe_allow_html=True,
)
