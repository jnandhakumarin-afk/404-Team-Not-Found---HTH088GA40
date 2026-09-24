import os
import sys
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import httpx
import streamlit as st

# ---------------------------------------------------------------------------
# Backend Configuration
# ---------------------------------------------------------------------------
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

# ---------------------------------------------------------------------------
# Streamlit Page Configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="AI Code Review & Release-Risk Assistant",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Session State Initialization
# ---------------------------------------------------------------------------
if "theme" not in st.session_state:
    st.session_state["theme"] = "Dark"

if "active_page" not in st.session_state:
    st.session_state["active_page"] = "Dashboard"

if "review_result" not in st.session_state:
    st.session_state["review_result"] = None

if "eval_benchmark_result" not in st.session_state:
    st.session_state["eval_benchmark_result"] = None

if "target_url" not in st.session_state:
    st.session_state["target_url"] = ""

if "findings_filter" not in st.session_state:
    st.session_state["findings_filter"] = "All"

# ---------------------------------------------------------------------------
# Theme Palettes & Semantic Color System
# ---------------------------------------------------------------------------
PALETTES = {
    "Dark": {
        "bg": "#1A1B25",
        "card_bg": "#232530",
        "card_bg_elevated": "#282A37",
        "border": "#3A3D4D",
        "border_subtle": "#2E3140",
        "primary_text": "#E8E9F1",
        "secondary_text": "#8A8FA3",
        "muted_text": "#6B7085",
        "accent": "#2DD4BF",
        "accent_glow": "rgba(45, 212, 191, 0.18)",
        "security": "#F4534F",
        "security_bg": "rgba(244, 83, 79, 0.12)",
        "bug": "#FF9838",
        "bug_bg": "rgba(255, 152, 56, 0.12)",
        "performance": "#54A1FF",
        "performance_bg": "rgba(84, 161, 255, 0.12)",
        "style": "#8A8FA3",
        "style_bg": "rgba(138, 143, 163, 0.12)",
        "action_btn": "#2DD4BF",
        "action_text": "#1A1B25",
        "code_bg": "#14151E",
        "code_border": "#2E3140",
        "shadow_card": "0 6px 18px -2px rgba(0, 0, 0, 0.4), 0 2px 6px -1px rgba(0, 0, 0, 0.25), inset 0 1px 0 rgba(255, 255, 255, 0.05)",
        "shadow_elevated": "0 10px 28px -4px rgba(0, 0, 0, 0.5), 0 4px 10px -2px rgba(0, 0, 0, 0.35)",
    },
    "Light": {
        "bg": "#F4F6F8",
        "card_bg": "#FFFFFF",
        "card_bg_elevated": "#FAFBFC",
        "border": "#D9DDE5",
        "border_subtle": "#E5E8EF",
        "primary_text": "#1A1B25",
        "secondary_text": "#475467",
        "muted_text": "#667085",
        "accent": "#2DD4BF",
        "accent_glow": "rgba(45, 212, 191, 0.20)",
        "security": "#F4534F",
        "security_bg": "rgba(244, 83, 79, 0.10)",
        "bug": "#FF9838",
        "bug_bg": "rgba(255, 152, 56, 0.10)",
        "performance": "#54A1FF",
        "performance_bg": "rgba(84, 161, 255, 0.10)",
        "style": "#8A8FA3",
        "style_bg": "rgba(138, 143, 163, 0.10)",
        "action_btn": "#0D9488",
        "action_text": "#FFFFFF",
        "code_bg": "#F0F2F6",
        "code_border": "#D9DDE5",
        "shadow_card": "0 4px 16px -2px rgba(16, 24, 40, 0.08), 0 1px 3px rgba(16, 24, 40, 0.04), inset 0 1px 0 rgba(255, 255, 255, 0.9)",
        "shadow_elevated": "0 8px 24px -4px rgba(16, 24, 40, 0.12), 0 3px 8px -2px rgba(16, 24, 40, 0.06)",
    },
}

current_theme = st.session_state["theme"]
P = PALETTES[current_theme]

# ---------------------------------------------------------------------------
# Custom CSS: Times New Roman, 3D Elevation, and Theme Contrasts
# ---------------------------------------------------------------------------
GLOBAL_CSS = f"""
<style>
/* Universal Times New Roman Typography */
html, body, [class*="css"], .stApp, h1, h2, h3, h4, h5, h6, p, div, span, button, input, textarea, label, [data-testid="stSidebar"] {{
    font-family: "Times New Roman", Times, serif !important;
}}

/* Application Canvas */
.stApp {{
    background-color: {P["bg"]} !important;
    color: {P["primary_text"]} !important;
}}

/* Sidebar Base */
[data-testid="stSidebar"] {{
    background-color: {P["card_bg"]} !important;
    border-right: 1px solid {P["border"]} !important;
    padding-top: 1rem;
}}

[data-testid="stSidebar"] hr {{
    border-color: {P["border"]} !important;
    margin: 1rem 0 !important;
}}

/* Streamlit Inputs */
.stTextInput > div > div > input {{
    background-color: {P["card_bg"]} !important;
    color: {P["primary_text"]} !important;
    border: 1px solid {P["border"]} !important;
    border-radius: 10px !important;
    font-size: 1rem !important;
    padding: 0.65rem 1rem !important;
    box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.04) !important;
    transition: all 0.2s ease !important;
}}

.stTextInput > div > div > input:focus {{
    border-color: {P["accent"]} !important;
    box-shadow: 0 0 0 2px {P["accent_glow"]} !important;
}}

.stTextInput label {{
    color: {P["primary_text"]} !important;
    font-weight: bold !important;
    font-size: 0.95rem !important;
}}

/* Primary Action Buttons */
.stButton > button {{
    border-radius: 10px !important;
    font-weight: bold !important;
    padding: 0.6rem 1.4rem !important;
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.12) !important;
    letter-spacing: 0.3px !important;
}}

.stButton > button:hover {{
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 14px rgba(0, 0, 0, 0.18) !important;
}}

.stButton > button:active {{
    transform: translateY(0) !important;
}}

/* Sidebar Navigation Buttons */
[data-testid="stSidebar"] .stButton > button {{
    width: 100% !important;
    text-align: left !important;
    justify-content: flex-start !important;
    font-size: 0.95rem !important;
    border-radius: 8px !important;
    padding: 0.55rem 0.9rem !important;
    margin-bottom: 0.25rem !important;
}}

/* 3D Elevated Cards */
.cyber-card {{
    background-color: {P["card_bg"]};
    border: 1px solid {P["border"]};
    border-radius: 12px;
    padding: 1.35rem;
    margin-bottom: 1.25rem;
    box-shadow: {P["shadow_card"]};
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}}

.cyber-card:hover {{
    box-shadow: {P["shadow_elevated"]};
}}

.cyber-metric-card {{
    background: {P["card_bg_elevated"]};
    border: 1px solid {P["border"]};
    border-radius: 12px;
    padding: 1.25rem;
    text-align: center;
    box-shadow: {P["shadow_card"]};
    position: relative;
    overflow: hidden;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}}

.cyber-metric-card:hover {{
    transform: translateY(-2px);
    box-shadow: {P["shadow_elevated"]};
}}

.cyber-metric-title {{
    color: {P["secondary_text"]};
    font-size: 0.85rem;
    font-weight: bold;
    letter-spacing: 1px;
    text-transform: uppercase;
    margin-bottom: 0.4rem;
}}

.cyber-metric-value {{
    color: {P["primary_text"]};
    font-size: 2.4rem;
    font-weight: bold;
    line-height: 1.1;
    margin-bottom: 0.35rem;
}}

.cyber-metric-sub {{
    color: {P["muted_text"]};
    font-size: 0.85rem;
}}

/* Pills and Badges */
.status-pill {{
    display: inline-block;
    padding: 0.3rem 0.75rem;
    border-radius: 8px;
    font-size: 0.82rem;
    font-weight: bold;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}}

.pill-security {{
    background-color: {P["security_bg"]};
    color: {P["security"]};
    border: 1px solid {P["security"]};
}}

.pill-bug {{
    background-color: {P["bug_bg"]};
    color: {P["bug"]};
    border: 1px solid {P["bug"]};
}}

.pill-performance {{
    background-color: {P["performance_bg"]};
    color: {P["performance"]};
    border: 1px solid {P["performance"]};
}}

.pill-style {{
    background-color: {P["style_bg"]};
    color: {P["style"]};
    border: 1px solid {P["style"]};
}}

.pill-accent {{
    background-color: {P["accent_glow"]};
    color: {P["accent"]};
    border: 1px solid {P["accent"]};
}}

/* Monospace Code & Evidence Boxes */
.evidence-box {{
    background-color: {P["code_bg"]};
    border: 1px solid {P["code_border"]};
    border-left: 3px solid {P["accent"]};
    padding: 0.65rem 0.85rem;
    border-radius: 6px;
    font-family: Consolas, Monaco, "Courier New", monospace !important;
    font-size: 0.88rem;
    color: {P["primary_text"]};
    margin: 0.6rem 0;
    overflow-x: auto;
    line-height: 1.4;
}}

/* Navigation Active Indicator */
.nav-active {{
    background-color: {P["accent_glow"]} !important;
    border-left: 4px solid {P["accent"]} !important;
    color: {P["accent"]} !important;
    font-weight: bold !important;
}}

/* System Pulse Indicator */
.pulse-dot {{
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background-color: {P["accent"]};
    margin-right: 6px;
    box-shadow: 0 0 8px {P["accent"]};
}}
</style>
"""
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Backend Client Methods
# ---------------------------------------------------------------------------
def call_backend_review(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Call POST /api/review on the FastAPI backend."""
    try:
        with httpx.Client(timeout=90.0) as client:
            resp = client.post(f"{BACKEND_URL}/api/review", json=payload)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 400:
                raise ValueError(resp.json().get("detail", "Invalid GitHub URL provided."))
            elif resp.status_code == 404:
                raise ValueError("GitHub pull request or commit was not found. Please verify the URL.")
            elif resp.status_code == 422:
                raise ValueError("Could not parse or process the GitHub target.")
            else:
                raise RuntimeError(f"Backend returned status {resp.status_code}: {resp.text}")
    except httpx.ConnectError:
        raise ConnectionError(
            f"Cannot connect to the backend at {BACKEND_URL}. Ensure the FastAPI server is running on port 8000."
        )
    except httpx.TimeoutException:
        raise TimeoutError("The review request timed out. Please check your network connection.")


def call_backend_evaluate() -> Dict[str, Any]:
    """Call POST /api/evaluate on the backend against the built-in dataset."""
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(f"{BACKEND_URL}/api/evaluate", json={"use_dataset": True})
            if resp.status_code == 200:
                return resp.json()
            else:
                raise RuntimeError(f"Evaluation failed: {resp.text}")
    except Exception as e:
        raise RuntimeError(f"Could not connect to evaluation service: {e}")


# ---------------------------------------------------------------------------
# Shared Sub-Renderers: Header & Provider Notice
# ---------------------------------------------------------------------------
def render_header():
    """Renders the standard top product banner."""
    st.markdown(
        f"""
        <div style="margin-bottom: 1.5rem; padding-bottom: 0.85rem; border-bottom: 1px solid {P['border']};">
            <h1 style="margin: 0; font-size: 2.3rem; font-weight: bold; color: {P['primary_text']}; letter-spacing: -0.5px;">
                AI Code Review & Release-Risk Assistant
            </h1>
            <p style="margin: 0.35rem 0 0 0; font-size: 1.05rem; color: {P['secondary_text']};">
                Automated code analysis, AI-assisted review, and deterministic release-risk scoring.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_provider_status(review_data: Dict[str, Any]):
    """Renders the AI provider badge and notices with high visibility."""
    is_fallback = review_data.get("fallback_to_static", False)
    provider = review_data.get("provider", "static")
    truncated_files = review_data.get("truncated_files", [])

    if truncated_files:
        st.warning(
            f"⚠️ **Changed files were truncated for analysis (capped at 500 lines):** "
            f"{', '.join(truncated_files)}"
        )

    if not is_fallback:
        if provider == "gemini":
            st.success("✅ **AI review powered by Gemini**")
        elif provider == "groq":
            st.info("ℹ️ **AI review powered by Groq fallback**")
        else:
            st.success(f"✅ **AI review powered by {provider.capitalize()}**")
    else:
        st.info("ℹ️ **AI review unavailable — showing static analysis findings.**")


# ---------------------------------------------------------------------------
# View 1: Dashboard
# ---------------------------------------------------------------------------
def render_dashboard():
    """Render the central overview dashboard."""
    render_header()
    review_data = st.session_state.get("review_result")

    # Review Action Card
    st.markdown(
        f"""
        <div class="cyber-card" style="margin-bottom: 1.5rem;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
                <h3 style="margin: 0; font-size: 1.25rem; color: {P['primary_text']};">
                    🚀 Run Instant Code Review
                </h3>
                <span style="font-size: 0.85rem; color: {P['secondary_text']};">
                    GitHub PRs & Commits Supported
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_url, col_btn = st.columns([5, 1.2])
    with col_url:
        target_url = st.text_input(
            "GitHub URL",
            value=st.session_state.get("target_url", ""),
            placeholder="https://github.com/owner/repo/pull/123 or https://github.com/owner/repo/commit/...",
            label_visibility="collapsed",
            key="dash_url_input",
        )
    with col_btn:
        run_review = st.button("Analyze Code", key="dash_run_btn", use_container_width=True)

    if run_review:
        if not target_url.strip():
            st.error("Please enter a valid GitHub Pull Request or Commit URL.")
        else:
            st.session_state["target_url"] = target_url.strip()
            with st.status("Analyzing codebase...", expanded=True) as status:
                st.write("1. Ingesting PR/commit diff from GitHub...")
                try:
                    st.write("2. Running static analysis (Ruff, Bandit, ESLint)...")
                    st.write("3. Calling contextual AI reviewer (Gemini / Groq)...")
                    st.write("4. Executing deterministic risk engine...")
                    result = call_backend_review({"url": target_url.strip()})
                    st.session_state["review_result"] = result
                    status.update(label="Review complete!", state="complete", expanded=False)
                    st.rerun()
                except Exception as e:
                    status.update(label="Review failed", state="error", expanded=True)
                    st.error(f"Error during code review: {e}")

    # Metrics Grid
    if review_data:
        render_provider_status(review_data)
        risk = review_data.get("risk", {})
        total_risk = risk.get("total_risk", 0)
        release_status = risk.get("release_status", "SAFE TO RELEASE")
        findings = review_data.get("findings", [])
        evaluation = review_data.get("evaluation", {})
        sig_ratio_pct = evaluation.get("signal_ratio_pct", "0.0%")
        act_findings = evaluation.get("actionable_findings", 0)
        top_must_fix = risk.get("top_must_fix", [])

        # Color for release badge
        status_color = P["accent"]
        if "BLOCK" in release_status:
            status_color = P["security"]
        elif "REVIEW" in release_status:
            status_color = P["bug"]

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.markdown(
                f"""
                <div class="cyber-metric-card" style="border-top: 3px solid {status_color};">
                    <div class="cyber-metric-title">Release Risk</div>
                    <div class="cyber-metric-value">{total_risk}</div>
                    <div style="display:inline-block; margin-top:4px; padding: 3px 8px; border-radius: 6px; font-weight:bold; font-size:0.8rem; border: 1px solid {status_color}; color: {status_color};">
                        {release_status}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with m2:
            st.markdown(
                f"""
                <div class="cyber-metric-card" style="border-top: 3px solid {P['accent']};">
                    <div class="cyber-metric-title">Signal Ratio</div>
                    <div class="cyber-metric-value" style="color: {P['accent']};">{sig_ratio_pct}</div>
                    <div class="cyber-metric-sub">{act_findings} actionable / {len(findings)} total</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with m3:
            st.markdown(
                f"""
                <div class="cyber-metric-card" style="border-top: 3px solid {P['performance']};">
                    <div class="cyber-metric-title">Total Findings</div>
                    <div class="cyber-metric-value">{len(findings)}</div>
                    <div class="cyber-metric-sub">Across all categories</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with m4:
            st.markdown(
                f"""
                <div class="cyber-metric-card" style="border-top: 3px solid {P['security']};">
                    <div class="cyber-metric-title">Must-Fix Items</div>
                    <div class="cyber-metric-value" style="color: {P['security']};">{len(top_must_fix)}</div>
                    <div class="cyber-metric-sub">Highest release impact</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Executive Summary & Quick Actions
        st.markdown(
            f"""
            <div class="cyber-card" style="margin-top: 1.5rem;">
                <h3 style="margin: 0 0 0.5rem 0; font-size: 1.15rem; color: {P['primary_text']};">
                    📋 AI Review Summary
                </h3>
                <p style="margin: 0; font-size: 1.05rem; color: {P['secondary_text']}; line-height: 1.5;">
                    {review_data.get('summary', 'No summary provided.')}
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("📊 View Deep Risk Analysis ➔", use_container_width=True):
                st.session_state["active_page"] = "Risk Analysis"
                st.rerun()
        with col_b:
            if st.button("⚠️ Inspect All Prioritized Findings ➔", use_container_width=True):
                st.session_state["active_page"] = "Findings"
                st.rerun()

    else:
        # Elegant Cybersecurity Empty State
        st.markdown(
            f"""
            <div class="cyber-card" style="text-align: center; padding: 3.5rem 1.5rem; margin-top: 1.5rem;">
                <div style="font-size: 3.5rem; margin-bottom: 0.75rem;">🛡️</div>
                <h2 style="margin: 0; color: {P['primary_text']}; font-size: 1.7rem;">System Ready for Review</h2>
                <p style="margin: 0.6rem auto 1.5rem auto; color: {P['secondary_text']}; font-size: 1.05rem; max-width: 600px;">
                    Enter any public GitHub Pull Request or Commit URL above, or switch to <strong>Code Review</strong> in the sidebar to run static analysis and AI release-risk scoring.
                </p>
                <div style="display: inline-flex; gap: 15px; font-size: 0.9rem; color: {P['muted_text']};">
                    <span>⚡ Google Gemini Primary</span>
                    <span>•</span>
                    <span>⚡ Groq Fallback</span>
                    <span>•</span>
                    <span>⚡ Ruff + Bandit + ESLint</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# View 2: Code Review
# ---------------------------------------------------------------------------
def render_code_review():
    """Dedicated screen for submitting and inspecting GitHub code reviews."""
    st.markdown(
        f"""
        <div style="margin-bottom: 1.5rem; padding-bottom: 0.85rem; border-bottom: 1px solid {P['border']};">
            <h1 style="margin: 0; font-size: 2.1rem; font-weight: bold; color: {P['primary_text']};">
                🔍 Code Review Console
            </h1>
            <p style="margin: 0.35rem 0 0 0; font-size: 1.05rem; color: {P['secondary_text']};">
                Targeted pull request and commit inspection with multimodal AI code impact analysis.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="cyber-card">
            <div style="font-weight: bold; font-size: 1.05rem; color: {P['primary_text']}; margin-bottom: 0.35rem;">
                GitHub Pull Request or Commit Target
            </div>
            <div style="font-size: 0.9rem; color: {P['secondary_text']}; margin-bottom: 0.75rem;">
                Paste any public repository URL. The ingestion pipeline extracts changed files, applies line truncation limits, and runs automated analyzers.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_input, col_action = st.columns([5, 1.3])
    with col_input:
        target_url = st.text_input(
            "Target URL",
            value=st.session_state.get("target_url", ""),
            placeholder="https://github.com/pallets/flask/pull/6162",
            label_visibility="collapsed",
            key="cr_url_input",
        )
    with col_action:
        submit_btn = st.button("Run Review", key="cr_submit_btn", use_container_width=True)

    if submit_btn:
        if not target_url.strip():
            st.error("Please enter a valid GitHub URL.")
        else:
            st.session_state["target_url"] = target_url.strip()
            with st.status("Performing automated review...", expanded=True) as status:
                st.write("Fetching changes from GitHub...")
                try:
                    result = call_backend_review({"url": target_url.strip()})
                    st.session_state["review_result"] = result
                    status.update(label="Analysis complete!", state="complete", expanded=False)
                    st.rerun()
                except Exception as e:
                    status.update(label="Review failed", state="error", expanded=True)
                    st.error(f"Review error: {e}")

    review_data = st.session_state.get("review_result")
    if review_data:
        st.markdown("---")
        render_provider_status(review_data)

        # Overview Grid
        findings = review_data.get("findings", [])
        risk = review_data.get("risk", {})

        st.markdown(
            f"""
            <div class="cyber-card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
                    <div style="font-size: 1.15rem; font-weight: bold; color: {P['primary_text']};">
                        Review Summary & Diagnostic Findings
                    </div>
                    <span class="status-pill pill-accent">
                        {len(findings)} Findings Total
                    </span>
                </div>
                <div style="font-size: 1.05rem; color: {P['primary_text']}; line-height: 1.5; margin-bottom: 1rem;">
                    {review_data.get('summary', 'No summary generated.')}
                </div>
                <div style="font-size: 0.85rem; color: {P['secondary_text']}; border-top: 1px solid {P['border']}; padding-top: 0.75rem;">
                    Evaluated against: <code>{st.session_state.get('target_url')}</code>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("📊 Open Risk Breakdown ➔", key="cr_goto_risk", use_container_width=True):
                st.session_state["active_page"] = "Risk Analysis"
                st.rerun()
        with col2:
            if st.button("⚠️ View Individual Findings ➔", key="cr_goto_findings", use_container_width=True):
                st.session_state["active_page"] = "Findings"
                st.rerun()
    else:
        st.info("No active review loaded. Enter a GitHub URL above and click **Run Review**.")


# ---------------------------------------------------------------------------
# View 3: Risk Analysis
# ---------------------------------------------------------------------------
def render_risk_analysis():
    """Dedicated screen for explainable release-risk scoring and weighted breakdowns."""
    st.markdown(
        f"""
        <div style="margin-bottom: 1.5rem; padding-bottom: 0.85rem; border-bottom: 1px solid {P['border']};">
            <h1 style="margin: 0; font-size: 2.1rem; font-weight: bold; color: {P['primary_text']};">
                📊 Explainable Release-Risk Engine
            </h1>
            <p style="margin: 0.35rem 0 0 0; font-size: 1.05rem; color: {P['secondary_text']};">
                Deterministic mathematical scoring with weighted category multipliers and release gates.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    review_data = st.session_state.get("review_result")
    if not review_data:
        st.warning("⚠️ No active code review loaded. Run a review from the **Dashboard** or **Code Review** tab first.")
        return

    risk = review_data.get("risk", {})
    total_risk = risk.get("total_risk", 0)
    release_status = risk.get("release_status", "SAFE TO RELEASE")
    breakdown = risk.get("breakdown", {})
    top_must_fix = risk.get("top_must_fix", [])

    status_color = P["accent"]
    if "BLOCK" in release_status:
        status_color = P["security"]
    elif "REVIEW" in release_status:
        status_color = P["bug"]

    # Top Hero Score Card
    st.markdown(
        f"""
        <div class="cyber-card" style="text-align: center; padding: 2rem; border-top: 4px solid {status_color};">
            <div style="font-size: 0.95rem; font-weight: bold; color: {P['secondary_text']}; letter-spacing: 1.5px; text-transform: uppercase;">
                TOTAL RELEASE-RISK SCORE
            </div>
            <div style="font-size: 4rem; font-weight: bold; color: {P['primary_text']}; margin: 0.25rem 0;">
                {total_risk}
            </div>
            <div style="display: inline-block; padding: 0.4rem 1.25rem; border-radius: 8px; font-weight: bold; font-size: 1.1rem; border: 2px solid {status_color}; color: {status_color}; background: rgba(0,0,0,0.06);">
                {release_status}
            </div>
            <p style="font-size: 0.95rem; color: {P['muted_text']}; margin: 0.75rem auto 0 auto; max-width: 550px;">
                Calculated strictly by the Stage 4 deterministic risk scoring formula without LLM hallucinations.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Weighted Category Breakdown Cards
    st.markdown(f"<h3 style='margin: 1.5rem 0 1rem 0; color:{P['primary_text']};'>📐 Weighted Category Breakdown</h3>", unsafe_allow_html=True)

    sec = breakdown.get("security", {"count": 0, "weight": 3, "score": 0})
    bug = breakdown.get("bug", {"count": 0, "weight": 2, "score": 0})
    perf = breakdown.get("performance", {"count": 0, "weight": 1.5, "score": 0})
    sty = breakdown.get("style", {"count": 0, "weight": 0.5, "score": 0})

    b1, b2, b3, b4 = st.columns(4)
    with b1:
        st.markdown(
            f"""
            <div class="cyber-card" style="border-left: 4px solid {P['security']};">
                <span class="status-pill pill-security">SECURITY</span>
                <div style="font-size: 1.8rem; font-weight: bold; color: {P['primary_text']}; margin: 0.5rem 0 0.2rem 0;">
                    {sec['score']} <span style="font-size: 0.9rem; color:{P['secondary_text']};">pts</span>
                </div>
                <div style="font-size: 0.9rem; color: {P['secondary_text']};">
                    {sec['count']} issues × 3.0 weight
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with b2:
        st.markdown(
            f"""
            <div class="cyber-card" style="border-left: 4px solid {P['bug']};">
                <span class="status-pill pill-bug">BUG</span>
                <div style="font-size: 1.8rem; font-weight: bold; color: {P['primary_text']}; margin: 0.5rem 0 0.2rem 0;">
                    {bug['score']} <span style="font-size: 0.9rem; color:{P['secondary_text']};">pts</span>
                </div>
                <div style="font-size: 0.9rem; color: {P['secondary_text']};">
                    {bug['count']} issues × 2.0 weight
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with b3:
        st.markdown(
            f"""
            <div class="cyber-card" style="border-left: 4px solid {P['performance']};">
                <span class="status-pill pill-performance">PERFORMANCE</span>
                <div style="font-size: 1.8rem; font-weight: bold; color: {P['primary_text']}; margin: 0.5rem 0 0.2rem 0;">
                    {perf['score']} <span style="font-size: 0.9rem; color:{P['secondary_text']};">pts</span>
                </div>
                <div style="font-size: 0.9rem; color: {P['secondary_text']};">
                    {perf['count']} issues × 1.5 weight
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with b4:
        st.markdown(
            f"""
            <div class="cyber-card" style="border-left: 4px solid {P['style']};">
                <span class="status-pill pill-style">STYLE</span>
                <div style="font-size: 1.8rem; font-weight: bold; color: {P['primary_text']}; margin: 0.5rem 0 0.2rem 0;">
                    {sty['score']} <span style="font-size: 0.9rem; color:{P['secondary_text']};">pts</span>
                </div>
                <div style="font-size: 0.9rem; color: {P['secondary_text']};">
                    {sty['count']} issues × 0.5 weight
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Top 3 Must-Fix Section
    if top_must_fix:
        st.markdown(f"<h3 style='margin: 1.8rem 0 0.75rem 0; color:{P['primary_text']};'>🚨 Top 3 Must-Fix Findings</h3>", unsafe_allow_html=True)
        col_must = st.columns(min(len(top_must_fix), 3))
        for idx, item in enumerate(top_must_fix[:3]):
            cat = str(item.get("category", "bug")).lower()
            color = P.get(cat, P["bug"])
            conf = item.get("confidence", "high")
            with col_must[idx]:
                st.markdown(
                    f"""
                    <div class="cyber-card" style="border-top: 4px solid {color}; height: 100%;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                            <span class="status-pill pill-{cat}">{cat.upper()}</span>
                            <span style="font-size: 0.8rem; color: {P['secondary_text']}; font-weight: bold;">
                                CONF: {conf.upper()}
                            </span>
                        </div>
                        <div style="font-weight: bold; font-size: 1rem; color: {P['primary_text']}; margin-bottom: 0.35rem;">
                            📁 {item.get('file', 'unknown')}:{item.get('line', 0)}
                        </div>
                        <div style="font-size: 0.95rem; color: {P['primary_text']}; margin: 0.35rem 0;">
                            <strong>Problem:</strong> {item.get('problem') or item.get('explanation', '')}
                        </div>
                        <div style="font-size: 0.9rem; color: {color}; margin: 0.35rem 0;">
                            <strong>Impact:</strong> {item.get('impact', 'Potential risk to project stability.')}
                        </div>
                        <div style="font-size: 0.9rem; color: {P['accent']}; margin-top: 0.5rem;">
                            💡 <strong>Fix:</strong> {item.get('suggested_fix', '')}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


# ---------------------------------------------------------------------------
# View 4: Findings
# ---------------------------------------------------------------------------
def render_findings():
    """Dedicated screen for inspecting all findings in strict priority order."""
    st.markdown(
        f"""
        <div style="margin-bottom: 1.5rem; padding-bottom: 0.85rem; border-bottom: 1px solid {P['border']};">
            <h1 style="margin: 0; font-size: 2.1rem; font-weight: bold; color: {P['primary_text']};">
                ⚠️ Prioritized Code Findings
            </h1>
            <p style="margin: 0.35rem 0 0 0; font-size: 1.05rem; color: {P['secondary_text']};">
                Findings ordered strictly by deterministic category priority: Security ➔ Bug ➔ Performance ➔ Style.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    review_data = st.session_state.get("review_result")
    if not review_data:
        st.warning("⚠️ No active code review loaded. Run a review from the **Dashboard** or **Code Review** tab first.")
        return

    all_findings = review_data.get("findings", [])
    if not all_findings:
        st.info("✅ No issues detected in the reviewed changes.")
        return

    # Category Filter Pills
    filter_col1, filter_col2 = st.columns([4, 1])
    with filter_col1:
        cat_choices = ["All", "Security", "Bug", "Performance", "Style"]
        chosen_cat = st.radio(
            "Category Filter",
            options=cat_choices,
            horizontal=True,
            index=cat_choices.index(st.session_state["findings_filter"]) if st.session_state["findings_filter"] in cat_choices else 0,
            key="cat_filter_radio",
        )
        st.session_state["findings_filter"] = chosen_cat

    # Filter findings
    if chosen_cat == "All":
        filtered = all_findings
    else:
        filtered = [f for f in all_findings if str(f.get("category", "")).lower() == chosen_cat.lower()]

    st.markdown(f"<p style='color:{P['secondary_text']}; font-size:0.95rem; margin-top:0.5rem;'>Showing <strong>{len(filtered)}</strong> of {len(all_findings)} findings</p>", unsafe_allow_html=True)

    for idx, item in enumerate(filtered, 1):
        cat = str(item.get("category", "style")).lower()
        color = P.get(cat, P["style"])
        source = item.get("source", "static")
        rule_id = item.get("rule_id")
        evidence = item.get("evidence", "")
        problem = item.get("problem") or item.get("explanation", "")
        impact = item.get("impact", "")
        why_it_happens = item.get("why_it_happens", "")
        fix = item.get("suggested_fix", "")
        conf = item.get("confidence", "moderate")

        # Source badge formatting
        if source == "static":
            source_badge = f"static: {rule_id if rule_id else 'analyzer'}"
        else:
            source_badge = f"llm: {evidence[:25] + '...' if len(evidence) > 25 else (evidence if evidence else 'AI review')}"

        st.markdown(
            f"""
            <div class="cyber-card" style="border-left: 5px solid {color}; margin-bottom: 1.25rem;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                    <div>
                        <span class="status-pill pill-{cat}">{cat.upper()}</span>
                        <span style="margin-left: 0.6rem; font-size: 0.85rem; font-family: monospace !important; color: {P['secondary_text']}; background: rgba(0,0,0,0.06); padding: 2px 6px; border-radius: 4px;">
                            {source_badge}
                        </span>
                    </div>
                    <div style="font-size: 0.85rem; color: {P['secondary_text']}; font-weight: bold;">
                        CONFIDENCE: {conf.upper()}
                    </div>
                </div>
                <div style="font-weight: bold; font-size: 1.15rem; color: {P['primary_text']}; margin: 0.35rem 0;">
                    📁 {item.get('file', 'unknown')} <span style="color:{P['muted_text']}; font-size:0.95rem;">(Line {item.get('line', 0)})</span>
                </div>
                <div style="margin: 0.4rem 0; font-size: 1.05rem; color: {P['primary_text']}; line-height: 1.4;">
                    <strong>Problem:</strong> {problem}
                </div>
                {f'<div class="evidence-box"><strong>Evidence:</strong> <code>{evidence}</code></div>' if evidence else ''}
                {f'<div style="margin: 0.4rem 0; font-size: 0.95rem; color: {color};"><strong>Impact:</strong> {impact}</div>' if impact else ''}
                {f'<div style="margin: 0.4rem 0; font-size: 0.95rem; color: {P["secondary_text"]};"><strong>Why it happens:</strong> {why_it_happens}</div>' if why_it_happens else ''}
                <div style="margin-top: 0.5rem; font-size: 0.95rem; color: {P['accent']};">
                    💡 <strong>Suggested Fix:</strong> {fix}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# View 5: Test Evaluation
# ---------------------------------------------------------------------------
def render_test_evaluation():
    """Dedicated screen for empirical test evaluation and ground-truth metrics."""
    st.markdown(
        f"""
        <div style="margin-bottom: 1.5rem; padding-bottom: 0.85rem; border-bottom: 1px solid {P['border']};">
            <h1 style="margin: 0; font-size: 2.1rem; font-weight: bold; color: {P['primary_text']};">
                🧪 Test Harness & Evaluation Metrics
            </h1>
            <p style="margin: 0.35rem 0 0 0; font-size: 1.05rem; color: {P['secondary_text']};">
                Empirical validation of precision, recall, and signal ratio against hand-tagged ground truth.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="cyber-card">
            <div style="font-weight: bold; font-size: 1.05rem; color: {P['primary_text']}; margin-bottom: 0.35rem;">
                Empirical Evaluation Benchmark
            </div>
            <div style="font-size: 0.95rem; color: {P['secondary_text']}; margin-bottom: 1rem;">
                Run automated testing against the built-in hand-tagged dataset containing security vulnerabilities, logic defects, and clean controls.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("Run Benchmark Evaluation", key="eval_run_btn"):
        with st.spinner("Executing evaluation harness across dataset..."):
            try:
                res = call_backend_evaluate()
                st.session_state["eval_benchmark_result"] = res
                st.success("Benchmark evaluation completed successfully!")
            except Exception as e:
                st.error(f"Evaluation error: {e}")

    # Check whether we have benchmark results or review evaluation data
    eval_data = st.session_state.get("eval_benchmark_result")
    review_data = st.session_state.get("review_result")

    if not eval_data and review_data:
        eval_data = review_data.get("evaluation")

    if eval_data:
        prec = eval_data.get("precision", 0.0)
        rec = eval_data.get("recall", 0.0)
        sig = eval_data.get("signal_ratio", 0.0)
        sig_pct = eval_data.get("signal_ratio_pct", f"{sig:.1%}")
        tp = eval_data.get("true_positives", 0)
        fp = eval_data.get("false_positives", 0)
        fn = eval_data.get("false_negatives", 0)
        act = eval_data.get("actionable_findings", 0)
        total = eval_data.get("total_findings", 0)

        st.markdown(f"<h3 style='margin: 1.5rem 0 1rem 0; color:{P['primary_text']};'>📊 Quality & Accuracy Metrics</h3>", unsafe_allow_html=True)

        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(
                f"""
                <div class="cyber-metric-card" style="border-top: 3px solid {P['accent']};">
                    <div class="cyber-metric-title">PRECISION</div>
                    <div class="cyber-metric-value">{prec:.1%}</div>
                    <div class="cyber-metric-sub">TP / (TP + FP)</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with c2:
            st.markdown(
                f"""
                <div class="cyber-metric-card" style="border-top: 3px solid {P['performance']};">
                    <div class="cyber-metric-title">RECALL</div>
                    <div class="cyber-metric-value">{rec:.1%}</div>
                    <div class="cyber-metric-sub">TP / (TP + FN)</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with c3:
            st.markdown(
                f"""
                <div class="cyber-metric-card" style="border-top: 3px solid {P['bug']};">
                    <div class="cyber-metric-title">SIGNAL RATIO</div>
                    <div class="cyber-metric-value" style="color: {P['accent']};">{sig_pct}</div>
                    <div class="cyber-metric-sub">{act} Actionable / {total} Total</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown(f"<h3 style='margin: 1.5rem 0 1rem 0; color:{P['primary_text']};'>🎯 Confusion Matrix Counts</h3>", unsafe_allow_html=True)
        cm1, cm2, cm3 = st.columns(3)
        with cm1:
            st.markdown(
                f"""
                <div class="cyber-card" style="text-align: center;">
                    <div style="color: {P['accent']}; font-weight: bold; font-size: 0.9rem;">TRUE POSITIVES (TP)</div>
                    <div style="font-size: 2.5rem; font-weight: bold; color: {P['primary_text']};">{tp}</div>
                    <div style="color: {P['secondary_text']}; font-size: 0.85rem;">Correctly identified real issues</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with cm2:
            st.markdown(
                f"""
                <div class="cyber-card" style="text-align: center;">
                    <div style="color: {P['bug']}; font-weight: bold; font-size: 0.9rem;">FALSE POSITIVES (FP)</div>
                    <div style="font-size: 2.5rem; font-weight: bold; color: {P['primary_text']};">{fp}</div>
                    <div style="color: {P['secondary_text']}; font-size: 0.85rem;">Spurious findings not in ground truth</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with cm3:
            st.markdown(
                f"""
                <div class="cyber-card" style="text-align: center;">
                    <div style="color: {P['security']}; font-weight: bold; font-size: 0.9rem;">FALSE NEGATIVES (FN)</div>
                    <div style="font-size: 2.5rem; font-weight: bold; color: {P['primary_text']};">{fn}</div>
                    <div style="color: {P['secondary_text']}; font-size: 0.85rem;">Expected issues that were missed</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.info("Click **Run Benchmark Evaluation** above to run the test suite against the ground truth dataset.")


# ---------------------------------------------------------------------------
# Sidebar Navigation & Persistent Controls
# ---------------------------------------------------------------------------
def render_sidebar():
    """Renders the persistent sidebar with brand logo, navigation buttons, and theme toggle."""
    with st.sidebar:
        # 1. Branding & Logo (Original logo preserved without alteration)
        logo_png = Path(__file__).resolve().parent / "assets" / "logo.png"
        logo_svg = Path(__file__).resolve().parent / "assets" / "logo.svg"

        if logo_png.exists():
            st.image(str(logo_png), use_container_width=True)
        elif logo_svg.exists():
            st.image(str(logo_svg), use_container_width=True)
        else:
            st.markdown(
                f"""
                <div style="padding: 10px 0; border-bottom: 1px solid {P['border']}; margin-bottom: 15px;">
                    <div style="font-size: 1.3rem; font-weight: bold; letter-spacing: 1px; color: {P['primary_text']};">
                        🛡️ AI CODE REVIEW
                    </div>
                    <div style="font-size: 0.85rem; color: {P['secondary_text']};">
                        Release-Risk Assistant
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # 2. True Single-Screen Navigation System
        st.markdown(
            f"<p style='color:{P['secondary_text']}; font-size:0.8rem; font-weight:bold; letter-spacing:1px; margin: 15px 0 8px 0;'>NAVIGATION</p>",
            unsafe_allow_html=True,
        )

        nav_options = [
            ("Dashboard", "🏠  Dashboard"),
            ("Code Review", "🔍  Code Review"),
            ("Risk Analysis", "📊  Risk Analysis"),
            ("Findings", "⚠️  Findings"),
            ("Test Evaluation", "🧪  Test Evaluation"),
        ]

        current_active = st.session_state["active_page"]

        for page_id, label in nav_options:
            is_active = (current_active == page_id)
            btn_type = "primary" if is_active else "secondary"
            if st.button(label, key=f"nav_btn_{page_id}", type=btn_type, use_container_width=True):
                if st.session_state["active_page"] != page_id:
                    st.session_state["active_page"] = page_id
                    st.rerun()

        st.markdown("---")

        # 3. Theme Toggle
        st.markdown(
            f"<p style='color:{P['secondary_text']}; font-size:0.8rem; font-weight:bold; letter-spacing:1px;'>INTERFACE THEME</p>",
            unsafe_allow_html=True,
        )
        theme_choice = st.radio(
            "Select Theme",
            options=["Dark", "Light"],
            index=0 if st.session_state["theme"] == "Dark" else 1,
            label_visibility="collapsed",
            key="theme_radio_select",
        )
        if theme_choice != st.session_state["theme"]:
            st.session_state["theme"] = theme_choice
            st.rerun()

        st.markdown("---")

        # 4. System Status Indicator
        st.markdown(
            f"""
            <div style="font-size:0.82rem; color:{P['secondary_text']}; line-height: 1.6;">
                <div><span class="pulse-dot"></span> Backend: <span style="color:{P['accent']}; font-weight:bold;">Online</span></div>
                <div style="font-size:0.75rem; color:{P['muted_text']}; font-family: monospace;">{BACKEND_URL}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Main Routing Logic
# ---------------------------------------------------------------------------
render_sidebar()

active_page = st.session_state["active_page"]

if active_page == "Dashboard":
    render_dashboard()
elif active_page == "Code Review":
    render_code_review()
elif active_page == "Risk Analysis":
    render_risk_analysis()
elif active_page == "Findings":
    render_findings()
elif active_page == "Test Evaluation":
    render_test_evaluation()
