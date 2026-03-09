# LAZZYBIOINTEL v6.3 PRO
### Enterprise Identity Verification System

> Developed by **ASI Anudit Khatri** • NPHQ Special Bureau • All operations are logged

![Python](https://img.shields.io/badge/Python-3.11-cyan?style=flat-square&logo=python&logoColor=white&labelColor=0A0F1E&color=00FFFF)
![InsightFace](https://img.shields.io/badge/InsightFace-buffalo__l-cyan?style=flat-square&labelColor=0A0F1E&color=00FFFF)
![MediaPipe](https://img.shields.io/badge/MediaPipe-0.10.14-cyan?style=flat-square&labelColor=0A0F1E&color=00FFFF)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-cyan?style=flat-square&labelColor=0A0F1E&color=00FFFF)
![License](https://img.shields.io/badge/Use-Authorised%20Only-red?style=flat-square&labelColor=0A0F1E)

---

## Overview

LazzyBioIntel v6.3 PRO is a forensic-grade face verification system built for enterprise identity intelligence. It determines whether two face images depict the same individual, with specific robustness against:

- **Age gaps of 5–10+ years**
- **Sunglasses / eyewear**
- **Masks and face coverings**
- **Wigs and hair changes**
- **Degraded, low-resolution, or scanned photographs**

The system runs a **dual-engine pipeline**: the original `UltimateVerifier` core (v6.2, fully preserved) runs alongside the new `FusionEngine` (v6.3), which combines periocular embeddings, zone-aware occlusion analysis, and adaptive quality compensation to produce a more reliable fused verdict.

---

## System Architecture

### Core Engine — v6.2 (unchanged)

The original verification pipeline is fully preserved and always runs first.

```
Image 1 ──┐
           ├──► InsightFace buffalo_l ──► 512-dim embedding ──► Cosine Similarity ──┐
Image 2 ──┘                                                                          ├──► Verdict
           ├──► MediaPipe FaceMesh ──► 4 geometry features ──► Geometry Sim ─────────┤
           └──► Quality Analyzer ──► blur/brightness/contrast/resolution score ──────┘
```

| Signal | Method |
|---|---|
| Face embedding | InsightFace `buffalo_l` — 512-dim cosine similarity |
| Geometry | MediaPipe FaceMesh — eye distance, ratio, aspect, symmetry |
| Quality | Laplacian blur + brightness + contrast + resolution (weighted) |
| Threshold | Adaptive — adjusted by quality score and geometry confidence |

---

### Fusion Engine — v6.3 (new, runs alongside core)

Never modifies core results. Produces its own parallel `FusionResult`.

#### Layer 1 — Age Robust Engine (`age_robust_engine.py`)

Extracts a **periocular crop** (eye + brow region) using MediaPipe landmark indices before embedding. The eye socket region is the most anatomically stable zone across 5–10 years of aging — hair, skin, weight all change but eye geometry does not.

- Crops to periocular zone using 28 precise landmark indices
- Embeds crop using the **shared** `buffalo_l` instance — zero extra RAM
- Falls back to upper-face band → full face if crop is too small for detection

#### Layer 2 — Zone Selector (`zone_selector.py`)

Analyses **4 facial zones** per image independently and detects occlusion type:

| Zone | Covers | Used when |
|---|---|---|
| `full` | Entire face | Default, no occlusion |
| `upper` | Forehead + eyes + nose bridge | Mask detected |
| `periocular` | Eye + brow region only | Mask detected |
| `lower` | Nose + mouth + chin | Sunglasses detected |

**Occlusion detection** uses pixel variance heuristics:
- Low variance in eye band → **sunglasses** → deprioritises periocular, uses lower face
- Low variance in lower band → **mask** → deprioritises lower face, uses periocular + upper

Returns a quality-weighted priority list of usable zones for each image.

#### Layer 3 — Fusion + Low Quality Adapter (`fusion_engine.py`)

Blends three signals with **dynamic weights**:

```
Fused Score = (core × 0.30) + (periocular × 0.50) + (zone_weighted × 0.20)
```

**LowQualityAdapter** — activates automatically when quality asymmetry is detected (old photo vs new photo pattern):

- Enhances degraded images with **CLAHE** (recovers faded contrast) + **unsharp mask** (recovers compression blur) + **bicubic upscale** if face < 80px
- Dynamically shifts weights further toward periocular (up to 0.65) as quality gap grows
- Relaxes age-gap rescue threshold proportionally when worst image quality is very low

**Age-gap rescue rule** — if the fused score is in the uncertain band:
- Periocular ≥ 0.45 AND core ≤ 0.44 → overrides `UNCERTAIN` → `FUSION_SAME_MEDIUM`
- This pattern (strong eye match, weak full-face) is the fingerprint of age drift
- Rescue threshold lowers automatically for very degraded images (e.g. scanned passports)

---

## File Structure

```
Lazzybiointel/
│
├── verify_v6.py              # Core engine — UltimateVerifier v6.2 (unchanged)
├── occlusion_engine.py       # Upper-face occlusion embedding (unchanged)
├── lz_validators.py          # Input validation & path safety (unchanged)
├── logger.py                 # JSON structured logging, 90-day rotation (unchanged)
├── recovery.py               # Session state persistence (unchanged)
├── verify_forensic.py        # Forensic combined CLI report (unchanged)
│
├── age_robust_engine.py      # NEW v6.3 — periocular crop + age-stable embedding
├── zone_selector.py          # NEW v6.3 — 4-zone analysis + occlusion detection
├── fusion_engine.py          # NEW v6.3 — fusion + LowQualityAdapter + rescue logic
│
├── app.py                    # UPDATED v6.3 — Streamlit UI wired to fusion engine
├── requirements.txt          # Pinned dependencies
└── run_local.sh              # Launch script
```

---

## Installation

### Requirements

- Python **3.11** (required — tested on 3.11.x only)
- Ubuntu 20.04+ or Debian 11+ recommended
- Minimum **4GB RAM** (8GB recommended)
- CPU-only supported; NVIDIA GPU optional

### System Dependencies

```bash
sudo apt install libgl1 libglib2.0-0
```

> Required by OpenCV on headless Linux. Already present on most desktop installs.

### Python Setup

```bash
# Clone the repo
git clone https://github.com/arthurrgg8-lgtm/Lazzybiointel-v6.2-PRO.git
cd Lazzybiointel-v6.2-PRO

# Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### InsightFace Model

On first run, InsightFace automatically downloads `buffalo_l` (~500MB) to `~/.insightface/models/buffalo_l/`. Ensure internet access on first launch.

---

## Usage

### Streamlit Web UI

```bash
./run_local.sh
# or
streamlit run app.py --server.address=0.0.0.0 --server.port=8501
```

Open `http://localhost:8501`. Upload a reference image and a probe image. The system runs both engines and displays verdicts, confidence scores, fusion breakdown, and occlusion analysis in the UI.

### Command Line — Core Verifier

```bash
python3 verify_v6.py image1.jpg image2.jpg
python3 verify_v6.py image1.jpg image2.jpg --json     # JSON output
python3 verify_v6.py image1.jpg image2.jpg --quiet    # verdict only
```

### Command Line — Fusion Engine

```bash
python3 fusion_engine.py image1.jpg image2.jpg
```

### Command Line — Forensic Report

```bash
python3 verify_forensic.py image1.jpg image2.jpg
```

### Exit Codes (`verify_v6.py`)

| Code | Meaning |
|---|---|
| `0` | `SAME_HIGH` or `SAME_MEDIUM` — match confirmed |
| `1` | `ERROR` — verification failed |
| `2` | `UNCERTAIN` or `DIFFERENT` — no match or inconclusive |
| `130` | Interrupted by user (Ctrl+C) |

---

## Verdict Reference

### Core Verdicts (`UltimateVerifier`)

| Verdict | Meaning |
|---|---|
| `SAME_HIGH` | Cosine similarity well above threshold — high confidence match |
| `SAME_MEDIUM` | Cosine similarity above threshold — medium confidence match |
| `UNCERTAIN` | Similarity in borderline zone — retry with better images |
| `DIFFERENT` | Similarity clearly below threshold — different individuals |
| `ERROR` | Invalid image, no face detected, or pipeline exception |

### Fusion Verdicts (`FusionEngine`)

| Verdict | Meaning |
|---|---|
| `FUSION_SAME_HIGH` | Fused score ≥ 0.50 — strong multi-signal match |
| `FUSION_SAME_MEDIUM` | Fused score ≥ 0.40, or age-gap rescue triggered |
| `FUSION_UNCERTAIN` | Fused score in uncertain band — inconclusive |
| `FUSION_DIFFERENT` | Fused score < 0.33 — different individuals |
| `FUSION_ERROR` | Fusion pipeline failed — core result still valid |

---

## Configuration

### Core Engine — `verify_v6.py` (`Config` class)

| Parameter | Default | Description |
|---|---|---|
| `BASE_THRESHOLD` | `0.45` | Core cosine similarity threshold |
| `HIGH_CONF_DELTA` | `0.08` | Delta above threshold for `SAME_HIGH` |
| `UNCERTAIN_DELTA` | `0.05` | Delta below threshold for uncertain band |
| `LOW_QUALITY_THRESHOLD` | `50` | Quality score below which threshold is lowered |
| `HIGH_GEOMETRY_THRESHOLD` | `70` | Geometry score above which threshold is raised |
| `DET_SIZE` | `(640, 640)` | InsightFace detection resolution |

### Fusion Engine — `fusion_engine.py` (`FusionConfig` class)

| Parameter | Default | Description |
|---|---|---|
| `CORE_WEIGHT` | `0.30` | Weight of core similarity in fused score |
| `PERIOCULAR_WEIGHT` | `0.50` | Weight of periocular (age-robust) similarity |
| `ZONE_WEIGHT` | `0.20` | Weight of zone-weighted similarity |
| `SAME_HIGH_TH` | `0.50` | Fused score threshold for `FUSION_SAME_HIGH` |
| `SAME_MED_TH` | `0.40` | Fused score threshold for `FUSION_SAME_MEDIUM` |
| `UNCERTAIN_TH` | `0.33` | Fused score threshold for `FUSION_UNCERTAIN` |
| `AGE_RESCUE_PERI_MIN` | `0.45` | Minimum periocular sim to trigger age-gap rescue |
| `AGE_RESCUE_CORE_MAX` | `0.44` | Maximum core sim for rescue (age drift zone) |
| `AGE_RESCUE_CONF` | `62.0` | Confidence assigned when rescue fires |
| `AGREEMENT_BOOST` | `5.0` | Confidence boost when core and periocular agree |
| `DISAGREEMENT_PEN` | `8.0` | Confidence penalty when signals disagree |

### Low Quality Adapter — `fusion_engine.py` (`LowQualityAdapter` class)

| Parameter | Default | Description |
|---|---|---|
| `ASYMMETRY_THRESHOLD` | `20.0` | Quality gap (pts) that triggers weight shifting |
| `LOW_QUALITY_FLOOR` | `45.0` | Score below which image enhancement is applied |
| `MIN_FACE_DIM` | `80` | Minimum face dimension (px) before upscaling |

---

## GPU Acceleration

By default the system runs on CPU. To enable NVIDIA GPU:

```bash
# 1. In requirements.txt — replace:
#    onnxruntime==1.19.2
onnxruntime-gpu==1.19.2

# 2. In verify_v6.py, occlusion_engine.py, age_robust_engine.py — change:
providers=["CUDAExecutionProvider", "CPUExecutionProvider"]
```

---

## Logging

All events are written to `face_verification.log` in JSON Lines format with daily rotation (90-day retention). The fusion engine additionally logs quality gap, weights used, enhancement flags, rescue threshold adjustments, and zone selections.

```json
{"ts":"2026-03-09T12:59:51Z","level":"INFO","logger":"fusion_engine",
 "msg":"Age-gap rescue triggered: peri=0.471 (threshold=0.412) core=0.381 → FUSION_SAME_MEDIUM"}
```

---

## Known Limitations

- Occlusion detection is heuristic (pixel variance) — may misfire in unusual lighting
- Periocular embedding requires `buffalo_l` to detect a face in a tight crop — falls back to full face on failure
- Fusion weights are reasoned, not calibrated on a labeled dataset — tune `FusionConfig` based on real results
- Core and fusion verdicts may disagree — review both alongside the detailed breakdown in the UI
- Processing time ~2x core-only on CPU due to zone analysis and multiple embedding passes
- First run requires internet access to download `buffalo_l` (~500MB)

---

## Author

**ASI Anudit Khatri** • NPHQ Special Bureau

> All operations performed by this system are logged. Intended for authorised forensic and identity verification use only.
