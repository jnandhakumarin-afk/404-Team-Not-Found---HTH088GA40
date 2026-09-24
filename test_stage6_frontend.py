"""
Stage 6 - Streamlit Frontend & Final Dashboard Tests
======================================================
Covers:
  - Frontend app syntax & compilation
  - Typography verification (Times New Roman everywhere)
  - Color system verification (Dark & Light themes, exact semantic colors)
  - Single-screen dashboard constraint (no frontend/pages directory)
  - Logo asset location check (frontend/assets/README.md)
  - Backend response contract verification for Frontend consumption:
      - risk score and release_status
      - weighted risk breakdown (security x3, bug x2, performance x1.5, style x0.5)
      - signal ratio display
      - top 3 must-fix findings
      - deterministic findings order (Security -> Bug -> Performance -> Style)
      - evaluation metrics (precision, recall, signal ratio)
      - truncated files notice support
      - static-only fallback notice support
"""

import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from main import app
from frontend.app import PALETTES

client = TestClient(app)


def test_single_screen_structure():
    print("Testing single-screen structure (no multipage pages/ directory)...")
    frontend_dir = Path(__file__).resolve().parent / "frontend"
    pages_dir = frontend_dir / "pages"
    assert not pages_dir.exists(), "Multipage 'pages/' directory must NOT exist."
    app_py = frontend_dir / "app.py"
    assert app_py.exists(), "frontend/app.py must exist."
    print("  PASS  Single-screen structure verified (no pages/ folder)")


def test_logo_asset_location():
    print("Testing logo asset location...")
    assets_dir = Path(__file__).resolve().parent / "frontend" / "assets"
    readme = assets_dir / "README.md"
    assert assets_dir.exists(), "frontend/assets directory must exist."
    assert readme.exists(), "frontend/assets/README.md must exist."
    content = readme.read_text(encoding="utf-8")
    assert "logo.png" in content
    print("  PASS  Clear local asset location for logo verified")


def test_typography_and_font():
    print("Testing universal Times New Roman typography...")
    app_py = Path(__file__).resolve().parent / "frontend" / "app.py"
    content = app_py.read_text(encoding="utf-8")
    assert '"Times New Roman", Times, serif' in content
    print("  PASS  Times New Roman enforced across the frontend")


def test_color_system_consistency():
    print("Testing color system (Dark & Light themes, identical semantic colors)...")
    dark = PALETTES["Dark"]
    light = PALETTES["Light"]

    # Semantic colors MUST be identical in both themes
    semantic_keys = ["security", "bug", "performance", "style", "accent"]
    expected_colors = {
        "security": "#F4534F",
        "bug": "#FF9838",
        "performance": "#54A1FF",
        "style": "#8A8FA3",
        "accent": "#2DD4BF",
    }

    for key, expected_hex in expected_colors.items():
        assert dark[key].upper() == expected_hex.upper(), f"Dark {key} mismatch: {dark[key]}"
        assert light[key].upper() == expected_hex.upper(), f"Light {key} mismatch: {light[key]}"

    # Backgrounds and card surfaces
    assert dark["bg"] == "#1A1B25"
    assert dark["card_bg"] == "#232530"
    assert dark["border"] == "#3A3D4D"

    assert light["bg"] == "#F4F6F8"
    assert light["card_bg"] == "#FFFFFF"
    assert light["border"] == "#D9DDE5"
    print("  PASS  Exact color system verified for both Dark and Light themes")


def test_backend_contract_for_frontend():
    print("Testing backend contract completeness for frontend consumption...")
    resp = client.post("/api/review", json={"code": "eval('secret')"})
    assert resp.status_code == 200
    data = resp.json()

    # 1. Summary
    assert "summary" in data

    # 2. Risk Score & Breakdown
    assert "risk" in data
    risk = data["risk"]
    assert "total_risk" in risk
    assert "release_status" in risk
    assert "breakdown" in risk
    breakdown = risk["breakdown"]
    assert breakdown["security"]["weight"] == 3
    assert breakdown["bug"]["weight"] == 2
    assert breakdown["performance"]["weight"] == 1.5
    assert breakdown["style"]["weight"] == 0.5

    # 3. Top 3 Must Fix
    assert "top_must_fix" in risk
    assert isinstance(risk["top_must_fix"], list)
    assert len(risk["top_must_fix"]) <= 3

    # 4. Strict Finding Order
    findings = data["findings"]
    assert isinstance(findings, list)
    prio = {"security": 1, "bug": 2, "performance": 3, "style": 4}
    for i in range(len(findings) - 1):
        cat1 = findings[i].get("category", "style").lower()
        cat2 = findings[i + 1].get("category", "style").lower()
        assert prio.get(cat1, 5) <= prio.get(cat2, 5), f"Order violation: {cat1} before {cat2}"

    # 5. Signal Ratio & Evaluation Metrics
    assert "evaluation" in data
    eval_data = data["evaluation"]
    assert "precision" in eval_data
    assert "recall" in eval_data
    assert "signal_ratio" in eval_data
    assert "signal_ratio_pct" in eval_data
    assert "actionable_findings" in eval_data
    assert "total_findings" in eval_data

    # 6. Notices: Truncation & Fallback flags
    assert "truncated_files" in data
    assert "fallback_to_static" in data
    print("  PASS  Backend delivers all 10 required frontend dashboard sections")


if __name__ == "__main__":
    tests = [
        test_single_screen_structure,
        test_logo_asset_location,
        test_typography_and_font,
        test_color_system_consistency,
        test_backend_contract_for_frontend,
    ]

    total = 0
    passed = 0
    failed = 0

    print(f"\n{'-' * 60}")
    print("  Stage 6 - Streamlit Frontend & Final Dashboard Test Suite")
    print(f"{'-' * 60}")

    for t in tests:
        total += 1
        try:
            t()
            passed += 1
        except Exception as exc:
            failed += 1
            print(f"  FAIL  {t.__name__}: {exc}")

    print(f"\n{'=' * 60}")
    print(f"  Results: {passed}/{total} passed, {failed} failed")
    print(f"{'=' * 60}")
    if failed:
        sys.exit(1)
