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
import base64
import mimetypes
from typing import Optional
from datetime import datetime
from pathlib import Path
import pandas as pd

import recovery
from logger import LogManager
from access_control import (
    authenticate_user,
    delete_user,
    ensure_bootstrap_admin,
    get_login_events,
    get_users,
    init_access_db,
    update_user,
    upsert_user,
)

logger = LogManager.get_logger("app")

restored_state = recovery.restore_session_state()
recovery.cleanup_old_sessions()
try:
    init_access_db()
    ensure_bootstrap_admin()
except Exception:
    logger.critical("Access control initialization failed", exc_info=True)
    st.error("Critical startup error: access-control database failed to initialize.")
    st.stop()

from verify_v6 import UltimateVerifier, VerificationResult
from occlusion_engine import OcclusionEngine, cosine_sim
from fusion_engine import FusionEngine, print_fusion_report   # NEW v6.3
from evidence_locker import save_evidence_pair

@st.cache_resource
def get_verifier():
    return UltimateVerifier()

@st.cache_resource
def get_occlusion_engine():
    return OcclusionEngine()

@st.cache_resource                                            # NEW v6.3
def get_fusion_engine():
    # Share the already-loaded buffalo_l from UltimateVerifier — saves ~500MB RAM
    verifier = get_verifier()
    return FusionEngine(shared_app=verifier.engine.app)

# =============================================================================
# Page Configuration
# =============================================================================
st.set_page_config(
    page_title="LazzyBioIntel v6.2 | Identity Verification System",
    page_icon="🔐",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =============================================================================
# Session State Management
# =============================================================================
if "verification_history" not in st.session_state:
    st.session_state.verification_history = restored_state.get("verification_history", [])
if "session_id" not in st.session_state:
    st.session_state.session_id = restored_state.get(
        "session_id", datetime.now().strftime("%Y%m%d_%H%M%S")
    )
if "audit_log" not in st.session_state:
    st.session_state.audit_log = restored_state.get("audit_log", [])
if "access_authenticated" not in st.session_state:
    st.session_state.access_authenticated = False
if "access_user_name" not in st.session_state:
    st.session_state.access_user_name = None
if "access_user_role" not in st.session_state:
    st.session_state.access_user_role = None


def _find_nepal_police_logo() -> Optional[str]:
    candidates = [
        "nepalpolicelogo.webp",
        "assets/nepalpolicelogo.webp",
        "assets/nepal_police_logo.webp",
        "assets/nepal_police_logo.gif",
        "assets/nepal_police_logo.png",
        "assets/nepal_police_logo.jpg",
        "assets/nepal_police_logo.jpeg",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _find_nepal_flag() -> Optional[str]:
    candidates = [
        "nepalflag.webp",
        "nepalflag.png",
        "nepalflag.jpg",
        "nepalflag.jpeg",
        "assets/nepalflag.webp",
        "assets/nepalflag.png",
        "assets/nepalflag.jpg",
        "assets/nepalflag.jpeg",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _img_data_uri(path: str) -> Optional[str]:
    try:
        mime, _ = mimetypes.guess_type(path)
        if not mime:
            mime = "image/png"
        raw = Path(path).read_bytes()
        enc = base64.b64encode(raw).decode("ascii")
        return f"data:{mime};base64,{enc}"
    except Exception:
        logger.warning("Failed to load image for login header: %s", path, exc_info=True)
        return None


def _client_context() -> tuple[str, str]:
    client_ip = "unknown"
    user_agent = "unknown"
    try:
        headers = getattr(st.context, "headers", {}) or {}
        xff = headers.get("x-forwarded-for") or headers.get("X-Forwarded-For")
        xri = headers.get("x-real-ip") or headers.get("X-Real-Ip")
        uah = headers.get("user-agent") or headers.get("User-Agent")
        if xff:
            client_ip = str(xff).split(",")[0].strip()
        elif xri:
            client_ip = str(xri).strip()
        if uah:
            user_agent = str(uah)
    except Exception:
        logger.warning("Could not read client headers", exc_info=True)
    return client_ip, user_agent

# =============================================================================
# Professional Dark Theme CSS
# =============================================================================
st.markdown("""
<style>
    /* Global Styles */
    .main {
        background: linear-gradient(165deg, #0A0F1E 0%, #0F1425 100%);
    }
    
    .stApp {
        background: linear-gradient(165deg, #0A0F1E 0%, #0F1425 100%);
    }
    
    /* Typography */
    h1, h2, h3, h4, h5, h6 {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        font-weight: 500;
        letter-spacing: -0.02em;
    }
    
    /* Custom Components */
    .header-container {
        background: linear-gradient(90deg, rgba(0, 30, 60, 0.95) 0%, rgba(20, 40, 80, 0.95) 100%);
        border-bottom: 1px solid rgba(0, 255, 255, 0.2);
        padding: 1.5rem 2rem;
        margin-bottom: 2rem;
        backdrop-filter: blur(10px);
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
        position: relative;
        overflow: hidden;
        border-radius: 20px;
        transform: perspective(1400px) rotateX(0.6deg);
    }

    .header-container::after {
        content: "";
        position: absolute;
        inset: 0;
        background: linear-gradient(135deg, rgba(255,255,255,0.08), transparent 38%);
        pointer-events: none;
    }
    
    .title-main {
        font-size: 2.2rem;
        font-weight: 600;
        background: linear-gradient(135deg, #00FFFF, #4169E1);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.25rem;
        letter-spacing: -0.02em;
    }
    
    .title-sub {
        color: #8892b0;
        font-size: 0.9rem;
        font-weight: 400;
        letter-spacing: 0.5px;
    }
    
    /* Metric Cards */
    .metric-card {
        background: linear-gradient(145deg, rgba(17, 31, 54, 0.96), rgba(10, 21, 39, 0.94));
        border: 1px solid rgba(138, 177, 228, 0.12);
        border-radius: 18px;
        padding: 1.25rem;
        box-shadow: 0 14px 28px rgba(0, 0, 0, 0.24);
        transition: transform 0.2s, border-color 0.2s;
        position: relative;
        overflow: hidden;
    }

    .metric-card::before {
        content: "";
        position: absolute;
        inset: 0;
        background: linear-gradient(180deg, rgba(255,255,255,0.05), transparent 26%);
        pointer-events: none;
    }
    
    .metric-card:hover {
        border-color: rgba(106, 177, 255, 0.28);
        transform: translateY(-2px);
    }
    
    .metric-label {
        color: #8892b0;
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 0.5rem;
    }
    
    .metric-value {
        color: #e6f1ff;
        font-size: 2rem;
        font-weight: 600;
        line-height: 1.2;
    }
    
    .metric-trend {
        color: #4ade80;
        font-size: 0.875rem;
        margin-top: 0.5rem;
    }
    
    /* Status Indicators */
    .status-badge {
        display: inline-flex;
        align-items: center;
        padding: 0.35rem 0.75rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }
    
    .status-badge-success {
        background: rgba(34, 197, 94, 0.15);
        border: 1px solid rgba(34, 197, 94, 0.4);
        color: #4ade80;
    }
    
    .status-badge-warning {
        background: rgba(249, 115, 22, 0.15);
        border: 1px solid rgba(249, 115, 22, 0.4);
        color: #fb923c;
    }
    
    .status-badge-error {
        background: rgba(239, 68, 68, 0.15);
        border: 1px solid rgba(239, 68, 68, 0.4);
        color: #f87171;
    }
    
    .status-badge-info {
        background: rgba(59, 130, 246, 0.15);
        border: 1px solid rgba(59, 130, 246, 0.4);
        color: #60a5fa;
    }
    
    /* Panels */
    .panel {
        background: linear-gradient(180deg, rgba(16, 29, 49, 0.96), rgba(12, 23, 39, 0.94));
        border: 1px solid rgba(138, 177, 228, 0.10);
        border-radius: 22px;
        padding: 1.5rem;
        backdrop-filter: blur(10px);
        box-shadow: 0 18px 36px rgba(0, 0, 0, 0.28);
        position: relative;
        overflow: hidden;
        transform: translateZ(0);
    }

    .panel::before {
        content: "";
        position: absolute;
        inset: 0;
        background: linear-gradient(180deg, rgba(255,255,255,0.05), transparent 22%);
        pointer-events: none;
    }
    
    .panel-header {
        border-bottom: 1px solid rgba(138, 177, 228, 0.10);
        padding-bottom: 1rem;
        margin-bottom: 1.5rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    
    .panel-title {
        color: #e6f1ff;
        font-size: 1.08rem;
        font-weight: 600;
        letter-spacing: 0.01em;
    }
    
    /* Verdict Display */
    .verdict-container {
        border-radius: 22px;
        padding: 2rem;
        margin: 1.5rem 0;
        text-align: center;
        background: linear-gradient(145deg, rgba(17, 31, 54, 0.94), rgba(11, 23, 38, 0.96));
        border: 1px solid rgba(138, 177, 228, 0.14);
        box-shadow: 0 18px 36px rgba(0, 0, 0, 0.28), inset 0 1px 0 rgba(255,255,255,0.06);
        transform: perspective(1200px) rotateX(1.2deg);
        animation: riseIn 520ms ease;
    }
    
    .verdict-same {
        background: linear-gradient(135deg, rgba(34, 197, 94, 0.2), rgba(34, 197, 94, 0.05));
        border-color: rgba(34, 197, 94, 0.3);
    }
    
    .verdict-different {
        background: linear-gradient(135deg, rgba(239, 68, 68, 0.2), rgba(239, 68, 68, 0.05));
        border-color: rgba(239, 68, 68, 0.3);
    }
    
    .verdict-uncertain {
        background: linear-gradient(135deg, rgba(249, 115, 22, 0.2), rgba(249, 115, 22, 0.05));
        border-color: rgba(249, 115, 22, 0.3);
    }
    
    .verdict-text {
        font-size: 2.5rem;
        font-weight: 600;
        margin-bottom: 0.5rem;
        letter-spacing: -0.02em;
    }
    
    /* Progress Animation */
    .progress-container {
        background: rgba(0, 0, 0, 0.3);
        border-radius: 8px;
        height: 8px;
        overflow: hidden;
        margin: 1rem 0;
    }
    
    .progress-bar {
        height: 100%;
        background: linear-gradient(90deg, #00FFFF, #4169E1);
        transition: width 0.3s ease;
        border-radius: 8px;
    }
    
    /* Upload Area */
    .upload-area {
        border: 1px dashed rgba(138, 177, 228, 0.24);
        border-radius: 22px;
        padding: 2rem;
        text-align: center;
        background: linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.05));
        transition: all 0.2s;
        box-shadow: 0 12px 24px rgba(0, 0, 0, 0.16), inset 0 1px 0 rgba(255,255,255,0.03);
    }

    .upload-area:hover {
        border-color: rgba(106, 177, 255, 0.34);
        background: linear-gradient(180deg, rgba(106,177,255,0.05), rgba(255,255,255,0.06));
    }
    
    /* Timestamp */
    .timestamp {
        color: #5a6a8a;
        font-size: 0.75rem;
        font-family: 'JetBrains Mono', monospace;
    }
    
    /* Divider */
    .divider {
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(0, 255, 255, 0.3), transparent);
        margin: 2rem 0;
    }
    
    /* Sidebar */
    .css-1d391kg {
        background: linear-gradient(180deg, #0A0F1E 0%, #0F1425 100%);
    }
    
    /* Streamlit Overrides */
    .stButton > button {
        background: linear-gradient(135deg, #00FFFF, #4169E1);
        color: #0A0F1E;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 2rem;
        font-weight: 500;
        letter-spacing: 0.5px;
        transition: all 0.2s;
        width: 100%;
        box-shadow: 0 10px 22px rgba(17, 49, 96, 0.28);
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 16px rgba(0, 255, 255, 0.3);
    }

    @keyframes riseIn {
        from {
            opacity: 0;
            transform: translateY(10px) scale(0.985);
        }
        to {
            opacity: 1;
            transform: translateY(0) scale(1);
        }
    }

    @keyframes floatGlow {
        from {
            transform: translateY(0px);
        }
        to {
            transform: translateY(-3px);
        }
    }

    .metric-card, .upload-area {
        animation: floatGlow 4.2s ease-in-out infinite alternate;
    }

    @media (prefers-reduced-motion: reduce) {
        .metric-card, .upload-area, .verdict-container, .stButton > button {
            animation: none !important;
            transition: none !important;
        }
    }
    
    .stTextInput > div > div > input {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(0, 255, 255, 0.2);
        border-radius: 8px;
        color: #e6f1ff;
    }
    
    /* Data Tables */
    .dataframe {
        background: transparent !important;
    }
    
    .dataframe th {
        background: rgba(0, 255, 255, 0.1) !important;
        color: #e6f1ff !important;
        font-weight: 500 !important;
    }
    
    .dataframe td {
        color: #8892b0 !important;
        border-bottom: 1px solid rgba(0, 255, 255, 0.1) !important;
    }
</style>
""", unsafe_allow_html=True)

# =============================================================================
# Access Control (Name + 6-digit Computer Code)
# =============================================================================
if not st.session_state.access_authenticated:
    logo_path = _find_nepal_police_logo()
    flag_path = _find_nepal_flag()
    logo_uri = _img_data_uri(logo_path) if logo_path else None
    flag_uri = _img_data_uri(flag_path) if flag_path else None
    if logo_uri or flag_uri:
        st.markdown(
            f"""
            <div style="display:flex; align-items:flex-end; justify-content:space-between; gap:12px; margin-bottom:0.5rem;">
                <div style="flex:1;">
                    {"<img src='" + logo_uri + "' style='height:98px; width:auto; object-fit:contain;'/>" if logo_uri else ""}
                </div>
                <div>
                    {"<img src='" + flag_uri + "' style='height:82px; width:auto; object-fit:contain;'/>" if flag_uri else ""}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        """
        <div class="header-container">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <div class="title-main">Secure Access Required</div>
                    <div class="title-sub">Enter your full name and 6-digit computer code</div>
                </div>
                <div style="text-align: right;">
                    <div class="timestamp">System Time: """
        + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        + """</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.subheader("Login")
        with st.form("name_code_login_form", clear_on_submit=False):
            full_name_in = st.text_input("Full Name")
            code_in = st.text_input("Computer Code (6 digits)", max_chars=6, type="password")
            submit_login = st.form_submit_button("Access System", use_container_width=True)

        if submit_login:
            client_ip, user_agent = _client_context()
            ok, msg, user = authenticate_user(
                full_name_in,
                code_in,
                client_ip=client_ip,
                user_agent=user_agent,
            )
            if ok and user:
                st.session_state.access_authenticated = True
                st.session_state.access_user_name = user["full_name"]
                st.session_state.access_user_role = user["role"]
                st.rerun()
            else:
                st.error(msg)

        with st.expander("Need Access or Forgot Credentials?"):
            st.info("Contact Developer - Name: ASI Anudit Khatri | Contact: 9851291019")

    st.stop()

# =============================================================================
# Sidebar - System Status & Controls
# =============================================================================
with st.sidebar:
    st.markdown("""
    <div style="text-align: center; padding: 1rem 0;">
        <span style="font-size: 2rem;">🔐</span>
        <h3 style="color: #e6f1ff; margin: 0.5rem 0;">LazzyBioIntel</h3>
        <div class="status-badge status-badge-info">v6.2 PRO</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(
        f"""
        <div style="margin: 0.75rem 0 0.25rem 0;">
            <div class="metric-label">Logged In User</div>
            <div style="color: #e6f1ff; font-size: 1rem; font-weight: 600;">{st.session_state.access_user_name}</div>
            <div class="timestamp">Role: {st.session_state.access_user_role}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Logout", use_container_width=True):
        st.session_state.access_authenticated = False
        st.session_state.access_user_name = None
        st.session_state.access_user_role = None
        st.rerun()

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # System Status
    st.markdown("### System Status")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-label">Engine</div>
            <div class="metric-value" style="font-size: 1rem;">🟢 Online</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-label">Session</div>
            <div class="metric-value" style="font-size: 1rem;">🟢 Active</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown(f"""
    <div style="margin: 1rem 0;">
        <div class="metric-label">Session ID</div>
        <code style="background: #0A0F1E; padding: 0.25rem 0.5rem; border-radius: 4px;">{st.session_state.session_id}</code>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # Session Statistics
    st.markdown("### Session Statistics")
    total_verifications = len(st.session_state.verification_history)
    if total_verifications > 0:
        same_count = sum(1 for v in st.session_state.verification_history if v['verdict'].startswith('SAME'))
        different_count = sum(1 for v in st.session_state.verification_history if v['verdict'] == 'DIFFERENT')
        st.markdown(f"""
        <div style="margin: 1rem 0;">
            <div class="metric-label">Total Verifications</div>
            <div class="metric-value" style="font-size: 1.5rem;">{total_verifications}</div>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
            <div>
                <div class="metric-label">Same</div>
                <div style="color: #4ade80; font-size: 1.25rem;">{same_count}</div>
            </div>
            <div>
                <div class="metric-label">Different</div>
                <div style="color: #f87171; font-size: 1.25rem;">{different_count}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("No verifications in this session")

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # Data Management
    st.markdown("### Data Management")
    if st.button("📊 Export Session Data", use_container_width=True):
        if st.session_state.verification_history:
            df = pd.DataFrame(st.session_state.verification_history)
            csv = df.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name=f"verification_history_{st.session_state.session_id}.csv",
                mime="text/csv"
            )
        else:
            st.warning("No data to export")

    if st.button("🔄 New Session", use_container_width=True):
        st.session_state.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        st.session_state.verification_history = []
        st.rerun()

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown("### Access Control")
    if st.session_state.access_user_role == "admin":
            with st.expander("Admin Panel", expanded=False):
                with st.form("admin_user_add_form"):
                    admin_name = st.text_input("Full Name", help="Must be unique; admin can update existing user with same name.")
                    admin_code = st.text_input("Computer Code (6 digits)", max_chars=6, type="password")
                    admin_role = st.selectbox("Role", ["staff", "admin"], index=0)
                    admin_active = st.checkbox("Active", value=True)
                    admin_submit = st.form_submit_button("Save User", use_container_width=True)
                if admin_submit:
                    try:
                        action = upsert_user(admin_name, admin_code, role=admin_role, active=admin_active)
                        st.success(f"User {action} successfully.")
                    except Exception as admin_err:
                        st.error(f"Could not save user: {admin_err}")

                users = get_users()
                if users:
                    user_options = {f"{u['full_name']} ({u['role']})": u for u in users}
                    selected_label = st.selectbox("Select User to Edit/Remove", options=list(user_options.keys()))
                    selected_user = user_options[selected_label]

                    with st.form("admin_user_edit_form"):
                        edit_name = st.text_input("Edit Full Name", value=selected_user["full_name"])
                        edit_code = st.text_input("New Computer Code (6 digits, optional)", max_chars=6, type="password")
                        edit_role = st.selectbox(
                            "Edit Role",
                            ["staff", "admin"],
                            index=0 if selected_user["role"] == "staff" else 1,
                        )
                        edit_active = st.checkbox("Active", value=bool(selected_user["active"]))
                        edit_submit = st.form_submit_button("Update User", use_container_width=True)
                    if edit_submit:
                        try:
                            update_user(
                                user_id=int(selected_user["id"]),
                                full_name=edit_name,
                                computer_code=edit_code,
                                role=edit_role,
                                active=edit_active,
                            )
                            st.success("User updated successfully.")
                            st.rerun()
                        except Exception as edit_err:
                            st.error(f"Could not update user: {edit_err}")

                    if st.button("Remove Selected User", use_container_width=True):
                        try:
                            delete_user(int(selected_user["id"]))
                            st.success("User removed successfully.")
                            st.rerun()
                        except Exception as del_err:
                            st.error(f"Could not remove user: {del_err}")

                    users_df = pd.DataFrame(users)
                    users_df["active"] = users_df["active"].map({1: "YES", 0: "NO"})
                    users_df = users_df.rename(columns={"active": "is_active", "created_at": "created_utc", "updated_at": "updated_utc", "last_login_at": "last_login_utc"})
                    st.dataframe(
                        users_df[["full_name", "role", "is_active", "last_login_utc", "updated_utc"]],
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.info("No users found.")

            st.markdown("#### Login Audit")
            login_events = get_login_events(limit=150)
            if login_events:
                audit_df = pd.DataFrame(login_events)
                audit_df["success"] = audit_df["success"].map({1: "SUCCESS", 0: "FAILED"})
                audit_df = audit_df.rename(
                    columns={
                        "created_at": "timestamp_utc",
                        "full_name": "user_name",
                        "client_ip": "ip",
                    }
                )
                st.dataframe(
                    audit_df[["timestamp_utc", "user_name", "success", "reason", "ip"]],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("No login events yet.")
    else:
        st.info("Admin panel and login audit visible only to admin users.")

# =============================================================================
# Main Header
# =============================================================================
header_logo_html = ""
header_logo_path = _find_nepal_police_logo()
if header_logo_path:
    header_logo_uri = _img_data_uri(header_logo_path)
    if header_logo_uri:
        header_logo_html = f"<img src='{header_logo_uri}' style='height:42px; width:auto; object-fit:contain; margin-right:10px;'/>"

st.markdown(f"""
<div class="header-container">
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <div>
            <div style="display:flex; align-items:center;">
                {header_logo_html}
                <div class="title-main">Identity Verification System (For Analysts)</div>
            </div>
            <div class="title-sub">Advanced Biometric Analysis Engine • NPHQ Special Bureau</div>
        </div>
        <div style="text-align: right;">
            <div class="timestamp">Session: """ + st.session_state.session_id + """</div>
            <div class="timestamp">System Time: """ + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# =============================================================================
# Main Content Area - FIXED: Replaced use_column_width with use_container_width
# =============================================================================
col1, col2 = st.columns([1, 1])

with col1:
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown("""
    <div class="panel-header">
        <span class="panel-title">📸 Reference Image Capture</span>
        <span class="status-badge status-badge-info">PRIMARY IDENTITY</span>
    </div>
    """, unsafe_allow_html=True)
    
    imgref = st.file_uploader(
        "Upload reference image",
        type=["jpg", "jpeg", "png"],
        key="ref_uploader",
        label_visibility="collapsed"
    )
    
    if imgref:
        # FIXED: Changed use_column_width=True to use_container_width=True
        st.image(imgref, use_container_width=True)
        st.markdown(f"""
        <div style="margin-top: 0.5rem;">
            <span class="status-badge status-badge-success">Loaded</span>
            <span class="timestamp" style="margin-left: 0.5rem;">{imgref.name}</span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="upload-area">
            <span style="font-size: 3rem;">📁</span>
            <p style="color: #8892b0; margin: 1rem 0;">Drag & drop or browse to upload</p>
            <p style="color: #5a6a8a; font-size: 0.875rem;">Supports JPG, PNG • Max 10MB</p>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

with col2:
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown("""
    <div class="panel-header">
        <span class="panel-title">🔍 Probe Image Capture</span>
        <span class="status-badge status-badge-info">VERIFICATION TARGET</span>
    </div>
    """, unsafe_allow_html=True)
    
    imgprobe = st.file_uploader(
        "Upload probe image",
        type=["jpg", "jpeg", "png"],
        key="probe_uploader",
        label_visibility="collapsed"
    )
    
    if imgprobe:
        # FIXED: Changed use_column_width=True to use_container_width=True
        st.image(imgprobe, use_container_width=True)
        st.markdown(f"""
        <div style="margin-top: 0.5rem;">
            <span class="status-badge status-badge-success">Loaded</span>
            <span class="timestamp" style="margin-left: 0.5rem;">{imgprobe.name}</span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="upload-area">
            <span style="font-size: 3rem;">🔍</span>
            <p style="color: #8892b0; margin: 1rem 0;">Drag & drop or browse to upload</p>
            <p style="color: #5a6a8a; font-size: 0.875rem;">Supports JPG, PNG • Max 10MB</p>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

# =============================================================================
# Verification Controls
# =============================================================================
st.markdown('<div class="panel" style="margin-top: 1rem;">', unsafe_allow_html=True)

col1, col2, col3 = st.columns([2, 1, 2])
with col2:
    run_verification = st.button("🚀 VERIFY IDENTITY", use_container_width=True)

if run_verification:
    if not imgref or not imgprobe:
        st.error("⚠️ Please upload both reference and probe images")
    else:
        ref_bytes = imgref.read()
        probe_bytes = imgprobe.read()

        # Separate, non-blocking evidence locker: never affects verification path.
        try:
            save_evidence_pair(
                ref_bytes=ref_bytes,
                ref_name=getattr(imgref, "name", "reference.jpg"),
                probe_bytes=probe_bytes,
                probe_name=getattr(imgprobe, "name", "probe.jpg"),
                session_id=st.session_state.session_id,
            )
        except Exception:
            logger.warning("Evidence locker save failed; continuing verification", exc_info=True)

        # Save temporary files
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as f1, \
             tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as f2:
            f1.write(ref_bytes)
            f2.write(probe_bytes)
            ref_path, probe_path = f1.name, f2.name
        
        try:
            # Verification Progress
            progress_placeholder = st.empty()
            status_placeholder = st.empty()
            
            # Progress bar container
            with progress_placeholder.container():
                st.markdown("""
                <div class="panel" style="margin: 1rem 0;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                        <span class="panel-title">Analysis Progress</span>
                        <span class="status-badge status-badge-info" id="progress-status">Initializing</span>
                    </div>
                """, unsafe_allow_html=True)
                progress_bar = st.progress(0)
                st.markdown('</div>', unsafe_allow_html=True)
            
            def update_progress(percent, status, message):
                progress_bar.progress(percent)
                status_placeholder.markdown(f"""
                <div style="margin-top: 0.5rem;">
                    <span class="status-badge status-badge-info">{status}</span>
                    <span style="color: #8892b0; margin-left: 0.5rem;">{message}</span>
                </div>
                """, unsafe_allow_html=True)
                time.sleep(0.2)
            
            # Run verification
            update_progress(20, "Loading", "Initializing neural networks...")
            verifier = get_verifier()

            update_progress(40, "Processing", "Analyzing facial features...")
            result: VerificationResult = verifier.verify(ref_path, probe_path)

            update_progress(65, "Computing", "Running fusion engine (age/occlusion)...")
            # --- Fusion Engine (NEW v6.3) ---
            fusion_result = None
            try:
                fusion_eng = get_fusion_engine()
                fusion_result = fusion_eng.verify(ref_path, probe_path, result)
            except Exception:
                logger.warning("Fusion engine failed; falling back to core result", exc_info=True)
                fusion_result = None

            update_progress(85, "Computing", "Calculating similarity metrics...")

            # Legacy occlusion sim (kept for metric card backward compat)
            try:
                occengine = get_occlusion_engine()
                e1u = occengine.embed_upper_face(ref_path)
                e2u = occengine.embed_upper_face(probe_path)
                occsim = cosine_sim(e1u, e2u)
            except Exception:
                logger.warning("Occlusion metric failed; continuing without it", exc_info=True)
                occsim = None

            update_progress(100, "Complete", "Verification finished")
            
            # Clear progress display
            progress_placeholder.empty()
            status_placeholder.empty()
            
            # Display Results
            st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
            
            # Verdict Display
            # Fusion verdict takes priority when available; core is always preserved
            active_verdict    = fusion_result.fusion_verdict   if fusion_result else result.verdict
            active_confidence = fusion_result.fusion_confidence if fusion_result else result.confidence
            fusion_active     = fusion_result is not None and not fusion_result.error

            if result.error:
                vclass = "verdict-different"
                vtext = f"ERROR: {result.error}"
                explanation = "Engine could not complete verification. Check image quality / face visibility."
            elif active_verdict.startswith("FUSION_SAME") or active_verdict.startswith("SAME"):
                vclass = "verdict-same"
                vtext = "SEEMS TO BE SAME PERSON"
                explanation = "Fusion engine (age + occlusion aware) supports a same-person match." if fusion_active else "Neural similarity + quality support a same-person match."
            elif "UNCERTAIN" in active_verdict:
                vclass = "verdict-uncertain"
                vtext = "UNCERTAIN MATCH — TRY MORE PICTURES"
                explanation = "Signals are borderline/mixed. Capture better images and retry."
            else:
                vclass = "verdict-different"
                vtext = "SEEMS DIFFERENT"
                explanation = "Embeddings show clear differences across all fusion zones."
            
            st.markdown(f"<div class='verdict-container {vclass}'><div class='verdict-text'>{vtext}</div><div style='color: #8892b0; margin-bottom: 1rem;'>{explanation}</div>", unsafe_allow_html=True)

            # Confidence + similarity row — shows fusion when available
            if fusion_active:
                st.markdown(f"""
                <div style="display: flex; justify-content: center; gap: 2rem; margin-top: 1rem;">
                    <div style="text-align:center;">
                        <div class="metric-label">Core Confidence</div>
                        <div style="font-size: 1.3rem; color: #8892b0;">{result.confidence:.1f}%</div>
                    </div>
                    <div style="text-align:center;">
                        <div class="metric-label">Fusion Confidence</div>
                        <div style="font-size: 1.5rem; color: #e6f1ff;">{fusion_result.fusion_confidence:.1f}%</div>
                    </div>
                    <div style="text-align:center;">
                        <div class="metric-label">Fused Similarity</div>
                        <div style="font-size: 1.5rem; color: #e6f1ff;">{fusion_result.fused_sim:.3f}</div>
                    </div>
                </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="display: flex; justify-content: center; gap: 2rem; margin-top: 1rem;">
                    <div>
                        <div class="metric-label">Confidence</div>
                        <div style="font-size: 1.5rem; color: #e6f1ff;">{result.confidence:.1f}%</div>
                    </div>
                    <div>
                        <div class="metric-label">Similarity</div>
                        <div style="font-size: 1.5rem; color: #e6f1ff;">{result.similarity:.3f}</div>
                    </div>
                </div>
                </div>
                """, unsafe_allow_html=True)
            
            # Metrics Grid
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.markdown("""
                <div class="metric-card">
                    <div class="metric-label">Neural Similarity</div>
                    <div class="metric-value">{:.3f}</div>
                </div>
                """.format(result.similarity), unsafe_allow_html=True)
            
            with col2:
                st.markdown("""
                <div class="metric-card">
                    <div class="metric-label">Quality Score</div>
                    <div class="metric-value">{:.1f}/100</div>
                </div>
                """.format(result.quality_avg), unsafe_allow_html=True)
            
            with col3:
                st.markdown("""
                <div class="metric-card">
                    <div class="metric-label">Processing Time</div>
                    <div class="metric-value">{:.2f}s</div>
                </div>
                """.format(result.execution_time), unsafe_allow_html=True)
            
            with col4:
                if fusion_active:
                    st.markdown("""
                    <div class="metric-card">
                        <div class="metric-label">Periocular Sim</div>
                        <div class="metric-value">{:.3f}</div>
                        <div class="metric-trend">Age-robust zone</div>
                    </div>
                    """.format(fusion_result.periocular_sim), unsafe_allow_html=True)
                elif occsim:
                    st.markdown("""
                    <div class="metric-card">
                        <div class="metric-label">Upper Face Match</div>
                        <div class="metric-value">{:.3f}</div>
                    </div>
                    """.format(occsim), unsafe_allow_html=True)
            
            # Detailed Analysis
            with st.expander("🔬 Detailed Analysis Report", expanded=False):
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("#### Reference Image Analysis")
                    st.metric("Quality Score", f"{result.q1.score:.1f}")
                    if hasattr(result.q1, 'details'):
                        st.json(result.q1.details)

                with col2:
                    st.markdown("#### Probe Image Analysis")
                    st.metric("Quality Score", f"{result.q2.score:.1f}")
                    if hasattr(result.q2, 'details'):
                        st.json(result.q2.details)

                st.markdown("#### Geometric Analysis")
                st.metric("Geometric Similarity", f"{result.geometry_sim:.1f}%")

                # --- Fusion breakdown (NEW v6.3) ---
                if fusion_active:
                    st.markdown("#### 🔀 Fusion Engine Breakdown")
                    fc1, fc2, fc3 = st.columns(3)
                    with fc1:
                        st.metric("Periocular Sim", f"{fusion_result.periocular_sim:.3f}",
                                  help="Eye/brow region — most stable across aging")
                    with fc2:
                        st.metric("Zone-Weighted Sim", f"{fusion_result.zone_sim:.3f}",
                                  help="Weighted across usable face zones")
                    with fc3:
                        st.metric("Fused Similarity", f"{fusion_result.fused_sim:.3f}",
                                  help="Combined core + periocular + zone score")

                    # Build weights display safely — getattr guards against stale cache
                    w         = getattr(fusion_result, "weights_used", None) or {}
                    q_gap     = getattr(fusion_result, "quality_gap", 0.0)
                    enh1_flag = getattr(fusion_result, "enhanced_img1", False)
                    enh2_flag = getattr(fusion_result, "enhanced_img2", False)
                    r_adj     = getattr(fusion_result, "rescue_adj", 0.0)
                    enh_flags = []
                    if enh1_flag:
                        enh_flags.append("img1")
                    if enh2_flag:
                        enh_flags.append("img2")
                    enh_str = ", ".join(enh_flags) if enh_flags else "none"

                    st.markdown(f"""
                    | Field | Value |
                    |---|---|
                    | Occlusion img1 | `{fusion_result.occlusion_img1}` |
                    | Occlusion img2 | `{fusion_result.occlusion_img2}` |
                    | Zones used | `{', '.join(fusion_result.zones_used)}` |
                    | Periocular method | `{fusion_result.periocular_method}` |
                    | Quality gap | `{q_gap:.1f} pts` |
                    | Enhanced images | `{enh_str}` |
                    | Weights (core/peri/zone) | `{w.get('core', 0):.2f} / {w.get('periocular', 0):.2f} / {w.get('zone', 0):.2f}` |
                    | Rescue threshold adj | `{r_adj:+.3f}` |
                    | Fusion verdict | `{fusion_result.fusion_verdict}` |
                    | Fusion confidence | `{fusion_result.fusion_confidence:.1f}%` |
                    """)

                st.markdown("#### Raw Data Export")
                export_data = {
                    "timestamp": datetime.now().isoformat(),
                    "session_id": st.session_state.session_id,
                    # Core (unchanged)
                    "core_verdict": result.verdict,
                    "core_confidence": result.confidence,
                    "core_similarity": round(result.similarity, 4),
                    "quality_average": round(result.quality_avg, 2),
                    "execution_time": round(result.execution_time, 3),
                    "reference_quality": result.q1.score,
                    "probe_quality": result.q2.score,
                    "geometric_similarity": round(result.geometry_sim, 2),
                    "upper_face_similarity": round(occsim, 4) if occsim else None,
                    "error": result.error,
                    # Fusion (new)
                    "fusion_verdict": fusion_result.fusion_verdict if fusion_active else None,
                    "fusion_confidence": fusion_result.fusion_confidence if fusion_active else None,
                    "fused_similarity": fusion_result.fused_sim if fusion_active else None,
                    "periocular_similarity": fusion_result.periocular_sim if fusion_active else None,
                    "zone_weighted_similarity": fusion_result.zone_sim if fusion_active else None,
                    "occlusion_img1": fusion_result.occlusion_img1 if fusion_active else None,
                    "occlusion_img2": fusion_result.occlusion_img2 if fusion_active else None,
                    "zones_used": fusion_result.zones_used if fusion_active else None,
                    "fusion_error": fusion_result.error if fusion_active else "not_run",
                }
                st.json(export_data)

                st.download_button(
                    label="📥 Download Report (JSON)",
                    data=json.dumps(export_data, indent=2),
                    file_name=f"verification_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json"
                )
            
            # Save to history
            st.session_state.verification_history.append({
                "timestamp": datetime.now().isoformat(),
                "verdict": result.verdict,
                "confidence": result.confidence,
                "similarity": result.similarity,
                "quality": result.quality_avg,
                "execution_time": result.execution_time
            })
            
        finally:
            # Cleanup
            for path in (ref_path, probe_path):
                try:
                    if path and os.path.exists(path):
                        os.unlink(path)
                except OSError:
                    logger.warning("Failed to delete temporary file: %s", path, exc_info=True)

st.markdown('</div>', unsafe_allow_html=True)

# Persist minimal session state for crash/reload resilience.
recovery.save_session_state(
    {
        "verification_history": st.session_state.verification_history,
        "session_id": st.session_state.session_id,
        "audit_log": st.session_state.audit_log,
    }
)

# =============================================================================
# Recent Activity
# =============================================================================
if st.session_state.verification_history:
    st.markdown('<div class="panel" style="margin-top: 1rem;">', unsafe_allow_html=True)
    st.markdown("""
    <div class="panel-header">
        <span class="panel-title">📋 Recent Verifications</span>
        <span class="status-badge status-badge-info">LIVE FEED</span>
    </div>
    """, unsafe_allow_html=True)
    
    # Create a DataFrame for display
    history_df = pd.DataFrame(st.session_state.verification_history[-5:])  # Last 5
    history_df = history_df[['timestamp', 'verdict', 'confidence', 'similarity', 'quality', 'execution_time']]
    history_df.columns = ['Timestamp', 'Verdict', 'Confidence %', 'Similarity', 'Quality', 'Time (s)']
    
    st.dataframe(
        history_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Confidence %": st.column_config.NumberColumn(format="%.1f%%"),
            "Similarity": st.column_config.NumberColumn(format="%.3f"),
            "Quality": st.column_config.NumberColumn(format="%.1f"),
            "Time (s)": st.column_config.NumberColumn(format="%.2f")
        }
    )
    
    st.markdown('</div>', unsafe_allow_html=True)

# =============================================================================
# Footer
# =============================================================================
st.markdown("""
<div style="margin-top: 3rem; padding: 1rem; text-align: center; border-top: 1px solid rgba(0, 255, 255, 0.1);">
    <div style="color: #5a6a8a; font-size: 0.75rem;">
        LazzyBioIntel v6.2 PRO — Enterprise Identity Verification System
    </div>
    <div style="color: #3a4a6a; font-size: 0.7rem; margin-top: 0.5rem;">
        Developed by ASI Anudit Khatri • NPHQ Special Bureau • All operations are logged
    </div>
</div>
""", unsafe_allow_html=True)
