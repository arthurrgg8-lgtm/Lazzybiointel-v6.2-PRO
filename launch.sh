#!/bin/bash
# ============================================================
# LazzyBioIntel v6.3 PRO — One-Click Launcher
# Double-click or run: bash launch.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║        LAZZYBIOINTEL v6.3 PRO — LAUNCHING           ║"
echo "║        NPHQ Special Bureau                          ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# --- Step 1: Create venv if it doesn't exist ---
if [ ! -d "venv" ]; then
    echo "[1/4] Creating virtual environment..."
    python3.11 -m venv venv
    if [ $? -ne 0 ]; then
        echo "      ERROR: python3.11 not found. Install it and retry."
        read -p "Press Enter to close..."
        exit 1
    fi
    echo "      Done."
else
    echo "[1/4] Virtual environment found — skipping creation."
fi

# --- Step 2: Activate venv ---
echo "[2/4] Activating virtual environment..."
source venv/bin/activate
if [ $? -ne 0 ]; then
    echo "      ERROR: Could not activate venv."
    read -p "Press Enter to close..."
    exit 1
fi
echo "      Done."

# --- Step 3: Install dependencies (only if not already done) ---
# Uses a sentinel file venv/.deps_installed
# Delete that file to force a reinstall next launch
SENTINEL="venv/.deps_installed"

if [ ! -f "$SENTINEL" ]; then
    echo "[3/4] Installing dependencies (first run — may take a few minutes)..."
    pip install -q -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "      ERROR: pip install failed. Check requirements.txt and internet."
        read -p "Press Enter to close..."
        exit 1
    fi
    touch "$SENTINEL"
    echo "      Done."
else
    echo "[3/4] Dependencies already installed — skipping."
    echo "      (Delete venv/.deps_installed to force reinstall)"
fi

# --- Step 4: Launch ---
echo "[4/4] Starting LazzyBioIntel..."
echo ""
chmod +x run_local.sh
./run_local.sh
