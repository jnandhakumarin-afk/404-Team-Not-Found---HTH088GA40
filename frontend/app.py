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
# Streamlit Page Config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="AI Code Review & Release-Risk Assistant",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Theme Management via Session State
# ---------------------------------------------------------------------------
if "theme" not in st.session_state:
    st.session_state["theme"] = "Dark"

if "review_result" not in st.session_state:
    st.session_state["review_result"] = None

if "eval_benchmark_result" not in st.session_state:
    st.session_state["eval_benchmark_result"] = None

# Color palette definitions matching design specifications
PALETTES = {
    "Dark": {
        "bg": "#1A1B25",
        "card_bg": "#232530",
        "border": "#3A3D4D",
        "primary_text": "#E8E9F1",
        "secondary_text": "#8A8FA3",
        "accent": "#2DD4BF",
        "security": "#F4534F",
        "bug": "#FF9838",
        "performance": "#54A1FF",
        "style": "#8A8FA3",
        "action_btn": "#2DD4BF",
        "action_text": "#1A1B25",
    },
    "Light": {
        "bg": "#F4F6F8",
        "card_bg": "#FFFFFF",
        "border": "#D9DDE5",
        "primary_text": "#1A1B25",
        "secondary_text": "#667085",
        "accent": "#2DD4BF",
        "security": "#F4534F",
        "bug": "#FF9838",
        "performance": "#54A1FF",
        "style": "#8A8FA3",
        "action_btn": "#159F91",
        "action_text": "#FFFFFF",
    },
}

current_theme = st.session_state["theme"]
P = PALETTES[current_theme]

# ---------------------------------------------------------------------------
# Global Typography & Style Injection (Times New Roman throughout)
# ---------------------------------------------------------------------------
GLOBAL_CSS = f"""
<style>
/* Universal Times New Roman Typography */
html, body, [class*="css"], .stApp, h1, h2, h3, h4, h5, h6, p, div, span, button, input, textarea, label, [data-testid="stSidebar"] {{
    font-family: "Times New Roman", Times, serif !important;
}}

/* Main Application Background & Text */
.stApp {{
    background-color: {P["bg"]} !important;
    color: {P["primary_text"]} !important;
}}

/* Sidebar Styling */
[data-testid="stSidebar"] {{
    background-color: {P["card_bg"]} !important;
    border-right: 1px solid {P["border"]} !important;
}}

/* Inputs */
.stTextInput > div > div > input {{
    background-color: {P["card_bg"]} !important;
    color: {P["primary_text"]} !important;
    border: 1px solid {P["border"]} !important;
    border-radius: 8px !important;
    font-size: 1rem !important;
}}

/* Buttons */
.stButton > button {{
    background-color: {P["action_btn"]} !important;
    color: {P["action_text"]} !important;
    font-weight: bold !important;
    border-radius: 8px !important;
    border: none !important;
    padding: 0.5rem 1.5rem !important;
    transition: all 0.2s ease-in-out !important;
}}

.stButton > button:hover {{
    opacity: 0.9 !important;
    transform: translateY(-1px) !important;
}}

/* Custom Cards */
.review-card {{
    background-color: {P["card_bg"]};
    border: 1px solid {P["border"]};
    border-radius: 10px;
    padding: 1.25rem;
    margin-bottom: 1rem;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}}

.metric-pill {{
    display: inline-block;
    padding: 0.25rem 0.6rem;
    border-radius: 6px;
    font-size: 0.85rem;
    font-weight: bold;
    text-transform: uppercase;
}}

.tag-security {{
    background-color: rgba(244, 83, 79, 0.15);
    color: {P["security"]};
    border: 1px solid {P["security"]};
}}

.tag-bug {{
    background-color: rgba(255, 152, 56, 0.15);
    color: {P["bug"]};
    border: 1px solid {P["bug"]};
}}

.tag-performance {{
    background-color: rgba(84, 161, 255, 0.15);
    color: {P["performance"]};
    border: 1px solid {P["performance"]};
}}

.tag-style {{
    background-color: rgba(138, 143, 163, 0.15);
    color: {P["style"]};
    border: 1px solid {P["style"]};
}}

.evidence-box {{
    background-color: rgba(0,0,0,0.15);
    border-left: 3px solid {P["border"]};
    padding: 0.5rem 0.75rem;
    font-family: monospace !important;
    font-size: 0.88rem;
    margin: 0.5rem 0;
    overflow-x: auto;
}}
</style>
"""
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helper API Functions
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
# Sidebar (Branding, Navigation Anchors, Theme Toggle)
# ---------------------------------------------------------------------------
with st.sidebar:
    # 1. Branding & Logo
    logo_path_png = Path(__file__).resolve().parent / "assets" / "logo.png"
    logo_path_svg = Path(__file__).resolve().parent / "assets" / "logo.svg"

    if logo_path_png.exists():
        st.image(str(logo_path_png), use_container_width=True)
    elif logo_path_svg.exists():
        st.image(str(logo_path_svg), use_container_width=True)
    else:
        st.markdown(
            f"""
            <div style="padding: 10px 0; border-bottom: 1px solid {P['border']}; margin-bottom: 15px;">
                <div style="font-size: 1.3rem; font-weight: bold; letter-spacing: 1px; color: {P['primary_text']};">
                    🛡️ AI CODE REVIEW
                </div>
                <div style="font-size: 0.9rem; color: {P['secondary_text']};">
                    Release-Risk Assistant
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 2. Visual Navigation Sections
    st.markdown(f"<p style='color:{P['secondary_text']}; font-size:0.85rem; font-weight:bold; margin-top:10px;'>NAVIGATION</p>", unsafe_allow_html=True)
    st.markdown("🏠 **Dashboard**")
    st.markdown("🔍 **Code Review**")
    st.markdown("📊 **Risk Analysis**")
    st.markdown("⚠️ **Findings**")
    st.markdown("🧪 **Test Evaluation**")

    st.markdown("---")

    # 3. Theme Toggle (Must actually work & persist in session_state)
    st.markdown(f"<p style='color:{P['secondary_text']}; font-size:0.85rem; font-weight:bold;'>INTERFACE THEME</p>", unsafe_allow_html=True)
    selected_theme = st.radio(
        "Select Theme",
        options=["Dark", "Light"],
        index=0 if st.session_state["theme"] == "Dark" else 1,
        label_visibility="collapsed",
    )
    if selected_theme != st.session_state["theme"]:
        st.session_state["theme"] = selected_theme
        st.rerun()

    st.markdown("---")
    st.markdown(
        f"<div style='font-size:0.8rem; color:{P['secondary_text']};'>"
        f"Backend: <code>{BACKEND_URL}</code><br>"
        f"Status: <span style='color:{P['accent']};'>Online</span>"
        f"</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Main Content Area
# ---------------------------------------------------------------------------

# Section 1: Main Header
st.markdown(
    f"""
    <div style="margin-bottom: 1.5rem; padding-bottom: 0.75rem; border-bottom: 1px solid {P['border']};">
        <h1 style="margin: 0; font-size: 2.2rem; color: {P['primary_text']};">
            AI Code Review & Release-Risk Assistant
        </h1>
        <p style="margin: 0.35rem 0 0 0; font-size: 1.05rem; color: {P['secondary_text']};">
            Automated code analysis, AI-assisted review, and deterministic release-risk scoring.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Section 2 & 3: GitHub PR / Commit Input & Review Button
st.markdown(f"<h3 style='margin-bottom:0.5rem; color:{P['primary_text']};'>GitHub Pull Request / Commit URL</h3>", unsafe_allow_html=True)

col_input, col_btn = st.columns([5, 1])
with col_input:
    github_url = st.text_input(
        "GitHub Pull Request / Commit URL",
        placeholder="https://github.com/owner/repository/pull/123 or https://github.com/owner/repository/commit/...",
        label_visibility="collapsed",
    )

with col_btn:
    review_clicked = st.button("Review Code", use_container_width=True)

# Trigger review
if review_clicked:
    if not github_url or not github_url.strip():
        st.error("Please enter a valid GitHub Pull Request or Commit URL.")
    else:
        with st.status("Analyzing codebase...", expanded=True) as status:
            st.write("Fetching changed files from GitHub...")
            try:
                st.write("Running static code analysis (Ruff, Bandit, ESLint)...")
                st.write("Generating contextual AI code review...")
                st.write("Calculating deterministic release risk...")
                st.write("Preparing report...")

                result = call_backend_review({"url": github_url.strip()})
                st.session_state["review_result"] = result
                status.update(label="Review complete!", state="complete", expanded=False)
            except Exception as e:
                status.update(label="Review failed", state="error", expanded=True)
                st.error(f"Unable to review this GitHub URL: {e}")

# Check review results in session state
review_data = st.session_state.get("review_result")

if review_data is None:
    # Section 21: Professional Empty State
    st.markdown(
        f"""
        <div class="review-card" style="text-align: center; padding: 3rem 1.5rem; margin-top: 2rem;">
            <div style="font-size: 3rem; margin-bottom: 0.75rem;">🛡️</div>
            <h2 style="margin: 0; color: {P['primary_text']}; font-size: 1.6rem;">Ready to Review</h2>
            <p style="margin: 0.5rem 0 0 0; color: {P['secondary_text']}; font-size: 1.05rem;">
                Paste a public GitHub PR or commit URL to begin automated code analysis.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    # Extract components
    summary = review_data.get("summary", "")
    findings = review_data.get("findings", [])
    risk = review_data.get("risk", {})
    breakdown = risk.get("breakdown", {})
    total_risk = risk.get("total_risk", 0)
    release_status = risk.get("release_status", "SAFE TO RELEASE")
    top_must_fix = risk.get("top_must_fix", [])
    truncated_files = review_data.get("truncated_files", [])
    is_fallback = review_data.get("fallback_to_static", False)
    evaluation = review_data.get("evaluation", {})

    # Section 10 Notices: Truncation & Static Fallback
    if truncated_files:
        st.warning(
            f"⚠️ **Some changed files were truncated for analysis (capped at 500 lines):** "
            f"{', '.join(truncated_files)}"
        )

    provider = review_data.get("provider", "static")
    if not is_fallback:
        if provider == "gemini":
            st.success("✅ AI review powered by Gemini")
        elif provider == "groq":
            st.info("ℹ️ AI review powered by Groq fallback")
    else:
        st.info("ℹ️ AI review unavailable — showing static analysis findings.")

    st.markdown("---")

    # Section 4 & 6: Risk Score & Signal Ratio Metrics
    col_risk, col_breakdown = st.columns([1, 2])

    with col_risk:
        # Determine status badge color
        status_color = P["accent"]
        if "BLOCK" in release_status:
            status_color = P["security"]
        elif "REVIEW" in release_status:
            status_color = P["bug"]

        st.markdown(
            f"""
            <div class="review-card" style="text-align: center; height: 100%;">
                <div style="font-size: 0.9rem; font-weight: bold; color: {P['secondary_text']}; letter-spacing: 1px;">
                    RELEASE RISK
                </div>
                <div style="font-size: 3.5rem; font-weight: bold; color: {P['primary_text']}; margin: 0.25rem 0;">
                    {total_risk}
                </div>
                <div style="display: inline-block; padding: 0.35rem 0.9rem; border-radius: 8px; font-weight: bold; background: rgba(0,0,0,0.1); border: 1px solid {status_color}; color: {status_color}; font-size: 0.95rem;">
                    {release_status}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_breakdown:
        # Section 5: Weighted Risk Breakdown
        sec_bd = breakdown.get("security", {"count": 0, "weight": 3, "score": 0})
        bug_bd = breakdown.get("bug", {"count": 0, "weight": 2, "score": 0})
        perf_bd = breakdown.get("performance", {"count": 0, "weight": 1.5, "score": 0})
        style_bd = breakdown.get("style", {"count": 0, "weight": 0.5, "score": 0})

        st.markdown(
            f"""
            <div class="review-card">
                <div style="font-size: 1.1rem; font-weight: bold; margin-bottom: 0.75rem; color: {P['primary_text']};">
                    Weighted Risk Breakdown
                </div>
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px;">
                    <div style="padding: 8px 12px; border: 1px solid {P['border']}; border-radius: 8px;">
                        <span style="color: {P['security']}; font-weight: bold;">Security (×3):</span><br>
                        {sec_bd['count']} findings × 3 = <strong>{sec_bd['score']}</strong>
                    </div>
                    <div style="padding: 8px 12px; border: 1px solid {P['border']}; border-radius: 8px;">
                        <span style="color: {P['bug']}; font-weight: bold;">Bug (×2):</span><br>
                        {bug_bd['count']} findings × 2 = <strong>{bug_bd['score']}</strong>
                    </div>
                    <div style="padding: 8px 12px; border: 1px solid {P['border']}; border-radius: 8px;">
                        <span style="color: {P['performance']}; font-weight: bold;">Performance (×1.5):</span><br>
                        {perf_bd['count']} findings × 1.5 = <strong>{perf_bd['score']}</strong>
                    </div>
                    <div style="padding: 8px 12px; border: 1px solid {P['border']}; border-radius: 8px;">
                        <span style="color: {P['style']}; font-weight: bold;">Style (×0.5):</span><br>
                        {style_bd['count']} findings × 0.5 = <strong>{style_bd['score']}</strong>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Section 6: Signal Ratio Display
    act_findings = evaluation.get("actionable_findings", 0)
    total_findings_count = len(findings)
    sig_ratio_pct = evaluation.get("signal_ratio_pct", "0.0%")

    st.markdown(
        f"""
        <div class="review-card" style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <strong style="color: {P['primary_text']}; font-size: 1.1rem;">Signal Ratio:</strong>
                <span style="color: {P['secondary_text']}; font-size: 1.05rem; margin-left: 0.5rem;">
                    {act_findings} signal / {total_findings_count} total findings — 
                    <strong style="color: {P['accent']};">{sig_ratio_pct} actionable</strong>
                </span>
            </div>
            <div style="color: {P['secondary_text']}; font-size: 0.9rem;">
                Based on Stage 5 Evaluation Metrics
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Section 7: Top 3 Must-Fix Findings
    if top_must_fix:
        st.markdown(f"<h3 style='margin-top:1.5rem; color:{P['primary_text']};'>🚨 TOP 3 MUST-FIX</h3>", unsafe_allow_html=True)
        col_must = st.columns(min(len(top_must_fix), 3))
        for idx, item in enumerate(top_must_fix[:3]):
            cat = str(item.get("category", "bug")).lower()
            color = P.get(cat, P["bug"])
            conf = item.get("confidence", "high")
            with col_must[idx]:
                st.markdown(
                    f"""
                    <div class="review-card" style="border-top: 4px solid {color};">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                            <span class="metric-pill tag-{cat}">{cat.upper()}</span>
                            <span style="font-size: 0.85rem; color: {P['secondary_text']}; font-weight: bold;">
                                CONF: {conf.upper()}
                            </span>
                        </div>
                        <div style="font-weight: bold; font-size: 0.95rem; color: {P['primary_text']}; margin-bottom: 0.25rem;">
                            📁 {item.get('file', 'unknown')}:{item.get('line', 0)}
                        </div>
                        <div style="font-size: 0.92rem; color: {P['primary_text']}; margin: 0.25rem 0;">
                            <strong>Problem:</strong> {item.get('problem') or item.get('explanation', '')}
                        </div>
                        <div style="font-size: 0.88rem; color: {color}; margin: 0.25rem 0;">
                            <strong>Impact:</strong> {item.get('impact', 'Potential risk to project stability or security.')}
                        </div>
                        <div style="font-size: 0.85rem; color: {P['accent']}; margin-top: 0.4rem;">
                            💡 <strong>Fix:</strong> {item.get('suggested_fix', '')}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    # Section 8: All Findings in Strict Deterministic Order
    st.markdown(f"<h3 style='margin-top:1.5rem; color:{P['primary_text']};'>📋 All Findings ({len(findings)})</h3>", unsafe_allow_html=True)

    if not findings:
        st.info("No issues detected in the reviewed changes.")
    else:
        for idx, item in enumerate(findings, 1):
            cat = str(item.get("category", "style")).lower()
            color = P.get(cat, P["style"])
            source = item.get("source", "static")
            rule_id = item.get("rule_id")
            evidence = item.get("evidence", "")
            problem = item.get("problem") or item.get("explanation", "")
            impact = item.get("impact", "")
            why_it_happens = item.get("why_it_happens", "")
            fix = item.get("suggested_fix", "")

            # Format source display per requirement:
            # static: <rule_id> or llm: <evidence>
            if source == "static":
                source_display = f"static: {rule_id if rule_id else 'analyzer'}"
            else:
                source_display = f"llm: {evidence if evidence else 'AI review'}"

            st.markdown(
                f"""
                <div class="review-card" style="border-left: 4px solid {color};">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">
                        <div>
                            <span class="metric-pill tag-{cat}">{cat.upper()}</span>
                            <span style="margin-left: 0.5rem; font-size: 0.85rem; font-family: monospace !important; color: {P['secondary_text']};">
                                {source_display}
                            </span>
                        </div>
                        <div style="font-size: 0.85rem; color: {P['secondary_text']}; font-weight: bold;">
                            CONFIDENCE: {item.get('confidence', 'moderate').upper()}
                        </div>
                    </div>
                    <div style="font-weight: bold; font-size: 1.05rem; color: {P['primary_text']}; margin: 0.25rem 0;">
                        📁 {item.get('file', 'unknown')} (Line {item.get('line', 0)})
                    </div>
                    <div style="margin: 0.35rem 0; font-size: 0.95rem; color: {P['primary_text']};">
                        <strong>Problem:</strong> {problem}
                    </div>
                    {f'<div class="evidence-box"><strong>Evidence:</strong> <code>{evidence}</code></div>' if evidence else ''}
                    {f'<div style="margin: 0.35rem 0; font-size: 0.92rem; color: {color};"><strong>Impact:</strong> {impact}</div>' if impact else ''}
                    {f'<div style="margin: 0.35rem 0; font-size: 0.92rem; color: {P["secondary_text"]};"><strong>Why it happens:</strong> {why_it_happens}</div>' if why_it_happens else ''}
                    <div style="margin-top: 0.4rem; font-size: 0.92rem; color: {P['accent']};">
                        💡 <strong>Suggested Fix:</strong> {fix}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # Section 9 & 20: Test Evaluation Metrics
    st.markdown(f"<h3 style='margin-top:2rem; color:{P['primary_text']};'>🧪 Evaluation Metrics</h3>", unsafe_allow_html=True)
    col_p, col_r, col_s = st.columns(3)

    prec = evaluation.get("precision", 0.0)
    rec = evaluation.get("recall", 0.0)
    sig = evaluation.get("signal_ratio", 0.0)

    with col_p:
        st.markdown(
            f"""
            <div class="review-card" style="text-align: center;">
                <div style="color: {P['secondary_text']}; font-size: 0.9rem; font-weight: bold;">PRECISION</div>
                <div style="font-size: 2.2rem; font-weight: bold; color: {P['primary_text']};">{prec:.1%}</div>
                <div style="color: {P['secondary_text']}; font-size: 0.8rem;">TP / (TP + FP)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_r:
        st.markdown(
            f"""
            <div class="review-card" style="text-align: center;">
                <div style="color: {P['secondary_text']}; font-size: 0.9rem; font-weight: bold;">RECALL</div>
                <div style="font-size: 2.2rem; font-weight: bold; color: {P['primary_text']};">{rec:.1%}</div>
                <div style="color: {P['secondary_text']}; font-size: 0.8rem;">TP / (TP + FN)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_s:
        st.markdown(
            f"""
            <div class="review-card" style="text-align: center;">
                <div style="color: {P['secondary_text']}; font-size: 0.9rem; font-weight: bold;">SIGNAL RATIO</div>
                <div style="font-size: 2.2rem; font-weight: bold; color: {P['accent']};">{sig:.1%}</div>
                <div style="color: {P['secondary_text']}; font-size: 0.8rem;">Actionable / Total</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
