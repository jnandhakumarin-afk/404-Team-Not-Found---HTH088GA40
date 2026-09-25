import os
import re
import sys
import json
import html
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
    st.session_state["active_page"] = "Landing"

if "review_result" not in st.session_state:
    st.session_state["review_result"] = None

if "eval_benchmark_result" not in st.session_state:
    st.session_state["eval_benchmark_result"] = None

if "target_url" not in st.session_state:
    st.session_state["target_url"] = ""

if "findings_filter" not in st.session_state:
    st.session_state["findings_filter"] = "All"

if "test_cases" not in st.session_state:
    st.session_state["test_cases"] = []

if "stack_trace_result" not in st.session_state:
    st.session_state["stack_trace_result"] = None

if "active_fix" not in st.session_state:
    st.session_state["active_fix"] = None

if "applied_fixes" not in st.session_state:
    st.session_state["applied_fixes"] = []

if "fix_success_message" not in st.session_state:
    st.session_state["fix_success_message"] = None

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
        "shadow_card": "0 6px 18px -2px rgba(0,0,0,0.4), 0 2px 6px -1px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.05)",
        "shadow_elevated": "0 10px 28px -4px rgba(0,0,0,0.5), 0 4px 10px -2px rgba(0,0,0,0.35)",
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
        "shadow_card": "0 4px 16px -2px rgba(16,24,40,0.08), 0 1px 3px rgba(16,24,40,0.04), inset 0 1px 0 rgba(255,255,255,0.9)",
        "shadow_elevated": "0 8px 24px -4px rgba(16,24,40,0.12), 0 3px 8px -2px rgba(16,24,40,0.06)",
    },
}

current_theme = st.session_state["theme"]
P = PALETTES[current_theme]

# ---------------------------------------------------------------------------
# Global CSS — Layout, Spacing, Typography & Responsive System
# ---------------------------------------------------------------------------
GLOBAL_CSS = f"""
<style>
/* ── Universal Box Sizing & Fluid Reset ── */
*, *::before, *::after {{
    box-sizing: border-box !important;
}}

/* ── Typography: Times New Roman Enforced Universally ── */
html, body, [class*="css"], .stApp, h1, h2, h3, h4, h5, h6,
p, div, span, button, input, textarea, label,
[data-testid="stSidebar"], [data-testid="stExpander"],
[data-testid="stMarkdownContainer"] {{
    font-family: "Times New Roman", Times, serif !important;
}}

/* ── App Canvas ── */
.stApp {{
    background-color: {P["bg"]} !important;
    color: {P["primary_text"]} !important;
    overflow-x: hidden !important;
}}

/* ── Ensure block containers do not overflow horizontally ── */
.stApp [data-testid="stVerticalBlock"],
.stApp [data-testid="stHorizontalBlock"],
.stApp [data-testid="stColumn"] {{
    min-width: 0 !important;
    max-width: 100% !important;
}}

/* ── Sidebar ── */
[data-testid="stSidebar"] {{
    background-color: {P["card_bg"]} !important;
    border-right: 1px solid {P["border"]} !important;
    padding: 1rem 0.75rem !important;
    min-width: 250px !important;
}}
[data-testid="stSidebar"] hr {{
    border-color: {P["border"]} !important;
    margin: 0.85rem 0 !important;
}}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{
    gap: 0.4rem !important;
}}

/* ── Inputs ── */
.stTextInput > div > div > input {{
    background-color: {P["card_bg"]} !important;
    color: {P["primary_text"]} !important;
    border: 1px solid {P["border"]} !important;
    border-radius: 10px !important;
    font-size: 1rem !important;
    padding: 0.65rem 1rem !important;
    transition: all 0.2s ease !important;
    max-width: 100% !important;
}}
.stTextInput > div > div > input:focus {{
    border-color: {P["accent"]} !important;
    box-shadow: 0 0 0 2px {P["accent_glow"]} !important;
}}
.stTextInput label {{
    color: {P["primary_text"]} !important;
    font-weight: bold !important;
    margin-bottom: 0.25rem !important;
}}

/* ── Textarea ── */
.stTextArea > div > div > textarea {{
    background-color: {P["card_bg"]} !important;
    color: {P["primary_text"]} !important;
    border: 1px solid {P["border"]} !important;
    border-radius: 10px !important;
    font-size: 0.95rem !important;
    line-height: 1.5 !important;
    padding: 0.75rem 1rem !important;
    transition: all 0.2s ease !important;
    max-width: 100% !important;
}}
.stTextArea > div > div > textarea:focus {{
    border-color: {P["accent"]} !important;
    box-shadow: 0 0 0 2px {P["accent_glow"]} !important;
}}

/* ── Buttons ── */
.stButton > button {{
    border-radius: 10px !important;
    font-weight: bold !important;
    padding: 0.6rem 1.25rem !important;
    transition: all 0.2s cubic-bezier(0.16,1,0.3,1) !important;
    box-shadow: 0 2px 6px rgba(0,0,0,0.12) !important;
    letter-spacing: 0.3px !important;
    min-height: 2.6rem !important;
    word-break: normal !important;
}}
.stButton > button:hover {{
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 14px rgba(0,0,0,0.18) !important;
}}
.stButton > button:active {{
    transform: translateY(0) !important;
}}

/* ── Sidebar Nav Buttons ── */
[data-testid="stSidebar"] .stButton > button {{
    width: 100% !important;
    text-align: left !important;
    justify-content: flex-start !important;
    font-size: 0.95rem !important;
    border-radius: 8px !important;
    padding: 0.55rem 0.85rem !important;
    margin-bottom: 0.2rem !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
}}

/* ── Universal Cards ── */
.cyber-card {{
    background-color: {P["card_bg"]};
    border: 1px solid {P["border"]};
    border-radius: 12px;
    padding: 1.35rem 1.5rem;
    margin-bottom: 1.25rem;
    box-shadow: {P["shadow_card"]};
    min-width: 0;
    max-width: 100%;
    overflow-wrap: break-word;
    word-break: break-word;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}}
.cyber-card:hover {{
    box-shadow: {P["shadow_elevated"]};
}}

/* ── Metric Cards ── */
.cyber-metric-card {{
    background: {P["card_bg_elevated"]};
    border: 1px solid {P["border"]};
    border-radius: 12px;
    padding: 1.15rem 0.85rem;
    text-align: center;
    box-shadow: {P["shadow_card"]};
    position: relative;
    overflow: hidden;
    min-width: 0;
    max-width: 100%;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}}
.cyber-metric-card:hover {{
    transform: translateY(-2px);
    box-shadow: {P["shadow_elevated"]};
}}
.cyber-metric-title {{
    color: {P["secondary_text"]};
    font-size: 0.78rem;
    font-weight: bold;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    margin-bottom: 0.35rem;
    line-height: 1.3;
    overflow-wrap: break-word;
    word-break: break-word;
}}
.cyber-metric-value {{
    color: {P["primary_text"]};
    font-size: clamp(1.4rem, 2.2vw, 2.2rem);
    font-weight: bold;
    line-height: 1.15;
    margin-bottom: 0.25rem;
    overflow-wrap: break-word;
    word-break: break-word;
}}
.cyber-metric-sub {{
    color: {P["muted_text"]};
    font-size: 0.8rem;
    line-height: 1.3;
    overflow-wrap: break-word;
    word-break: break-word;
}}

/* ── Status Pills & Badges ── */
.status-pill {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0.25rem 0.65rem;
    border-radius: 6px;
    font-size: 0.76rem;
    font-weight: bold;
    letter-spacing: 0.6px;
    text-transform: uppercase;
    white-space: nowrap;
    line-height: 1.2;
}}
.pill-security {{ background-color: {P["security_bg"]}; color: {P["security"]}; border: 1px solid {P["security"]}; }}
.pill-bug {{ background-color: {P["bug_bg"]}; color: {P["bug"]}; border: 1px solid {P["bug"]}; }}
.pill-performance {{ background-color: {P["performance_bg"]}; color: {P["performance"]}; border: 1px solid {P["performance"]}; }}
.pill-style {{ background-color: {P["style_bg"]}; color: {P["style"]}; border: 1px solid {P["style"]}; }}
.pill-accent {{ background-color: {P["accent_glow"]}; color: {P["accent"]}; border: 1px solid {P["accent"]}; }}
.pill-neutral {{ background-color: {P["border_subtle"]}; color: {P["secondary_text"]}; border: 1px solid {P["border"]}; }}

/* ── Clean Label & Value System ── */
.kv-table {{
    display: grid;
    grid-template-columns: 140px minmax(0, 1fr);
    gap: 0.65rem 1rem;
    align-items: baseline;
    margin: 0.85rem 0;
    font-size: 0.95rem;
    line-height: 1.5;
}}
.kv-label {{
    color: {P["secondary_text"]};
    font-weight: bold;
    font-size: 0.82rem;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    overflow-wrap: break-word;
    word-break: break-word;
}}
.kv-value {{
    color: {P["primary_text"]};
    overflow-wrap: break-word;
    word-break: break-word;
    min-width: 0;
}}
.code-pill {{
    font-family: Consolas, Monaco, "Courier New", monospace !important;
    font-size: 0.88rem;
    background-color: {P["code_bg"]};
    border: 1px solid {P["code_border"]};
    padding: 0.15rem 0.5rem;
    border-radius: 4px;
    display: inline-block;
    max-width: 100%;
    overflow-wrap: break-word;
    word-break: break-all;
}}

@media (max-width: 720px) {{
    .kv-table {{
        grid-template-columns: 1fr;
        gap: 0.25rem;
    }}
}}

/* ── Code / Evidence Display ── */
.evidence-box, .code-before, .code-after {{
    background-color: {P["code_bg"]};
    border-radius: 8px;
    padding: 0.75rem 1rem;
    font-family: Consolas, Monaco, "Courier New", monospace !important;
    font-size: 0.86rem;
    line-height: 1.5;
    margin: 0.5rem 0;
    overflow-x: auto !important;
    max-width: 100% !important;
    white-space: pre-wrap !important;
    word-break: break-word !important;
    overflow-wrap: break-word !important;
    box-sizing: border-box !important;
}}
.evidence-box {{
    border: 1px solid {P["code_border"]};
    border-left: 4px solid {P["accent"]};
    color: {P["primary_text"]};
}}
.code-before {{
    border: 1px solid {P["security"]};
    border-left: 4px solid {P["security"]};
    color: {P["primary_text"]};
}}
.code-after {{
    border: 1px solid {P["accent"]};
    border-left: 4px solid {P["accent"]};
    color: {P["primary_text"]};
}}

/* ── Finding Detail Layout ── */
.finding-card {{
    background-color: {P["card_bg"]};
    border: 1px solid {P["border"]};
    border-radius: 10px;
    padding: 1.25rem;
    margin-bottom: 0.75rem;
    min-width: 0;
    max-width: 100%;
    box-shadow: {P["shadow_card"]};
}}
.finding-header-bar {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 0.6rem;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid {P["border_subtle"]};
    margin-bottom: 0.85rem;
}}
.finding-badges-left {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.5rem;
    min-width: 0;
}}
.finding-section-block {{
    margin: 0.75rem 0;
    min-width: 0;
}}
.finding-section-title {{
    font-size: 0.82rem;
    font-weight: bold;
    color: {P["secondary_text"]};
    text-transform: uppercase;
    letter-spacing: 0.7px;
    margin-bottom: 0.25rem;
}}
.finding-section-content {{
    font-size: 0.95rem;
    line-height: 1.5;
    color: {P["primary_text"]};
    overflow-wrap: break-word;
    word-break: break-word;
}}

/* ── Pulse Dot & Risk Indicator Animations ── */
.pulse-dot {{
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background-color: {P["accent"]};
    margin-right: 6px;
    animation: softPulse 2s ease-in-out infinite;
    box-shadow: 0 0 6px {P["accent"]};
}}
@keyframes softPulse {{
    0%, 100% {{ opacity: 1; transform: scale(1); }}
    50% {{ opacity: 0.6; transform: scale(0.92); }}
}}
@keyframes riskPulseLow {{
    0%, 100% {{ box-shadow: 0 0 8px 2px rgba(45,212,191,0.3); }}
    50% {{ box-shadow: 0 0 16px 6px rgba(45,212,191,0.5); }}
}}
@keyframes riskPulseMedium {{
    0%, 100% {{ box-shadow: 0 0 10px 3px rgba(255,152,56,0.35); }}
    50% {{ box-shadow: 0 0 20px 8px rgba(255,152,56,0.55); }}
}}
@keyframes riskPulseHigh {{
    0%, 100% {{ box-shadow: 0 0 12px 4px rgba(244,83,79,0.4); }}
    50% {{ box-shadow: 0 0 24px 10px rgba(244,83,79,0.6); }}
}}
@keyframes riskPulseCritical {{
    0%, 100% {{ box-shadow: 0 0 16px 5px rgba(244,83,79,0.5); }}
    50% {{ box-shadow: 0 0 32px 14px rgba(244,83,79,0.75); }}
}}

.risk-indicator-low {{
    animation: riskPulseLow 2.5s ease-in-out infinite;
    border-radius: 50%;
}}
.risk-indicator-medium {{
    animation: riskPulseMedium 2s ease-in-out infinite;
    border-radius: 50%;
}}
.risk-indicator-high {{
    animation: riskPulseHigh 1.8s ease-in-out infinite;
    border-radius: 50%;
}}
.risk-indicator-critical {{
    animation: riskPulseCritical 1.4s ease-in-out infinite;
    border-radius: 50%;
}}

/* ── Landing Page Components ── */
.landing-hero {{
    text-align: center;
    padding: 3rem 1rem 2rem 1rem;
    max-width: 900px;
    margin: 0 auto;
}}
.landing-workflow-container {{
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.6rem;
    flex-wrap: wrap;
    margin: 1.5rem auto;
    max-width: 850px;
}}
.landing-workflow-step {{
    background: {P["card_bg"]};
    border: 1px solid {P["border"]};
    border-radius: 10px;
    padding: 0.85rem 1.1rem;
    text-align: center;
    font-size: 0.95rem;
    font-weight: bold;
    color: {P["primary_text"]};
    box-shadow: {P["shadow_card"]};
    min-width: 120px;
    transition: transform 0.2s ease;
}}
.landing-workflow-step:hover {{
    transform: translateY(-2px);
    box-shadow: {P["shadow_elevated"]};
}}
.feature-card {{
    background: {P["card_bg"]};
    border: 1px solid {P["border"]};
    border-radius: 12px;
    padding: 1.35rem;
    height: 100%;
    min-width: 0;
    max-width: 100%;
    box-shadow: {P["shadow_card"]};
    overflow-wrap: break-word;
    word-break: break-word;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}}
.feature-card:hover {{
    transform: translateY(-3px);
    box-shadow: {P["shadow_elevated"]};
}}

/* ── Progress Bars & Contribution ── */
.risk-bar-container {{
    background: {P["border_subtle"]};
    border-radius: 4px;
    height: 8px;
    margin: 4px 0 8px 0;
    overflow: hidden;
    width: 100%;
}}
.risk-bar-fill {{
    height: 8px;
    border-radius: 4px;
    transition: width 0.4s ease;
}}

/* ── Section Dividers ── */
.section-header {{
    font-size: 1.15rem;
    font-weight: bold;
    color: {P["primary_text"]};
    margin: 1.5rem 0 0.75rem 0;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid {P["border_subtle"]};
    letter-spacing: 0.2px;
}}

/* ── Streamlit Expander Styling ── */
[data-testid="stExpander"] {{
    background-color: {P["card_bg"]} !important;
    border: 1px solid {P["border"]} !important;
    border-radius: 10px !important;
    margin-bottom: 0.85rem !important;
    min-width: 0 !important;
    max-width: 100% !important;
    overflow: hidden !important;
}}
[data-testid="stExpander"] summary {{
    color: {P["primary_text"]} !important;
    font-weight: bold !important;
    padding: 0.75rem 1rem !important;
    line-height: 1.4 !important;
    overflow-wrap: break-word !important;
    word-break: break-word !important;
}}
[data-testid="stExpander"] [data-testid="stVerticalBlock"] {{
    padding: 0.5rem 0.75rem 1rem 0.75rem !important;
    gap: 0.75rem !important;
}}

/* ── Test Case Card ── */
.test-case-card {{
    background: {P["card_bg_elevated"]};
    border: 1px solid {P["border"]};
    border-left: 4px solid {P["accent"]};
    border-radius: 10px;
    padding: 1.2rem;
    margin-bottom: 0.85rem;
    box-shadow: {P["shadow_card"]};
    min-width: 0;
    max-width: 100%;
    overflow-wrap: break-word;
    word-break: break-word;
}}

/* ── Stack Trace Result Card ── */
.stack-result-card {{
    background: {P["card_bg"]};
    border: 1px solid {P["border"]};
    border-left: 4px solid {P["security"]};
    border-radius: 10px;
    padding: 1.35rem;
    box-shadow: {P["shadow_card"]};
    min-width: 0;
    max-width: 100%;
    overflow-wrap: break-word;
    word-break: break-word;
}}

/* ── Clean Scrollbars ── */
::-webkit-scrollbar {{ width: 6px; height: 6px; }}
::-webkit-scrollbar-track {{ background: {P["bg"]}; }}
::-webkit-scrollbar-thumb {{ background: {P["border"]}; border-radius: 3px; }}
::-webkit-scrollbar-thumb:hover {{ background: {P["secondary_text"]}; }}

/* ── Hide Streamlit Default Chrome ── */
#MainMenu {{ visibility: hidden; }}
footer {{ visibility: hidden; }}
header {{ visibility: hidden; }}
</style>
"""
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


def st_clean_html(html_str: str) -> None:
    """
    Renders raw HTML safely in Streamlit without triggering Markdown-it's
    indented code block parser (<pre><code>). Strips all leading indentation
    from each line and filters empty lines.
    """
    cleaned = "\n".join(line.strip() for line in html_str.splitlines() if line.strip())
    st.markdown(cleaned, unsafe_allow_html=True)


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

            detail = ""
            try:
                body = resp.json()
                if isinstance(body, dict):
                    detail = body.get("detail", "")
            except Exception:
                detail = ""

            if detail:
                raise ValueError(detail)
            elif resp.status_code == 400:
                raise ValueError("Invalid GitHub URL provided.")
            elif resp.status_code == 401:
                raise ValueError("GitHub authentication failed. Please check your GitHub token.")
            elif resp.status_code == 403:
                raise ValueError("GitHub API rate limit exceeded. Please configure a GitHub token or try again later.")
            elif resp.status_code == 404:
                raise ValueError("GitHub repository or PR/commit was not found or is not accessible.")
            elif resp.status_code == 422:
                raise ValueError("Could not parse or process the GitHub target.")
            else:
                raise RuntimeError(f"Backend returned status {resp.status_code}")
    except httpx.ConnectError:
        raise ConnectionError(
            f"Cannot connect to the backend at {BACKEND_URL}. Ensure the FastAPI server is running on port 8000."
        )
    except httpx.TimeoutException:
        raise TimeoutError("The review request timed out. Please check your network connection.")


def call_backend_fix(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Call POST /api/fix on the FastAPI backend."""
    try:
        with httpx.Client(timeout=90.0) as client:
            resp = client.post(f"{BACKEND_URL}/api/fix", json=payload)
            if resp.status_code == 200:
                return resp.json()

            detail = ""
            try:
                body = resp.json()
                if isinstance(body, dict):
                    detail = body.get("detail", "")
            except Exception:
                detail = ""

            if detail:
                raise ValueError(detail)
            else:
                raise RuntimeError(f"Backend fix error: HTTP {resp.status_code}")
    except httpx.ConnectError:
        raise ConnectionError(
            f"Cannot connect to the backend at {BACKEND_URL}. Ensure the FastAPI server is running on port 8000."
        )
    except httpx.TimeoutException:
        raise TimeoutError("The AI fix request timed out. Please try again.")


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
# AI Test Case Generator
# ---------------------------------------------------------------------------
def generate_test_cases_from_findings(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Generate test case specs from security and bug findings.
    Only generates for findings that are technically meaningful.
    """
    test_cases = []
    meaningful_cats = {"security", "bug"}

    for f in findings:
        cat = str(f.get("category", "")).lower()
        if cat not in meaningful_cats:
            continue

        problem = f.get("problem") or f.get("explanation", "")
        evidence = f.get("evidence", "")
        fix = f.get("suggested_fix", "")
        file_ref = f.get("file", "unknown")
        line_ref = f.get("line", 0)
        rule_id = f.get("rule_id", "")
        impact = f.get("impact", "")

        if not problem:
            continue

        if cat == "security":
            title = f"Security Validation: {rule_id or 'Vulnerability Guard'}"
            purpose = f"Verify that the security vulnerability in {file_ref}:{line_ref} is blocked."
            input_desc = f"Trigger execution path targeting {file_ref}:{line_ref}"
            expected = "Vulnerability must be rejected and unauthorized operations prevented."
        else:
            title = f"Bug Regression: {file_ref}:{line_ref}"
            purpose = f"Verify that the defect identified in {file_ref}:{line_ref} does not recur."
            input_desc = f"Invoke affected routine with edge-case or trigger payload"
            expected = "Function executes correctly without unexpected exceptions or corruption."

        impl = ""
        if evidence:
            impl = f"# Reproduce test scenario:\n# Context: {evidence[:250]}"
        if fix:
            impl += f"\n\n# Expected fix verification:\n# {fix[:250]}"

        test_cases.append({
            "title": title,
            "purpose": purpose,
            "category": cat,
            "input": input_desc,
            "expected": expected,
            "implementation": impl.strip(),
            "file": file_ref,
            "line": line_ref,
            "related_finding": problem[:250],
            "impact": impact,
        })

        if len(test_cases) >= 8:
            break

    return test_cases


# ---------------------------------------------------------------------------
# Stack Trace Analyzer
# ---------------------------------------------------------------------------
def analyze_stack_trace(trace: str, findings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Match a pasted stack trace against known findings without inventing files.
    """
    if not trace.strip():
        return {"matched": False, "reason": "No stack trace provided."}

    patterns = [
        r'File ["\']([^"\']+)["\'],\s*line\s*(\d+)',
        r'([a-zA-Z0-9_/\\.]+\.(?:py|js|ts|jsx|tsx|java|go|rb|php)):(\d+)',
        r'at .+?\(([^)]+\.(?:py|js|ts|jsx|tsx)):(\d+)\)',
    ]

    extracted_refs: List[Dict[str, Any]] = []
    for pat in patterns:
        for m in re.finditer(pat, trace):
            fname = m.group(1).split("/")[-1].split("\\")[-1]
            try:
                lineno = int(m.group(2))
            except ValueError:
                lineno = 0
            extracted_refs.append({"file": fname, "line": lineno})

    if not extracted_refs:
        return {
            "matched": False,
            "reason": "Unable to map this stack trace to an exact code location.",
            "extracted_files": [],
        }

    error_match = re.search(
        r'(Error|Exception|Traceback|Fatal|Panic|TypeError|ValueError|KeyError|AttributeError|ImportError|RuntimeError|SyntaxError)[:\s]([^\n]{0,120})',
        trace
    )
    error_type = error_match.group(0)[:140] if error_match else "Exception detected in trace"

    func_matches = re.findall(r'(?:in|at)\s+([a-zA-Z_][a-zA-Z0-9_.]+)\s', trace)
    functions = list(dict.fromkeys(func_matches))[:5]

    matched_findings = []
    for ref in extracted_refs:
        for finding in findings:
            f_file = (finding.get("file") or "").split("/")[-1].split("\\")[-1]
            f_line = finding.get("line", 0)
            if ref["file"] and ref["file"].lower() in f_file.lower():
                if abs(int(f_line) - ref["line"]) <= 10 or ref["line"] == 0:
                    matched_findings.append(finding)

    matched_findings = matched_findings[:3]

    return {
        "matched": True,
        "extracted_files": extracted_refs[:5],
        "error": error_type,
        "functions": functions,
        "matched_findings": matched_findings,
        "explanation": (
            f"Stack trace references {len(extracted_refs)} file location(s). "
            f"{len(matched_findings)} matching finding(s) identified in current review."
        ) if matched_findings else (
            f"Stack trace references {len(extracted_refs)} file location(s), "
            "but no exact match was found in the current review findings."
        ),
        "suggested_fix": matched_findings[0].get("suggested_fix", "") if matched_findings else "",
    }


# ---------------------------------------------------------------------------
# Provider Status Renderer
# ---------------------------------------------------------------------------
def render_provider_status(review_data: Dict[str, Any]):
    is_fallback = review_data.get("fallback_to_static", False)
    truncated_files = review_data.get("truncated_files", [])

    if truncated_files:
        files_str = ", ".join(truncated_files)
        st.warning(
            f"⚠️ **Truncation Notice:** Some files were truncated to 500 changed lines for analysis. "
            f"Affected files: `{files_str}`"
        )

    if not is_fallback:
        st.success("✅ **AI Analysis Complete** — Contextual review combined with static analysis.")
    else:
        st.info("ℹ️ **Static Analysis Only** — AI analysis unavailable. Showing static analysis findings.")


# ---------------------------------------------------------------------------
# Risk Level Helper
# ---------------------------------------------------------------------------
def get_risk_level(total_risk: int) -> tuple:
    """Returns (level_str, color, animation_class, label)"""
    if total_risk >= 10:
        return ("Critical", P["security"], "risk-indicator-critical", "BLOCK RELEASE")
    elif total_risk >= 6:
        return ("High", P["security"], "risk-indicator-high", "BLOCK RELEASE")
    elif total_risk >= 2:
        return ("Medium", P["bug"], "risk-indicator-medium", "REVIEW REQUIRED")
    else:
        return ("Low", P["accent"], "risk-indicator-low", "SAFE TO RELEASE")


# ---------------------------------------------------------------------------
# PAGE: Landing
# ---------------------------------------------------------------------------
def render_landing():
    P_ = P

    st.markdown(
        f"""
        <div class="landing-hero">
            <div style="display:inline-block; padding: 0.4rem 1.1rem; border-radius: 20px;
                        background:{P_['accent_glow']}; border:1px solid {P_['accent']};
                        color:{P_['accent']}; font-size:0.82rem; font-weight:bold;
                        letter-spacing:1.5px; margin-bottom:1.2rem;">
                AI-POWERED · DETERMINISTIC · OPEN-SOURCE READY
            </div>
            <h1 style="font-size:2.8rem; font-weight:bold; color:{P_['primary_text']};
                       margin:0 0 0.5rem 0; letter-spacing:-0.5px; line-height:1.2;">
                AI CODE REVIEW &amp;<br>RELEASE-RISK ASSISTANT
            </h1>
            <p style="font-size:1.15rem; color:{P_['secondary_text']}; margin:0 auto 1.5rem auto;
                      max-width:620px; line-height:1.6;">
                Intelligent code review for safer and more confident releases.
            </p>
            <h2 style="font-size:1.85rem; font-weight:bold; color:{P_['primary_text']};
                       margin:0 0 0.85rem 0; line-height:1.3;">
                Review Code. Detect Risk. Ship with Confidence.
            </h2>
            <p style="font-size:1rem; color:{P_['muted_text']}; max-width:700px;
                      margin:0 auto 2rem auto; line-height:1.65;">
                Analyze GitHub pull requests and commits using static analysis and
                AI-assisted review to detect security vulnerabilities, logic defects,
                performance bottlenecks, and deterministic release risk.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # CTA Buttons
    _, btn1, btn2, _ = st.columns([1.5, 1.5, 1.5, 1.5])
    with btn1:
        if st.button("🚀  Start Code Review", use_container_width=True, type="primary"):
            st.session_state["active_page"] = "Dashboard"
            st.rerun()
    with btn2:
        if st.button("📋  View Dashboard", use_container_width=True):
            st.session_state["active_page"] = "Dashboard"
            st.rerun()

    # Workflow Visual (Strictly Self-Contained HTML)
    wf_steps = [
        ("🔗", "GitHub PR / Commit"),
        ("→", ""),
        ("🔍", "Static Analysis"),
        ("→", ""),
        ("🤖", "AI Review"),
        ("→", ""),
        ("📊", "Risk Scoring"),
        ("→", ""),
        ("✅", "Actionable Fixes"),
    ]
    wf_inner = ""
    for icon, label in wf_steps:
        if icon == "→":
            wf_inner += f'<span style="color:{P_["secondary_text"]}; font-size:1.2rem; padding:0 0.2rem;">→</span>'
        else:
            wf_inner += f"""
            <div class="landing-workflow-step">
                <div style="font-size:1.4rem; margin-bottom:0.25rem;">{icon}</div>
                <div style="font-size:0.82rem; color:{P_['secondary_text']}; line-height:1.2;">{label}</div>
            </div>"""

    st.markdown(
        f"""
        <div style="margin: 2.5rem auto 1.5rem auto; max-width:850px; text-align:center;">
            <div style="font-size:0.85rem; font-weight:bold; letter-spacing:1.5px;
                        color:{P_['secondary_text']}; text-transform:uppercase; margin-bottom:1rem;">
                HOW IT WORKS
            </div>
            <div class="landing-workflow-container">
                {wf_inner}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Feature Cards
    st.markdown(
        f"""
        <div style="text-align:center; font-size:0.85rem; font-weight:bold;
                    letter-spacing:1.5px; color:{P_['secondary_text']};
                    text-transform:uppercase; margin: 2.5rem 0 1.25rem 0;">
            CORE CAPABILITIES
        </div>
        """,
        unsafe_allow_html=True,
    )

    features = [
        ("🔒", "Security Detection", P_["security"],
         "Detect SQL injection, XSS, hardcoded secrets, and insecure configurations."),
        ("🐛", "Bug Detection", P_["bug"],
         "Surface logic defects, null references, exception mishandling, and state races."),
        ("⚡", "Performance Analysis", P_["performance"],
         "Identify N+1 query patterns, blocking I/O, memory leaks, and inefficient algorithms."),
        ("📊", "Release-Risk Scoring", P_["accent"],
         "Deterministic weighted scoring: Security×3, Bug×2, Performance×1.5, Style×0.5."),
        ("🧪", "AI-Generated Test Cases", P_["accent"],
         "Auto-generate regression test cases with inputs and expected outcomes for critical findings."),
        ("🔎", "Stack Trace Mapping", P_["performance"],
         "Map error stack traces to corresponding file locations and review findings."),
    ]

    f1, f2, f3 = st.columns(3)
    cols = [f1, f2, f3]
    for i, (icon, title, color, desc) in enumerate(features):
        with cols[i % 3]:
            st.markdown(
                f"""
                <div class="feature-card" style="border-top: 3px solid {color}; margin-bottom:1.2rem;">
                    <div style="font-size:1.6rem; margin-bottom:0.4rem;">{icon}</div>
                    <div style="font-weight:bold; font-size:1.05rem; color:{P_['primary_text']};
                                margin-bottom:0.4rem;">{title}</div>
                    <div style="font-size:0.9rem; color:{P_['secondary_text']}; line-height:1.5;">{desc}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # Built for Developers
    st.markdown(
        f"""
        <div class="cyber-card" style="margin-top:1rem; padding:1.5rem 2rem;">
            <div style="font-size:1.1rem; font-weight:bold; color:{P_['primary_text']};
                        margin-bottom:0.85rem;">🛠️ Built for Engineering Teams</div>
            <div style="display:flex; gap:1.75rem; flex-wrap:wrap;">
                {"".join(f'<div style="color:{P_["secondary_text"]}; font-size:0.92rem;">✓ &nbsp;{pt}</div>' for pt in [
                    "Evidence-backed findings",
                    "Deterministic risk scoring",
                    "Static analysis + AI",
                    "Actionable suggested fixes",
                    "Zero secret leakage",
                ])}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def extract_snippet_for_finding(file_path: str, line_num: int, evidence: str, problem: str) -> str:
    """Extract real source code context around line_num if available."""
    from pathlib import Path
    for p in [Path(file_path), Path("backend") / file_path, Path("..") / file_path]:
        if p.exists() and p.is_file():
            try:
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                if 1 <= line_num <= len(lines):
                    start = max(0, line_num - 3)
                    end = min(len(lines), line_num + 2)
                    return "\n".join(lines[start:end])
            except Exception:
                pass

    review_res = st.session_state.get("review_result", {})
    files_list = review_res.get("files") or st.session_state.get("files", [])
    for f in files_list:
        if f.get("file") == file_path or f.get("filename") == file_path:
            patch = f.get("patch", "")
            if patch:
                added = [l[1:] for l in patch.splitlines() if l.startswith("+") and not l.startswith("+++")]
                if added:
                    return "\n".join(added[:5])

    if evidence and evidence.strip() and evidence.strip() != problem.strip():
        return evidence
    return problem or "Code snippet"


# ---------------------------------------------------------------------------
# PAGE: Dashboard
# ---------------------------------------------------------------------------
def render_dashboard():
    st.markdown(
        f"""
        <div style="margin-bottom:1.5rem; padding-bottom:0.85rem; border-bottom:1px solid {P['border']};">
            <h1 style="margin:0; font-size:2.2rem; font-weight:bold; color:{P['primary_text']}; letter-spacing:-0.5px;">
                🛡️ AI Code Review Dashboard
            </h1>
            <p style="margin:0.35rem 0 0 0; font-size:1rem; color:{P['secondary_text']};">
                Automated static analysis, AI-assisted review, and deterministic release-risk scoring.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    review_data = st.session_state.get("review_result")

    # URL Input Card
    st.markdown(
        f"""
        <div class="cyber-card" style="margin-bottom:1rem;">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem; margin-bottom:0.4rem;">
                <h3 style="margin:0; font-size:1.1rem; color:{P['primary_text']};">
                    🚀 Analyze a GitHub Pull Request or Commit
                </h3>
                <span style="font-size:0.82rem; color:{P['secondary_text']};">
                    Public GitHub URLs
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
            placeholder="https://github.com/owner/repo/pull/123 or /commit/abc...",
            label_visibility="collapsed",
            key="dash_url_input",
        )
    with col_btn:
        run_review = st.button("Analyze", key="dash_run_btn", use_container_width=True, type="primary")

    if run_review:
        if not target_url.strip():
            st.error("Please enter a valid GitHub Pull Request or Commit URL.")
        else:
            st.session_state["target_url"] = target_url.strip()
            st.session_state["test_cases"] = []
            st.session_state["stack_trace_result"] = None

            with st.status("Running analysis pipeline...", expanded=True) as status:
                st.write("✓ Fetching GitHub changes...")
                st.write("✓ Running static analysis (Ruff · Bandit · ESLint)...")
                st.write("● Performing AI review...")
                try:
                    result = call_backend_review({"url": target_url.strip()})
                    st.session_state["review_result"] = result
                    findings = result.get("findings", [])
                    st.session_state["test_cases"] = generate_test_cases_from_findings(findings)
                    st.write("○ Calculating release risk...")
                    status.update(label="✅ Review complete!", state="complete", expanded=False)
                    st.rerun()
                except Exception as e:
                    status.update(label="Review failed", state="error", expanded=True)
                    st.error(str(e))

    # Results Section
    if review_data:
        render_provider_status(review_data)

        risk = review_data.get("risk", {})
        total_risk = risk.get("total_risk", 0)
        release_status = risk.get("release_status", "SAFE TO RELEASE")
        findings = review_data.get("findings", [])
        top_must_fix = risk.get("top_must_fix", [])

        level, risk_color, anim_class, _ = get_risk_level(total_risk)

        cats = {"security": 0, "bug": 0, "performance": 0, "style": 0}
        for f in findings:
            c = str(f.get("category", "style")).lower()
            if c in cats:
                cats[c] += 1

        # PR Summary Metrics
        st.markdown(f"<div class='section-header'>📋 PR Review Summary</div>", unsafe_allow_html=True)
        m1, m2, m3, m4, m5 = st.columns(5)
        summary_metrics = [
            (m1, "Total Findings", len(findings), P["primary_text"], P["performance"]),
            (m2, "Security", cats["security"], P["security"], P["security"]),
            (m3, "Bugs", cats["bug"], P["bug"], P["bug"]),
            (m4, "Performance", cats["performance"], P["performance"], P["performance"]),
            (m5, "Style", cats["style"], P["style"], P["style"]),
        ]
        for col, title, val, val_color, top_color in summary_metrics:
            with col:
                st.markdown(
                    f"""
                    <div class="cyber-metric-card" style="border-top:3px solid {top_color};">
                        <div class="cyber-metric-title">{title}</div>
                        <div class="cyber-metric-value" style="color:{val_color};">{val}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        # Release Risk Indicator & Breakdown
        st.markdown(f"<div class='section-header'>🎯 Release Risk Indicator</div>", unsafe_allow_html=True)
        r1, r2 = st.columns([1, 2])
        with r1:
            st.markdown(
                f"""
                <div class="cyber-card" style="text-align:center; padding:1.75rem 1rem; border-top:4px solid {risk_color}; height:100%;">
                    <div style="font-size:0.78rem; font-weight:bold; letter-spacing:1.5px;
                                color:{P['secondary_text']}; text-transform:uppercase; margin-bottom:0.75rem;">
                        Release Risk Score
                    </div>
                    <div class="{anim_class}" style="display:inline-flex; align-items:center; justify-content:center;
                                width:110px; height:110px; border-radius:50%; border:4px solid {risk_color};
                                margin:0 auto 0.75rem auto; background:{P['card_bg_elevated']};">
                        <span style="font-size:2.5rem; font-weight:bold; color:{risk_color};">{total_risk}</span>
                    </div>
                    <div>
                        <span style="display:inline-block; padding:0.35rem 1rem; border-radius:6px;
                                     border:2px solid {risk_color}; color:{risk_color};
                                     font-weight:bold; font-size:0.92rem;">{release_status}</span>
                    </div>
                    <div style="font-size:0.82rem; color:{P['muted_text']}; margin-top:0.5rem;">
                        Risk Level: <strong>{level}</strong>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with r2:
            breakdown_items = [
                ("Security", cats["security"], 3, P["security"]),
                ("Bug", cats["bug"], 2, P["bug"]),
                ("Performance", cats["performance"], 1.5, P["performance"]),
                ("Style", cats["style"], 0.5, P["style"]),
            ]
            breakdown_rows = ""
            for label, count, weight, color in breakdown_items:
                score = count * weight
                bar_pct = min(int((score / (total_risk or 1)) * 100), 100) if total_risk > 0 else 0
                breakdown_rows += f"""
                <div style="margin-bottom:0.75rem;">
                    <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:3px;">
                        <span style="font-size:0.9rem; color:{P['primary_text']}; font-weight:bold;">
                            {label} <span style="font-size:0.78rem; color:{P['secondary_text']}; font-weight:normal;">×{weight}</span>
                        </span>
                        <span style="font-size:0.85rem; color:{color}; font-weight:bold;">
                            {count} issues = {score} pts
                        </span>
                    </div>
                    <div class="risk-bar-container">
                        <div class="risk-bar-fill" style="width:{bar_pct}%; background:{color};"></div>
                    </div>
                </div>"""

            st.markdown(
                f"""
                <div class="cyber-card" style="height:100%;">
                    <div style="font-size:0.85rem; font-weight:bold; color:{P['secondary_text']};
                                letter-spacing:1px; text-transform:uppercase; margin-bottom:0.85rem;">
                        Risk Breakdown by Category
                    </div>
                    {breakdown_rows}
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Top 3 Must-Fix Issues
        if top_must_fix:
            st.markdown(f"<div class='section-header'>🚨 Top 3 Must-Fix Issues</div>", unsafe_allow_html=True)
            must_cols = st.columns(min(len(top_must_fix), 3))
            for idx, item in enumerate(top_must_fix[:3]):
                cat = str(item.get("category", "bug")).lower()
                color = P.get(cat, P["bug"])
                conf = str(item.get("confidence", "moderate")).upper()
                file_name = item.get("file", "unknown")
                line_no = item.get("line", 0)
                prob = item.get("problem") or item.get("explanation", "")
                imp = item.get("impact", "")
                s_fix = item.get("suggested_fix", "")

                with must_cols[idx]:
                    card_html = f"""
                    <div class="cyber-card" style="border-top:4px solid {color}; height:100%; display:flex; flex-direction:column; justify-content:space-between;">
                        <div>
                            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.4rem; margin-bottom:0.6rem;">
                                <span class="status-pill pill-{cat}">{cat.upper()}</span>
                                <span class="status-pill pill-neutral">CONF: {conf}</span>
                            </div>
                            <div class="finding-section-block">
                                <div class="finding-section-title">File & Line</div>
                                <div class="code-pill">{html.escape(str(file_name))} : {line_no}</div>
                            </div>
                            <div class="finding-section-block">
                                <div class="finding-section-title">Issue</div>
                                <div class="finding-section-content">{html.escape(str(prob[:180]))}</div>
                            </div>
                            {f'<div class="finding-section-block"><div class="finding-section-title">Impact</div><div class="finding-section-content" style="color:{color};">{html.escape(str(imp[:120]))}</div></div>' if imp else ''}
                        </div>
                        {f'<div class="finding-section-block" style="border-top:1px solid {P["border_subtle"]}; padding-top:0.5rem; margin-top:0.5rem;"><div class="finding-section-title">Suggested Fix</div><div class="finding-section-content" style="color:{P["accent"]};">💡 {html.escape(str(s_fix[:140]))}</div></div>' if s_fix else ''}
                    </div>
                    """
                    st_clean_html(card_html)
                    if st.button("⚡ AI FIX", key=f"dash_must_fix_ai_{idx}", use_container_width=True):
                        code_to_fix = extract_snippet_for_finding(file_name, line_no, item.get("evidence", ""), prob)
                        with st.spinner("Generating AI Fix..."):
                            fix_payload = {
                                "file": file_name,
                                "code": code_to_fix,
                                "line": line_no,
                                "category": cat,
                                "source": item.get("source", "static"),
                                "rule_id": item.get("rule_id", None),
                                "evidence": code_to_fix,
                                "explanation": prob,
                                "suggested_fix": s_fix if s_fix else None,
                            }
                            try:
                                fix_resp = call_backend_fix(fix_payload)
                                st.session_state["active_fix"] = {
                                    "finding_idx": idx,
                                    "req": fix_payload,
                                    "resp": fix_resp,
                                }
                                st.session_state["active_page"] = "Findings"
                                st.rerun()
                            except Exception as e:
                                st.error(f"Fix generation failed: {e}")

        # AI Summary
        st.markdown(
            f"""
            <div class="cyber-card" style="margin-top:0.5rem;">
                <div style="font-size:1rem; font-weight:bold; color:{P['primary_text']}; margin-bottom:0.5rem;">
                    📄 AI Review Summary
                </div>
                <p style="margin:0; color:{P['secondary_text']}; line-height:1.6; font-size:0.95rem;">
                    {review_data.get('summary', 'No summary provided.')}
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Navigation Shortcuts
        c1, c2, c3, c4 = st.columns(4)
        nav_btns = [
            (c1, "📊 Risk Analysis", "Risk Analysis"),
            (c2, "⚠️ All Findings", "Findings"),
            (c3, "🧪 Test Cases", "Test Cases"),
            (c4, "🔎 Stack Trace", "Stack Trace"),
        ]
        for col, label, page in nav_btns:
            with col:
                if st.button(label, use_container_width=True):
                    st.session_state["active_page"] = page
                    st.rerun()

    else:
        # Empty State
        st.markdown(
            f"""
            <div class="cyber-card" style="text-align:center; padding:3.5rem 1.5rem; margin-top:1rem;">
                <div style="font-size:3.5rem; margin-bottom:0.75rem;">🛡️</div>
                <h2 style="margin:0 0 0.5rem 0; color:{P['primary_text']}; font-size:1.7rem;">
                    Ready to review your code?
                </h2>
                <p style="margin:0 auto 1.5rem auto; color:{P['secondary_text']}; font-size:1rem; max-width:560px; line-height:1.6;">
                    Paste a public GitHub pull request or commit URL to analyze security,
                    bugs, performance risks, and deterministic release risk.
                </p>
                <div style="display:inline-flex; gap:1.2rem; flex-wrap:wrap; justify-content:center; font-size:0.88rem; color:{P['muted_text']};">
                    <span>⚡ Static Analysis</span>
                    <span>·</span>
                    <span>⚡ AI-Assisted Review</span>
                    <span>·</span>
                    <span>⚡ Deterministic Risk Scoring</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# PAGE: Code Review
# ---------------------------------------------------------------------------
def render_code_review():
    st.markdown(
        f"""
        <div style="margin-bottom:1.5rem; padding-bottom:0.85rem; border-bottom:1px solid {P['border']};">
            <h1 style="margin:0; font-size:2rem; font-weight:bold; color:{P['primary_text']};">
                🔍 Code Review Console
            </h1>
            <p style="margin:0.3rem 0 0 0; color:{P['secondary_text']};">
                Targeted pull request and commit inspection with static and AI-assisted analysis.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="cyber-card">
            <div style="font-weight:bold; font-size:1rem; color:{P['primary_text']}; margin-bottom:0.3rem;">
                GitHub Pull Request or Commit URL
            </div>
            <div style="font-size:0.88rem; color:{P['secondary_text']}; line-height:1.5;">
                Paste any public GitHub URL. The review pipeline extracts changed files,
                applies static analysis (Ruff, Bandit, ESLint), and queries AI review models.
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
        submit_btn = st.button("Run Review", key="cr_submit_btn", use_container_width=True, type="primary")

    if submit_btn:
        if not target_url.strip():
            st.error("Please enter a valid GitHub URL.")
        else:
            st.session_state["target_url"] = target_url.strip()
            st.session_state["test_cases"] = []
            with st.status("Performing automated review...", expanded=True) as status:
                st.write("✓ Fetching changes from GitHub...")
                st.write("✓ Running Ruff · Bandit · ESLint...")
                st.write("● Running AI analysis...")
                try:
                    result = call_backend_review({"url": target_url.strip()})
                    st.session_state["review_result"] = result
                    findings = result.get("findings", [])
                    st.session_state["test_cases"] = generate_test_cases_from_findings(findings)
                    st.write("○ Calculating risk score...")
                    status.update(label="✅ Analysis complete!", state="complete", expanded=False)
                    st.rerun()
                except Exception as e:
                    status.update(label="Review failed", state="error", expanded=True)
                    st.error(str(e))

    review_data = st.session_state.get("review_result")
    if review_data:
        st.markdown("---")
        render_provider_status(review_data)

        findings = review_data.get("findings", [])
        st.markdown(
            f"""
            <div class="cyber-card">
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem; margin-bottom:0.6rem;">
                    <div style="font-size:1.05rem; font-weight:bold; color:{P['primary_text']};">
                        Review Summary
                    </div>
                    <span class="status-pill pill-accent">{len(findings)} Findings</span>
                </div>
                <p style="margin:0; color:{P['secondary_text']}; line-height:1.6; font-size:0.95rem;">
                    {review_data.get('summary', 'No summary generated.')}
                </p>
                <div style="font-size:0.82rem; color:{P['muted_text']}; border-top:1px solid {P['border']}; padding-top:0.6rem; margin-top:0.75rem;">
                    Target: <code>{st.session_state.get('target_url')}</code>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        c1, c2 = st.columns(2)
        with c1:
            if st.button("📊 Open Risk Analysis →", use_container_width=True):
                st.session_state["active_page"] = "Risk Analysis"
                st.rerun()
        with c2:
            if st.button("⚠️ View All Findings →", use_container_width=True):
                st.session_state["active_page"] = "Findings"
                st.rerun()
    else:
        st.info("No active review. Enter a GitHub URL above and click **Run Review**.")


# ---------------------------------------------------------------------------
# PAGE: Risk Analysis
# ---------------------------------------------------------------------------
def render_risk_analysis():
    st.markdown(
        f"""
        <div style="margin-bottom:1.5rem; padding-bottom:0.85rem; border-bottom:1px solid {P['border']};">
            <h1 style="margin:0; font-size:2rem; font-weight:bold; color:{P['primary_text']};">
                📊 Release-Risk Analysis
            </h1>
            <p style="margin:0.3rem 0 0 0; color:{P['secondary_text']};">
                Deterministic weighted scoring — zero LLM involvement in risk scoring.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    review_data = st.session_state.get("review_result")
    if not review_data:
        st.warning("⚠️ No review loaded. Run a review from the **Dashboard** first.")
        return

    risk = review_data.get("risk", {})
    total_risk = risk.get("total_risk", 0)
    release_status = risk.get("release_status", "SAFE TO RELEASE")
    breakdown = risk.get("breakdown", {})
    top_must_fix = risk.get("top_must_fix", [])

    level, risk_color, anim_class, _ = get_risk_level(total_risk)

    # Hero Risk Card
    st.markdown(
        f"""
        <div class="cyber-card" style="padding:2.2rem 1.5rem; text-align:center; border-top:4px solid {risk_color};">
            <div style="font-size:0.8rem; font-weight:bold; letter-spacing:2px;
                        color:{P['secondary_text']}; text-transform:uppercase; margin-bottom:1rem;">
                Total Release-Risk Score
            </div>
            <div class="{anim_class}" style="display:inline-flex; align-items:center; justify-content:center;
                        width:130px; height:130px; border-radius:50%; border:5px solid {risk_color};
                        margin:0 auto 1rem auto; background:{P['card_bg_elevated']};">
                <span style="font-size:3rem; font-weight:bold; color:{risk_color};">{total_risk}</span>
            </div>
            <div style="margin-bottom:0.6rem;">
                <span style="display:inline-block; padding:0.4rem 1.5rem; border-radius:8px;
                             font-weight:bold; font-size:1.1rem; border:2px solid {risk_color};
                             color:{risk_color}; background:rgba(0,0,0,0.04);">{release_status}</span>
            </div>
            <div style="font-size:0.9rem; color:{P['muted_text']};">
                Risk Classification: <strong>{level}</strong>
            </div>
            <p style="font-size:0.9rem; color:{P['muted_text']}; max-width:520px; margin:0.85rem auto 0 auto; line-height:1.5;">
                Deterministic engine: Security×3 · Bug×2 · Performance×1.5 · Style×0.5
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Weighted Breakdown
    st.markdown(f"<div class='section-header'>📐 Weighted Category Breakdown</div>", unsafe_allow_html=True)

    sec = breakdown.get("security", {"count": 0, "weight": 3, "score": 0})
    bug = breakdown.get("bug", {"count": 0, "weight": 2, "score": 0})
    perf = breakdown.get("performance", {"count": 0, "weight": 1.5, "score": 0})
    sty = breakdown.get("style", {"count": 0, "weight": 0.5, "score": 0})

    breakdown_data = [
        ("SECURITY", sec, P["security"], "security"),
        ("BUG", bug, P["bug"], "bug"),
        ("PERFORMANCE", perf, P["performance"], "performance"),
        ("STYLE", sty, P["style"], "style"),
    ]
    b_cols = st.columns(4)
    for col, (label, data, color, cls) in zip(b_cols, breakdown_data):
        with col:
            bar_pct = min(int((data["score"] / (total_risk or 1)) * 100), 100) if total_risk > 0 else 0
            st.markdown(
                f"""
                <div class="cyber-card" style="border-left:4px solid {color};">
                    <span class="status-pill pill-{cls}">{label}</span>
                    <div style="font-size:1.8rem; font-weight:bold; color:{P['primary_text']}; margin:0.5rem 0 0.1rem 0;">
                        {data['score']} <span style="font-size:0.85rem; color:{P['secondary_text']};">pts</span>
                    </div>
                    <div style="font-size:0.85rem; color:{P['secondary_text']}; margin-bottom:0.6rem;">
                        {data['count']} issues × {data['weight']}
                    </div>
                    <div style="font-size:0.78rem; color:{P['muted_text']}; margin-bottom:0.25rem;">Contribution</div>
                    <div class="risk-bar-container">
                        <div class="risk-bar-fill" style="width:{bar_pct}%; background:{color};"></div>
                    </div>
                    <div style="font-size:0.78rem; color:{P['muted_text']};">{bar_pct}%</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # Top 3 Must-Fix
    if top_must_fix:
        st.markdown(f"<div class='section-header'>🚨 Top 3 Must-Fix Issues</div>", unsafe_allow_html=True)
        must_cols = st.columns(min(len(top_must_fix), 3))
        for idx, item in enumerate(top_must_fix[:3]):
            cat = str(item.get("category", "bug")).lower()
            color = P.get(cat, P["bug"])
            conf = str(item.get("confidence", "moderate")).upper()
            file_name = item.get("file", "unknown")
            line_no = item.get("line", 0)
            prob = item.get("problem") or item.get("explanation", "")
            imp = item.get("impact", "")
            s_fix = item.get("suggested_fix", "")

            with must_cols[idx]:
                card_html = f"""
                <div class="cyber-card" style="border-top:4px solid {color}; height:100%; display:flex; flex-direction:column; justify-content:space-between;">
                    <div>
                        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.4rem; margin-bottom:0.6rem;">
                            <span class="status-pill pill-{cat}">{cat.upper()}</span>
                            <span class="status-pill pill-neutral">CONF: {conf}</span>
                        </div>
                        <div class="finding-section-block">
                            <div class="finding-section-title">File & Line</div>
                            <div class="code-pill">{html.escape(str(file_name))} : {line_no}</div>
                        </div>
                        <div class="finding-section-block">
                            <div class="finding-section-title">Issue</div>
                            <div class="finding-section-content">{html.escape(str(prob[:180]))}</div>
                        </div>
                        {f'<div class="finding-section-block"><div class="finding-section-title">Impact</div><div class="finding-section-content" style="color:{color};">{html.escape(str(imp[:120]))}</div></div>' if imp else ''}
                    </div>
                    {f'<div class="finding-section-block" style="border-top:1px solid {P["border_subtle"]}; padding-top:0.5rem; margin-top:0.5rem;"><div class="finding-section-title">Suggested Fix</div><div class="finding-section-content" style="color:{P["accent"]};">💡 {html.escape(str(s_fix[:140]))}</div></div>' if s_fix else ''}
                </div>
                """
                st_clean_html(card_html)
                if st.button("⚡ AI FIX", key=f"risk_must_fix_ai_{idx}", use_container_width=True):
                    code_to_fix = extract_snippet_for_finding(file_name, line_no, item.get("evidence", ""), prob)
                    with st.spinner("Generating AI Fix..."):
                        fix_payload = {
                            "file": file_name,
                            "code": code_to_fix,
                            "line": line_no,
                            "category": cat,
                            "source": item.get("source", "static"),
                            "rule_id": item.get("rule_id", None),
                            "evidence": code_to_fix,
                            "explanation": prob,
                            "suggested_fix": s_fix if s_fix else None,
                        }
                        try:
                            fix_resp = call_backend_fix(fix_payload)
                            st.session_state["active_fix"] = {
                                "finding_idx": idx,
                                "req": fix_payload,
                                "resp": fix_resp,
                            }
                            st.session_state["active_page"] = "Findings"
                            st.rerun()
                        except Exception as e:
                            st.error(f"Fix generation failed: {e}")


# ---------------------------------------------------------------------------
# AI Code Fix Assistant Actions & UI Panel
# ---------------------------------------------------------------------------
def apply_fix_and_reanalyze(active_fix: Dict[str, Any]) -> None:
    """
    Applies the approved fix locally, updates in-memory findings, and
    recalculates deterministic risk and evaluation metrics.
    """
    review_data = st.session_state.get("review_result")
    if not review_data:
        st.session_state["active_fix"] = None
        return

    req = active_fix.get("req", {})
    resp = active_fix.get("resp", {})
    file_name = req.get("file", "")
    line_no = req.get("line", 0)
    rule_id = req.get("rule_id", "")
    problem_text = req.get("explanation", "")

    findings = review_data.get("findings", [])
    old_risk = review_data.get("risk", {}).get("total_risk", 0)

    # Filter out the fixed finding
    new_findings = []
    removed = False
    for f in findings:
        f_file = f.get("file", "")
        f_line = f.get("line", 0)
        f_rule = f.get("rule_id", "")
        f_prob = f.get("problem") or f.get("explanation", "")

        match_rule = bool(rule_id and f_rule == rule_id and f_file == file_name)
        match_line = bool(f_file == file_name and abs(f_line - line_no) <= 2)
        match_prob = bool(problem_text and (problem_text in f_prob or f_prob in problem_text))

        if not removed and (match_rule or (match_line and match_prob)):
            removed = True
            continue  # Finding resolved!
        new_findings.append(f)

    # Recalculate deterministic risk with the remaining findings
    from risk.risk_engine import calculate_risk
    from evaluation.evaluator import evaluate_against_dataset

    updated_risk = calculate_risk(new_findings)
    updated_eval = evaluate_against_dataset(new_findings)

    # Update review_result in session state
    review_data["findings"] = updated_risk.get("ordered_findings", new_findings)
    review_data["issues"] = review_data["findings"]
    review_data["total_findings"] = len(review_data["findings"])
    review_data["total_issues"] = len(review_data["findings"])
    review_data["risk"] = updated_risk
    review_data["evaluation"] = updated_eval

    new_risk_score = updated_risk.get("total_risk", 0)

    # Track applied fix in session history
    st.session_state["applied_fixes"].append({
        "file": file_name,
        "line": line_no,
        "rule_id": rule_id,
        "issue": problem_text,
        "before": resp.get("original_code", req.get("evidence", "")),
        "after": resp.get("fixed_code", ""),
        "old_risk": old_risk,
        "new_risk": new_risk_score,
    })

    st.session_state["active_fix"] = None
    st.session_state["fix_success_message"] = (
        f"✅ Fix successfully applied to `{file_name}:{line_no}`! "
        f"Finding resolved. Risk score updated from {old_risk} to {new_risk_score}."
    )


def render_fix_panel(active_fix: Dict[str, Any], P: Dict[str, str], key_suffix: str = "") -> None:
    req = active_fix.get("req", {})
    resp = active_fix.get("resp", {})
    provider = str(resp.get("provider", "gemini")).upper()
    confidence = str(resp.get("confidence", "high")).upper()
    cat = str(req.get("category", "security")).lower()
    color = P.get(cat, P["accent"])

    panel_html = f"""
    <div class="cyber-card" style="border: 2px solid {P['accent']}; border-top: 5px solid {P['accent']}; margin-bottom: 1.5rem; background: {P['card_bg_elevated']};">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.6rem; margin-bottom:1rem; border-bottom:1px solid {P['border_subtle']}; padding-bottom:0.75rem;">
            <div style="font-size:1.3rem; font-weight:bold; color:{P['primary_text']}; display:flex; align-items:center; gap:8px;">
                <span>🛠️ AI Suggested Fix</span>
                <span class="status-pill pill-accent" style="font-size:0.75rem;">POWERED BY {html.escape(provider)}</span>
            </div>
            <div style="display:flex; gap:6px;">
                <span class="status-pill pill-{cat}">{cat.upper()}</span>
                <span class="status-pill pill-neutral">CONFIDENCE: {html.escape(confidence)}</span>
            </div>
        </div>
        <div class="kv-table" style="margin-bottom:1rem;">
            <div class="kv-label">Problem</div>
            <div class="kv-value"><strong>{html.escape(str(req.get('explanation', '')))}</strong></div>
            <div class="kv-label">File</div>
            <div class="kv-value"><span class="code-pill">{html.escape(str(req.get('file', '')))}</span></div>
            <div class="kv-label">Line</div>
            <div class="kv-value">{req.get('line', 0)}</div>
            <div class="kv-label">Category</div>
            <div class="kv-value" style="color:{color}; font-weight:bold;">{cat.upper()}</div>
            <div class="kv-label">Source</div>
            <div class="kv-value">{html.escape(str(req.get('source', 'static')).upper())}{f" ({html.escape(str(req.get('rule_id')))})" if req.get('rule_id') else ''}</div>
        </div>
    </div>
    """
    st_clean_html(panel_html)

    # Before / After Code Display
    col_b, col_a = st.columns(2)
    with col_b:
        st.markdown(
            f"""
            <div style="font-size:0.85rem; font-weight:bold; color:{P['security']}; margin-bottom:0.3rem; letter-spacing:0.5px;">
                BEFORE (ORIGINAL CODE)
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.code(resp.get("original_code", req.get("evidence", "")), language="python")

    with col_a:
        st.markdown(
            f"""
            <div style="font-size:0.85rem; font-weight:bold; color:{P['accent']}; margin-bottom:0.3rem; letter-spacing:0.5px;">
                AFTER (AI FIXED CODE)
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.code(resp.get("fixed_code", ""), language="python")

    # Explanation and Changes
    expl_html = f"""
    <div style="background:{P['card_bg']}; border:1px solid {P['border']}; border-radius:8px; padding:0.85rem 1rem; margin:0.75rem 0;">
        <div style="margin-bottom:0.4rem;">
            <strong style="color:{P['primary_text']}; font-size:0.9rem;">Explanation:</strong>
            <span style="color:{P['secondary_text']}; font-size:0.9rem; margin-left:6px;">{html.escape(str(resp.get('explanation', '')))}</span>
        </div>
        <div>
            <strong style="color:{P['primary_text']}; font-size:0.9rem;">Changes:</strong>
            <span style="color:{P['secondary_text']}; font-size:0.9rem; margin-left:6px;">{html.escape(str(resp.get('changes', '')))}</span>
        </div>
    </div>
    """
    st_clean_html(expl_html)

    # Actions: Apply Fix Locally / Dismiss
    col_apply, col_dismiss, _ = st.columns([1.8, 1.2, 3])
    apply_k = f"btn_apply_fix_{key_suffix}" if key_suffix else "btn_apply_fix_now"
    dismiss_k = f"btn_dismiss_fix_{key_suffix}" if key_suffix else "btn_dismiss_fix"
    with col_apply:
        if st.button("✅ Apply Fix Locally", type="primary", key=apply_k, use_container_width=True):
            apply_fix_and_reanalyze(active_fix)
            st.rerun()
    with col_dismiss:
        if st.button("✕ Dismiss", key=dismiss_k, use_container_width=True):
            st.session_state["active_fix"] = None
            st.rerun()




# ---------------------------------------------------------------------------
# PAGE: Findings
# ---------------------------------------------------------------------------
def render_findings():
    st.markdown(
        f"""
        <div style="margin-bottom:1.5rem; padding-bottom:0.85rem; border-bottom:1px solid {P['border']};">
            <h1 style="margin:0; font-size:2rem; font-weight:bold; color:{P['primary_text']};">
                ⚠️ Prioritized Findings
            </h1>
            <p style="margin:0.3rem 0 0 0; color:{P['secondary_text']};">
                Strict priority order: Security → Bug → Performance → Style
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    review_data = st.session_state.get("review_result")
    if not review_data:
        st.warning("⚠️ No review loaded. Run a review first.")
        return

    if st.session_state.get("fix_success_message"):
        st.success(st.session_state["fix_success_message"])
        st.session_state["fix_success_message"] = None

    active_fix = st.session_state.get("active_fix")

    applied_fixes = st.session_state.get("applied_fixes", [])
    if applied_fixes:
        with st.expander(f"✨ Applied Fixes in this Session ({len(applied_fixes)})", expanded=False):
            for af in applied_fixes:
                st.markdown(
                    f"- **{af['file']}:{af['line']}** — Resolved *{af['issue'][:90]}...* (Risk: {af['old_risk']} ➔ **{af['new_risk']}**)"
                )

    all_findings = review_data.get("findings", [])
    if not all_findings:
        st.info("✅ No issues detected in the reviewed changes.")
        return


    # Category Filter
    cat_choices = ["All", "Security", "Bug", "Performance", "Style"]
    chosen_cat = st.radio(
        "Filter by Category",
        options=cat_choices,
        horizontal=True,
        index=cat_choices.index(st.session_state["findings_filter"])
        if st.session_state["findings_filter"] in cat_choices else 0,
        key="cat_filter_radio",
    )
    st.session_state["findings_filter"] = chosen_cat

    if chosen_cat == "All":
        filtered = all_findings
    else:
        filtered = [f for f in all_findings
                    if str(f.get("category", "")).lower() == chosen_cat.lower()]

    st.markdown(
        f"<p style='color:{P['secondary_text']}; font-size:0.92rem; margin:0.4rem 0 0.9rem 0;'>"
        f"Showing <strong>{len(filtered)}</strong> of {len(all_findings)} findings</p>",
        unsafe_allow_html=True,
    )

    if active_fix:
        req_f = active_fix.get("req", {})
        matches_filtered = any(
            (f.get("file") == req_f.get("file") and f.get("line") == req_f.get("line"))
            for f in filtered
        )
        if not matches_filtered:
            render_fix_panel(active_fix, P, key_suffix="top_unfiltered")
        else:
            st.markdown(
                f"""
                <div style="background:{P['card_bg_elevated']}; border:1px solid {P['accent']}; border-radius:8px; padding:0.75rem 1rem; margin-bottom:1.25rem; display:flex; align-items:center; gap:10px;">
                    <span style="font-size:1.2rem;">🛠️</span>
                    <span style="color:{P['primary_text']}; font-size:0.92rem;">
                        <strong>AI Code Fix Ready:</strong> Active for <code>{html.escape(str(req_f.get('file', 'file')))} : Line {req_f.get('line', 0)}</code>. Review the BEFORE/AFTER diff and click <strong>Apply Fix Locally</strong> directly in the finding card below.
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )

    for idx, item in enumerate(filtered, 1):
        cat = str(item.get("category", "style")).lower()
        color = P.get(cat, P["style"])
        source = item.get("source", "static")
        rule_id = item.get("rule_id", "")
        evidence = item.get("evidence", "")
        problem = item.get("problem") or item.get("explanation", "")
        impact = item.get("impact", "")
        why_it_happens = item.get("why_it_happens", "")
        fix = item.get("suggested_fix", "")
        conf = str(item.get("confidence", "moderate")).upper()
        severity = str(item.get("severity", cat.upper())).upper()
        file_path = item.get("file", "unknown")
        line_num = item.get("line", 0)

        explanation = item.get("explanation", "")
        # Source badge
        source_badge = f"Static Analysis ({rule_id})" if (source == "static" and rule_id) else ("Static Analysis" if source == "static" else "AI Analysis")

        # Expander title
        expander_title = f"Finding #{idx}  [{cat.upper()}]  {file_path} : Line {line_num}"

        # Check if explanation should be shown separately (if distinct from problem)
        show_explanation = bool(explanation and explanation.strip() != problem.strip())

        with st.expander(expander_title, expanded=(idx <= 3 and cat in ("security", "bug"))):
            card_html = f"""
            <div class="finding-card" style="border-left:5px solid {color};">
                <div class="finding-header-bar">
                    <div class="finding-badges-left">
                        <span class="status-pill pill-{cat}">{cat.upper()}</span>
                        <span class="status-pill pill-neutral">SEVERITY: {severity}</span>
                        <span class="status-pill pill-neutral">{html.escape(source_badge)}</span>
                    </div>
                    <span class="status-pill pill-neutral">CONFIDENCE: {conf}</span>
                </div>
                <div class="kv-table">
                    <div class="kv-label">File</div>
                    <div class="kv-value"><span class="code-pill">{html.escape(str(file_path))}</span></div>
                    <div class="kv-label">Line</div>
                    <div class="kv-value">{line_num}</div>
                    {f'<div class="kv-label">Rule ID</div><div class="kv-value"><span class="code-pill">{html.escape(str(rule_id))}</span></div>' if rule_id else ''}
                    <div class="kv-label">Issue</div>
                    <div class="kv-value"><strong>{html.escape(str(problem))}</strong></div>
                    {f'<div class="kv-label">Impact</div><div class="kv-value" style="color:{color}; font-weight:600;">{html.escape(str(impact))}</div>' if impact else ''}
                    {f'<div class="kv-label">Why It Happens</div><div class="kv-value" style="color:{P["secondary_text"]};">{html.escape(str(why_it_happens))}</div>' if why_it_happens else ''}
                    {f'<div class="kv-label">Explanation</div><div class="kv-value" style="color:{P["secondary_text"]};">{html.escape(str(explanation))}</div>' if show_explanation else ''}
                    {f'<div class="kv-label">Suggested Fix</div><div class="kv-value" style="color:{P["accent"]}; font-weight:600;">{html.escape(str(fix))}</div>' if fix else ''}
                </div>
            </div>
            """
            st_clean_html(card_html)

            if evidence:
                evidence_html = f"""
                <div class="finding-section-block">
                    <div class="finding-section-title">Code Evidence</div>
                    <div class="evidence-box">{html.escape(str(evidence))}</div>
                </div>
                """
                st_clean_html(evidence_html)

            # Before / After Code View
            if fix:
                remediation_html = f"""
                <div class="finding-section-block">
                    <div class="finding-section-title" style="margin-top:0.6rem;">🔧 Suggested Remediation</div>
                    <div style="font-size:0.92rem; color:{P['primary_text']}; margin-bottom:0.5rem; line-height:1.5;">
                        {html.escape(str(fix))}
                    </div>
                </div>
                <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:1rem; margin-top:0.75rem;">
                    <div>
                        <div style="font-size:0.8rem; font-weight:bold; color:{P['security']}; letter-spacing:0.8px; margin-bottom:0.25rem;">
                            BEFORE (FLAGGED CODE)
                        </div>
                        <div class="code-before">{html.escape(str(evidence if evidence else problem))}</div>
                    </div>
                    <div>
                        <div style="font-size:0.8rem; font-weight:bold; color:{P['accent']}; letter-spacing:0.8px; margin-bottom:0.25rem;">
                            SUGGESTED AFTER (REMEDIATION)
                        </div>
                        <div class="code-after">{html.escape(str(fix))}</div>
                        <div style="font-size:0.75rem; color:{P['muted_text']}; margin-top:0.25rem;">
                            ⚠ Suggested fix — verify before applying.
                        </div>
                    </div>
                </div>
                """
                st_clean_html(remediation_html)

            # ── AI Code Fix Assistant Action ──
            req_active = active_fix.get("req", {}) if active_fix else {}
            is_active_for_this_card = (
                active_fix is not None and (
                    active_fix.get("finding_idx") == idx or
                    (req_active.get("file") == file_path and req_active.get("line") == line_num)
                )
            )

            if is_active_for_this_card:
                st.markdown(f"<div style='margin-top:1rem;'></div>", unsafe_allow_html=True)
                render_fix_panel(active_fix, P, key_suffix=f"card_{idx}")
            elif cat in ("security", "bug", "performance"):
                btn_cols = st.columns([1.8, 4])
                with btn_cols[0]:
                    if st.button("⚡ AI FIX", key=f"btn_ai_fix_{idx}", use_container_width=True, type="primary" if cat == "security" else "secondary"):
                        code_to_fix = extract_snippet_for_finding(file_path, line_num, evidence, problem)
                        with st.spinner("Generating AI Fix with Gemini/Groq..."):
                            fix_payload = {
                                "file": file_path,
                                "code": code_to_fix,
                                "line": line_num,
                                "category": cat,
                                "source": source,
                                "rule_id": rule_id if rule_id else None,
                                "evidence": code_to_fix,
                                "explanation": problem,
                                "suggested_fix": fix if fix else None,
                            }
                            try:
                                fix_resp = call_backend_fix(fix_payload)
                                st.session_state["active_fix"] = {
                                    "finding_idx": idx,
                                    "req": fix_payload,
                                    "resp": fix_resp,
                                }
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to generate fix: {e}")



# ---------------------------------------------------------------------------
# PAGE: Test Cases
# ---------------------------------------------------------------------------
def render_test_cases():
    st.markdown(
        f"""
        <div style="margin-bottom:1.5rem; padding-bottom:0.85rem; border-bottom:1px solid {P['border']};">
            <h1 style="margin:0; font-size:2rem; font-weight:bold; color:{P['primary_text']};">
                🧪 AI-Generated Test Cases
            </h1>
            <p style="margin:0.3rem 0 0 0; color:{P['secondary_text']};">
                Targeted regression tests generated for critical security and bug findings.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    review_data = st.session_state.get("review_result")
    test_cases = st.session_state.get("test_cases", [])

    if not review_data:
        st.warning("⚠️ No review loaded. Run a review first to generate test cases.")
        return

    if not test_cases:
        findings = review_data.get("findings", [])
        test_cases = generate_test_cases_from_findings(findings)
        st.session_state["test_cases"] = test_cases

    if not test_cases:
        st.info(
            "No test cases generated. Test cases are only produced for security and bug findings. "
            "This review does not contain findings requiring regression test generation."
        )
        return

    st.markdown(
        f"""
        <div class="cyber-card" style="margin-bottom:1.25rem;">
            <div style="font-size:0.92rem; color:{P['secondary_text']}; line-height:1.5;">
                <span class="status-pill pill-accent">{len(test_cases)} Test Cases</span>
                &nbsp; Generated for identified Security and Bug findings.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    for i, tc in enumerate(test_cases, 1):
        cat = tc.get("category", "bug")
        color = P.get(cat, P["bug"])

        with st.expander(f"Test Case #{i}: {tc['title']}", expanded=(i <= 2)):
            test_card_html = f"""
            <div class="test-case-card">
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem; margin-bottom:0.75rem;">
                    <span class="status-pill pill-{cat}">{cat.upper()}</span>
                    <span class="code-pill">{html.escape(str(tc.get('file','?')))} : Line {tc.get('line','?')}</span>
                </div>
                <div class="kv-table">
                    <div class="kv-label">Purpose</div>
                    <div class="kv-value">{html.escape(str(tc['purpose']))}</div>
                    <div class="kv-label">Input / Trigger</div>
                    <div class="kv-value">{html.escape(str(tc['input']))}</div>
                    <div class="kv-label">Expected Result</div>
                    <div class="kv-value">{html.escape(str(tc['expected']))}</div>
                    <div class="kv-label">Related Finding</div>
                    <div class="kv-value" style="color:{P['muted_text']};">{html.escape(str(tc.get('related_finding','')))}</div>
                </div>
            </div>
            """
            st_clean_html(test_card_html)

            impl = tc.get("implementation", "")
            if impl:
                with st.expander("View Implementation Example", expanded=False):
                    st.code(impl, language="python")


# ---------------------------------------------------------------------------
# PAGE: Stack Trace Analyzer
# ---------------------------------------------------------------------------
def render_stack_trace():
    st.markdown(
        f"""
        <div style="margin-bottom:1.5rem; padding-bottom:0.85rem; border-bottom:1px solid {P['border']};">
            <h1 style="margin:0; font-size:2rem; font-weight:bold; color:{P['primary_text']};">
                🔎 Stack Trace Analyzer
            </h1>
            <p style="margin:0.3rem 0 0 0; color:{P['secondary_text']};">
                Paste an error log or stack trace to map it against review findings.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="cyber-card">
            <div style="font-size:1rem; font-weight:bold; color:{P['primary_text']}; margin-bottom:0.3rem;">
                Paste Error Log or Stack Trace
            </div>
            <div style="font-size:0.88rem; color:{P['secondary_text']}; line-height:1.5;">
                Extracts file references, line numbers, and function names, mapping them
                against current review findings without inventing code locations.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    stack_input = st.text_area(
        "Stack Trace Input",
        height=200,
        placeholder="Paste error log or stack trace here...\n\nExample:\nTraceback (most recent call last):\n  File \"app.py\", line 42, in handle_request\n    result = process(data)\nValueError: invalid literal for int()",
        label_visibility="collapsed",
        key="stack_trace_input",
    )

    col_btn, _ = st.columns([1.5, 4])
    with col_btn:
        analyze_btn = st.button("Analyze Stack Trace", type="primary", use_container_width=True, key="analyze_stack_btn")

    if analyze_btn:
        if not stack_input.strip():
            st.error("Please paste a stack trace or error log.")
        else:
            review_data = st.session_state.get("review_result")
            findings = review_data.get("findings", []) if review_data else []
            with st.spinner("Analyzing stack trace..."):
                result = analyze_stack_trace(stack_input, findings)
                st.session_state["stack_trace_result"] = result

    result = st.session_state.get("stack_trace_result")
    if result:
        st.markdown(f"<div class='section-header'>Analysis Result</div>", unsafe_allow_html=True)

        if not result.get("matched"):
            st.markdown(
                f"""
                <div class="stack-result-card" style="border-left-color:{P['bug']};">
                    <div style="font-size:1rem; font-weight:bold; color:{P['bug']}; margin-bottom:0.4rem;">
                        ⚠️ Unable to map this stack trace to an exact code location.
                    </div>
                    <div style="font-size:0.92rem; color:{P['secondary_text']};">
                        {result.get('reason', 'No file references found in the stack trace.')}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            extracted = result.get("extracted_files", [])
            error_txt = result.get("error", "")
            functions = result.get("functions", [])
            matched = result.get("matched_findings", [])
            explanation = result.get("explanation", "")
            suggested_fix = result.get("suggested_fix", "")

            files_badges = "".join(f'<span class="code-pill" style="margin:2px;">{r.get("file","?")}:{r.get("line","?")}</span>' for r in extracted)
            funcs_badges = " · ".join(functions) if functions else "None extracted"

            stack_card_html = f"""
            <div class="stack-result-card">
                <div style="font-size:1.05rem; font-weight:bold; color:{P['primary_text']}; margin-bottom:0.85rem;">
                    🔍 Stack Trace Mapped
                </div>
                <div class="kv-table">
                    <div class="kv-label">Detected Error</div>
                    <div class="kv-value"><div class="evidence-box" style="margin:0;">{html.escape(str(error_txt))}</div></div>
                    <div class="kv-label">Functions</div>
                    <div class="kv-value">{funcs_badges}</div>
                    <div class="kv-label">File Locations</div>
                    <div class="kv-value">{files_badges}</div>
                    <div class="kv-label">Explanation</div>
                    <div class="kv-value" style="color:{P['secondary_text']};">{html.escape(str(explanation))}</div>
                    {f'<div class="kv-label">Suggested Fix</div><div class="kv-value" style="color:{P["accent"]};">💡 {html.escape(str(suggested_fix))}</div>' if suggested_fix else ''}
                </div>
            </div>
            """
            st_clean_html(stack_card_html)

            if matched:
                st.markdown(
                    f"<div class='section-header'>Related Findings ({len(matched)})</div>",
                    unsafe_allow_html=True,
                )
                for mf in matched:
                    cat = str(mf.get("category", "bug")).lower()
                    color = P.get(cat, P["bug"])
                    st.markdown(
                        f"""
                        <div class="cyber-card" style="border-left:4px solid {color}; margin-bottom:0.75rem;">
                            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.4rem; margin-bottom:0.4rem;">
                                <span class="status-pill pill-{cat}">{cat.upper()}</span>
                                <span class="code-pill">{mf.get('file','?')} : Line {mf.get('line','?')}</span>
                            </div>
                            <div style="font-size:0.92rem; color:{P['primary_text']}; margin:0.4rem 0; line-height:1.5;">
                                {mf.get('problem') or mf.get('explanation','')}
                            </div>
                            {f'<div style="font-size:0.88rem; color:{P["accent"]}; margin-top:0.25rem;">💡 {mf.get("suggested_fix","")}</div>' if mf.get("suggested_fix") else ''}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )


# ---------------------------------------------------------------------------
# PAGE: Evaluation
# ---------------------------------------------------------------------------
def render_test_evaluation():
    st.markdown(
        f"""
        <div style="margin-bottom:1.5rem; padding-bottom:0.85rem; border-bottom:1px solid {P['border']};">
            <h1 style="margin:0; font-size:2rem; font-weight:bold; color:{P['primary_text']};">
                🧪 Evaluation Metrics
            </h1>
            <p style="margin:0.3rem 0 0 0; color:{P['secondary_text']};">
                Empirical precision, recall, and signal ratio against hand-tagged ground truth.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="cyber-card">
            <div style="font-weight:bold; font-size:1rem; color:{P['primary_text']}; margin-bottom:0.3rem;">
                Benchmark Evaluation Harness
            </div>
            <div style="font-size:0.9rem; color:{P['secondary_text']}; line-height:1.5;">
                Executes evaluation against the built-in hand-tagged dataset containing security
                vulnerabilities, logic bugs, and clean controls to measure detection quality.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("▶ Run Benchmark Evaluation", key="eval_run_btn", type="primary"):
        with st.spinner("Executing evaluation harness..."):
            try:
                res = call_backend_evaluate()
                st.session_state["eval_benchmark_result"] = res
                st.success("✅ Benchmark evaluation completed successfully!")
            except Exception as e:
                st.error(f"Evaluation error: {e}")

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

        st.markdown(f"<div class='section-header'>📊 Quality Metrics</div>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        metric_data = [
            (c1, "PRECISION", f"{prec:.1%}", "TP / (TP + FP)", P["accent"]),
            (c2, "RECALL", f"{rec:.1%}", "TP / (TP + FN)", P["performance"]),
            (c3, "SIGNAL RATIO", sig_pct, f"{act} Actionable / {total} Total", P["bug"]),
        ]
        for col, title, val, sub, color in metric_data:
            with col:
                st.markdown(
                    f"""
                    <div class="cyber-metric-card" style="border-top:3px solid {color};">
                        <div class="cyber-metric-title">{title}</div>
                        <div class="cyber-metric-value" style="color:{color};">{val}</div>
                        <div class="cyber-metric-sub">{sub}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        st.markdown(f"<div class='section-header'>🎯 Confusion Matrix</div>", unsafe_allow_html=True)
        cm1, cm2, cm3 = st.columns(3)
        cm_data = [
            (cm1, "TRUE POSITIVES (TP)", tp, P["accent"], "Correctly identified real issues"),
            (cm2, "FALSE POSITIVES (FP)", fp, P["bug"], "Spurious findings not in ground truth"),
            (cm3, "FALSE NEGATIVES (FN)", fn, P["security"], "Expected issues that were missed"),
        ]
        for col, title, val, color, desc in cm_data:
            with col:
                st.markdown(
                    f"""
                    <div class="cyber-card" style="text-align:center;">
                        <div style="color:{color}; font-weight:bold; font-size:0.82rem; margin-bottom:0.4rem;">{title}</div>
                        <div style="font-size:2.5rem; font-weight:bold; color:{P['primary_text']};">{val}</div>
                        <div style="color:{P['secondary_text']}; font-size:0.82rem; margin-top:0.25rem;">{desc}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
    else:
        st.info("Click **Run Benchmark Evaluation** above to execute the benchmark against ground truth data.")


# ---------------------------------------------------------------------------
# Sidebar Navigation
# ---------------------------------------------------------------------------
def render_sidebar():
    with st.sidebar:
        # Logo
        logo_png = Path(__file__).resolve().parent / "assets" / "logo.png"
        logo_svg = Path(__file__).resolve().parent / "assets" / "logo.svg"

        if logo_png.exists():
            st.image(str(logo_png), use_container_width=True)
        elif logo_svg.exists():
            st.image(str(logo_svg), use_container_width=True)
        else:
            st.markdown(
                f"""
                <div style="padding:10px 0; border-bottom:1px solid {P['border']}; margin-bottom:15px;">
                    <div style="font-size:1.2rem; font-weight:bold; color:{P['primary_text']}; letter-spacing:1px;">
                        🛡️ AI CODE REVIEW
                    </div>
                    <div style="font-size:0.8rem; color:{P['secondary_text']};">
                        Release-Risk Assistant
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Theme Toggle
        st.markdown(
            f"<p style='color:{P['secondary_text']}; font-size:0.78rem; font-weight:bold; "
            f"letter-spacing:1px; margin:0.5rem 0 0.4rem 0;'>THEME</p>",
            unsafe_allow_html=True,
        )
        theme_choice = st.radio(
            "Theme",
            options=["Dark", "Light"],
            index=0 if st.session_state["theme"] == "Dark" else 1,
            label_visibility="collapsed",
            horizontal=True,
            key="theme_radio_select",
        )
        if theme_choice != st.session_state["theme"]:
            st.session_state["theme"] = theme_choice
            st.rerun()

        st.markdown("---")

        # Navigation
        st.markdown(
            f"<p style='color:{P['secondary_text']}; font-size:0.78rem; font-weight:bold; "
            f"letter-spacing:1px; margin:0 0 0.5rem 0;'>NAVIGATION</p>",
            unsafe_allow_html=True,
        )

        nav_options = [
            ("Landing", "🏠  Home"),
            ("Dashboard", "📋  Dashboard"),
            ("Code Review", "🔍  Code Review"),
            ("Risk Analysis", "📊  Risk Analysis"),
            ("Findings", "⚠️  Findings"),
            ("Test Cases", "🧪  Test Cases"),
            ("Stack Trace", "🔎  Stack Trace"),
            ("Evaluation", "📈  Evaluation"),
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

        # System Status
        review_data = st.session_state.get("review_result")
        has_review = review_data is not None
        findings_count = len(review_data.get("findings", [])) if has_review else 0

        st.markdown(
            f"""
            <div style="font-size:0.8rem; color:{P['secondary_text']}; line-height:1.8;">
                <div><span class="pulse-dot"></span>
                    Backend: <span style="color:{P['accent']}; font-weight:bold;">Online</span>
                </div>
                <div style="font-size:0.72rem; color:{P['muted_text']}; font-family:monospace !important; word-break:break-all;">
                    {BACKEND_URL}
                </div>
                {f'<div style="margin-top:0.4rem; color:{P["muted_text"]}; font-size:0.78rem;">Review loaded · {findings_count} findings</div>' if has_review else ''}
            </div>
            """,
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Main Routing
# ---------------------------------------------------------------------------
render_sidebar()

active_page = st.session_state["active_page"]

if active_page == "Landing":
    render_landing()
elif active_page == "Dashboard":
    render_dashboard()
elif active_page == "Code Review":
    render_code_review()
elif active_page == "Risk Analysis":
    render_risk_analysis()
elif active_page == "Findings":
    render_findings()
elif active_page == "Test Cases":
    render_test_cases()
elif active_page == "Stack Trace":
    render_stack_trace()
elif active_page == "Evaluation":
    render_test_evaluation()
else:
    render_landing()
