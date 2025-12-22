# Lazzybiointel-v6.2-PRO
AI based Forensic tool to compare suspects face structure. [UPRADED]
Specailly For LawEnforcement Agencies

# 🌟 LazzyBioIntel v6.2 PRO

Production-ready **face verification engine** with a Streamlit dashboard powered by **InsightFace**, **MediaPipe**, and an adaptive quality-aware decision core.[web:64][file:43]

> Core verification logic lives in `verify_v6.py v6.2` and is used unchanged by the Streamlit UI in `app.py`.

---

## 🚀 Features

- **Neural Face Embeddings** using InsightFace `buffalo_l` (CPU).
- **Adaptive Thresholding** with quality and geometry-aware adjustments (no hard-coded fixed threshold).[file:43]  
- **Image Quality Engine**: blur, brightness, contrast, resolution and composite score out of 100.[file:43]  
- **Geometry Similarity** via MediaPipe FaceMesh (eye distance, ratios, symmetry, aspect).[web:66][file:43]  
- **Enterprise UI**: Streamlit PRO dashboard with similarity, quality, geometry and confidence KPIs.[web:69][file:43]  
- **CLI + JSON**: same verifier available as terminal tool with optional JSON output.[file:43]

---

## 🧠 Architecture

verify_v6.py
├─ Config # Thresholds, quality & geometry weights
├─ ImageQualityAnalyzer # Blur / brightness / contrast / resolution
├─ Geometry (MediaPipe) # Landmark-based geometry embedding
├─ InsightEngine # InsightFace FaceAnalysis (buffalo_l)
└─ UltimateVerifier # Cosine similarity + adaptive decision

app.py
└─ Streamlit dashboard that calls UltimateVerifier.verify()
and visualizes similarity, quality, geometry & verdict


## 🛠️ Local Setup

### 1. Create virtual environment

cd Lazzybiointel
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip


### 2. Install dependencies

pip install
streamlit
insightface==0.7.3
onnxruntime
opencv-python-headless
mediapipe
numpy

---

## ▶️ Run the Streamlit App

cd Lazzybiointel
source .venv/bin/activate
streamlit run app.py

text

Then open: http://localhost:8501 in your browser.

**UI workflow:**

1. Upload **Reference Image** (left).  
2. Upload **Probe Image** (right).  
3. Click **“EXECUTE ENTERPRISE VERIFICATION”**.  
4. Read **Neural Similarity, Quality, Geometry, Verdict, Confidence, Time**.[file:43]

---

## 💻 CLI Verification (Same Engine)

Use the same engine from terminal:

python3 verify_v6.py img1.jpg img2.jpg

text

Options:

python3 verify_v6.py img1.jpg img2.jpg --json
python3 verify_v6.py img1.jpg img2.jpg --quiet


Exit codes:

- `0` → SAME person  
- `2` → DIFFERENT person  
- `1` → Error (quality failure, no face, etc.)[file:43]

---

## 📂 Repository Layout

Lazzybiointel/
├── app.py # Streamlit PRO dashboard (v6.2)
├── verify_v6.py # Ultimate face verification core (v6.2)
├── README.md # This file
└── .gitignore # Python / venv / cache ignores
