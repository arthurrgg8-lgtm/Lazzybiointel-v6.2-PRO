#!/usr/bin/env python3
"""
LazzyBioIntel v6.2 PRO
Enterprise Face Verification Dashboard (Streamlit UI)

Core verification logic is in verify_v6.py (UltimateVerifier v6.2+).
This UI calls verifier.verify() and visualizes the result only.
"""

import streamlit as st
import time
import tempfile
import os
import json
from typing import Optional

import recovery
recovery.restore_session_state()
recovery.cleanup_old_sessions()

from verify_v6 import UltimateVerifier, VerificationResult
from occlusion_engine import OcclusionEngine, cosine_sim
@st.cache_resource
def get_verifier():
    return UltimateVerifier()

@st.cache_resource
def get_occlusion_engine():
    return OcclusionEngine()

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
# Session state
# =============================================================================
if "runs" not in st.session_state:
    st.session_state.runs = 0
if "times" not in st.session_state:
    st.session_state.times = []

# =============================================================================
# Styles
# =============================================================================
st.markdown(
    """
<style>
.stApp{
  background: radial-gradient(circle at top, #020617 0%, #020617 40%, #020617 100%);
  color: #e5e7eb;
  font-family: -apple-system,BlinkMacSystemFont,system-ui,sans-serif;
}
.lz-container{max-width:950px;margin:0 auto;}
.lz-title{
  font-size:2.8rem;font-weight:800;text-align:center;letter-spacing:-0.04em;margin-bottom:0.4rem;
  background: linear-gradient(135deg,#38bdf8,#6366f1,#a855f7);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
}
.lz-subtitle{text-align:center;color:#9ca3af;font-size:1.02rem;margin-bottom:0.4rem;}
.lz-panel{
  background: rgba(15,23,42,0.98); border-radius:20px; padding:1.9rem 1.7rem;
  border: 1px solid rgba(148,163,184,0.4);
  box-shadow: 0 20px 45px rgba(0,0,0,0.75);
  margin-bottom: 1.5rem;
}
.lz-panel-soft{
  background: rgba(15,23,42,0.96); border-radius:16px; padding:1.5rem 1.5rem;
  border: 1px solid rgba(148,163,184,0.25); margin-bottom: 1.1rem;
}
.lz-section-title{font-size:1.15rem;font-weight:600;margin-bottom:0.7rem;}
.lz-drop-card{
  border-radius:18px;padding:1.1rem 1rem;
  background: radial-gradient(circle at top left, #020617, #020617);
  border: 1px solid rgba(148,163,184,0.55);
  transition: box-shadow 0.25s ease,border-color 0.25s ease,transform 0.15s ease;
}
.lz-status-bar{
  border-radius:999px;padding:0.45rem 0.9rem;font-size:0.78rem;letter-spacing:0.08em;text-transform:uppercase;
  color:#e5e7eb;background: radial-gradient(circle at left, #22c55e, #020617);
  border: 1px solid rgba(34,197,94,0.7); box-shadow: 0 0 18px rgba(34,197,94,0.55); margin-top:0.7rem;
}
.lz-metric{
  background: radial-gradient(circle at top, #020617, #020617 60%, #020617);
  border-radius:16px;padding:0.9rem;border:1px solid rgba(56,189,248,0.7);
  text-align:center;min-width:150px;min-height:90px;
  display:flex;flex-direction:column;justify-content:center;align-items:center;
  box-shadow: 0 0 14px rgba(56,189,248,0.45), 0 0 26px rgba(37,99,235,0.35);
}
.lz-metric-label{color:#9ca3af;font-size:0.78rem;text-transform:uppercase;letter-spacing:0.08em;}
.lz-metric-value{font-size:1.55rem;font-weight:600;margin-top:0.3rem;}
.lz-verdict{margin-top:1.5rem;padding:1.1rem 1rem;border-radius:18px;font-size:1.5rem;font-weight:700;text-align:center;}
.lz-verdict-success{background: radial-gradient(circle at top left,#22c55e,#14532d);box-shadow:0 0 34px rgba(34,197,94,0.55);}
.lz-verdict-warning{background: radial-gradient(circle at top left,#f97316,#78350f);box-shadow:0 0 34px rgba(249,115,22,0.55);}
.lz-verdict-error{background: radial-gradient(circle at top left,#ef4444,#7f1d1d);box-shadow:0 0 34px rgba(239,68,68,0.55);}
.lz-feed{
  font-family: SFMono-Regular, ui-monospace, Menlo, Monaco, Consolas, "Liberation Mono","Courier New", monospace;
  font-size:0.86rem;color:#e5e7eb;background:#020617;border-radius:10px;padding:0.55rem 0.9rem;
  border:1px solid rgba(148,163,184,0.35);
}
.lz-footer{text-align:center;color:#6b7280;font-size:0.8rem;margin-top:1.6rem;padding-bottom:0.8rem;}
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
    '<div class="lz-subtitle">NPHQ - Special Bureau | Analyst Verification Dashboard</div>',
    unsafe_allow_html=True,
)
st.caption("Copyright © 2025 Anudit Khatri")
# =============================================================================
# Input Panel
# =============================================================================
st.markdown('<div class="lz-panel">', unsafe_allow_html=True)
st.markdown('<div class="lz-section-title">Image input</div>', unsafe_allow_html=True)
st.markdown(
    '<div style="font-size:0.9rem;color:#9ca3af;margin-bottom:0.6rem">'
    "Load two face images into the verification engine. Different captures of the same person give the most realistic result."
    "</div>",
    unsafe_allow_html=True,
)

left, right = st.columns(2)

with left:
    st.markdown(
        '<div style="margin-bottom:0.75rem">'
        '<div style="font-size:0.8rem;text-transform:uppercase;letter-spacing:0.08em;color:#9ca3af">REFERENCE</div>'
        '<div style="font-size:0.9rem;color:#e5e7eb">Primary identity image</div>'
        "</div>",
        unsafe_allow_html=True,
    )
    imgref = st.file_uploader("Reference image", type=["jpg", "jpeg", "png"], label_visibility="collapsed", key="ref_uploader")

with right:
    st.markdown(
        '<div style="margin-bottom:0.75rem">'
        '<div style="font-size:0.8rem;text-transform:uppercase;letter-spacing:0.08em;color:#9ca3af">PROBE</div>'
        '<div style="font-size:0.9rem;color:#e5e7eb">Image to verify against reference</div>'
        "</div>",
        unsafe_allow_html=True,
    )
    imgprobe = st.file_uploader("Probe image", type=["jpg", "jpeg", "png"], label_visibility="collapsed", key="probe_uploader")

# Preview
if imgref or imgprobe:
    st.markdown(
        '<div style="margin-top:0.6rem;font-size:0.85rem;color:#9ca3af">Preview</div>',
        unsafe_allow_html=True,
    )
    p1col, p2col = st.columns(2)
    with p1col:
        if imgref:
            st.image(imgref, caption="Reference", width="stretch")  
        else:
            st.markdown(
                '<div style="border-radius:12px;border:1px dashed rgba(148,163,184,0.5);padding:1.6rem;text-align:center;font-size:0.8rem;color:#6b7280">'
                "Waiting for reference image"
                "</div>",
                unsafe_allow_html=True,
            )
    with p2col:
        if imgprobe:
            st.image(imgprobe, caption="Probe", width="stretch") 
        else:
            st.markdown(
                '<div style="border-radius:12px;border:1px dashed rgba(148,163,184,0.5);padding:1.6rem;text-align:center;font-size:0.8rem;color:#6b7280">'
                "Waiting for probe image"
                "</div>",
                unsafe_allow_html=True,
            )

st.markdown("</div>", unsafe_allow_html=True)  # close input panel

# =============================================================================
# Run verification
# =============================================================================
run_clicked = st.button("Verify identity now")

if run_clicked:
    if not imgref or not imgprobe:
        st.error("Please provide both reference and probe images.")
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as f1, tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as f2:
            f1.write(imgref.read())
            f2.write(imgprobe.read())
            p1, p2 = f1.name, f2.name

        try:
            st.markdown('<div class="lz-panel-soft">', unsafe_allow_html=True)
            st.markdown('<div class="lz-section-title">Analysis engine</div>', unsafe_allow_html=True)

            statusbar = st.markdown('<div class="lz-status-bar">ENGINE STATUS: INITIALIZING</div>', unsafe_allow_html=True)
            progress = st.progress(0)
            feedplaceholder = st.empty()

            def log(msg: str, pct: int, status: Optional[str] = None):
                feedplaceholder.markdown(f'<div class="lz-feed">{msg}</div>', unsafe_allow_html=True)
                progress.progress(pct)
                if status:
                    statusbar.markdown(f'<div class="lz-status-bar">{status}</div>', unsafe_allow_html=True)
                time.sleep(0.2)

            log("Booting verification engine", 20, "ENGINE STATUS: BOOTING")
            verifier = get_verifier()

            log("Running full pipeline (quality, embeddings, geometry)", 65, "ENGINE STATUS: ANALYSING")
            result: VerificationResult = verifier.verify(p1, p2)

            log("Done", 100, "ENGINE STATUS: DONE")
            statusbar.empty()
            progress.empty()
            feedplaceholder.empty()

            # Derived metrics
            similarity = result.similarity
            quality = result.quality_avg
            confidence = result.confidence
            rating10 = max(0.0, min(10.0, confidence / 10.0))
            margin = similarity - 0.52
            borderline = abs(margin) < 0.03

            occsim = None
            forensic_label = "Disabled"
            try:
                occengine = get_occlusion_engine()
                e1u = occengine.embed_upper_face(p1)
                e2u = occengine.embed_upper_face(p2)
                occsim = cosine_sim(e1u, e2u)

                if result.verdict.startswith("SAME") and occsim > 0.55:
                    forensic_label = "SUPPORTS SAME"
                elif result.verdict == "UNCERTAIN" and occsim > 0.55:
                    forensic_label = "LIKELY SAME (REVIEW)"
                elif result.verdict == "DIFFERENT" and occsim < 0.40:
                    forensic_label = "SUPPORTS DIFFERENT"
                else:
                    forensic_label = "INCONCLUSIVE"
            except Exception:
                occsim = None
                forensic_label = "Disabled"

            # Metrics
            st.markdown('<div class="lz-panel">', unsafe_allow_html=True)
            st.markdown("<div class='lz-section-title'>Trust indicators</div>", unsafe_allow_html=True)

            cols = st.columns(5 if occsim is not None else 4)
            with cols[0]:
                st.markdown(f"<div class='lz-metric'><div class='lz-metric-label'>Neural match</div><div class='lz-metric-value'>{similarity:.3f}</div></div>", unsafe_allow_html=True)
            with cols[1]:
                st.markdown(f"<div class='lz-metric'><div class='lz-metric-label'>Quality avg</div><div class='lz-metric-value'>{quality:.1f}/100</div></div>", unsafe_allow_html=True)
            with cols[2]:
                st.markdown(f"<div class='lz-metric'><div class='lz-metric-label'>Rating/10</div><div class='lz-metric-value'>{rating10:.1f}</div></div>", unsafe_allow_html=True)
            with cols[3]:
                st.markdown(f"<div class='lz-metric'><div class='lz-metric-label'>Borderline</div><div class='lz-metric-value'>{'YES' if borderline else 'NO'}</div></div>", unsafe_allow_html=True)
            if occsim is not None:
                with cols[4]:
                    st.markdown(f"<div class='lz-metric'><div class='lz-metric-label'>Upper-face sim</div><div class='lz-metric-value'>{occsim:.3f}</div></div>", unsafe_allow_html=True)

            if occsim is not None:
                st.caption(forensic_label)

            # Verdict
            if result.error:
                vclass = "lz-verdict lz-verdict-error"
                vtext = f"ERROR: {result.error}"
                explanation = "Engine could not complete verification. Check image quality / face visibility."
            elif result.verdict.startswith("SAME"):
                vclass = "lz-verdict lz-verdict-success"
                vtext = "SEEMS TO BE SAME PERSON"
                explanation = "Neural similarity + quality support a same-person match."
            elif result.verdict == "UNCERTAIN":
                vclass = "lz-verdict lz-verdict-warning"
                vtext = "UNCERTAIN MATCH — TRY MORE PICTURES"
                explanation = "Signals are borderline/mixed. Capture better images and retry."
            else:
                vclass = "lz-verdict lz-verdict-error"
                vtext = "SEEMS DIFFERENT"
                explanation = "Embeddings show clear differences."

            st.markdown(f"<div class='{vclass}'>{vtext}</div>", unsafe_allow_html=True)
            st.markdown(f"<p style='font-size:0.9rem;color:#e5e7eb;margin-top:0.45rem'>{explanation}</p>", unsafe_allow_html=True)

            c1, c2 = st.columns(2)
            c1.metric("Confidence", f"{confidence:.1f}%")
            c2.metric("Processing time", f"{result.execution_time:.2f} s")

            # JSON export
            with st.expander("Production JSON export"):
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

            st.markdown("</div>", unsafe_allow_html=True)  # close trust indicators panel
            st.markdown("</div>", unsafe_allow_html=True)  # close analysis panel

        finally:
            try:
                os.unlink(p1)
                os.unlink(p2)
            except Exception:
                pass

# Footer
st.markdown("---")
st.markdown(
    '<div class="lz-footer">LazzyBioIntel v6.2 PRO — Developed By ASI Anudit Khatri</div></div>',
    unsafe_allow_html=True,
)
