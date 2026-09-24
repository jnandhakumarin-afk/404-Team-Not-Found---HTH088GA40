from importlib import import_module

from parser.parser import parse_code, extract_changed_lines
from analyzer.static_analyzer import analyze_code
from ai.reviewer import review_code, _load_env_if_present

_load_env_if_present()
from risk.risk_engine import calculate_risk
from models.ingest import IngestRequest, IngestResponse
from models.analysis import AnalyzeFilesRequest, AnalyzeFilesResponse
from models.review import ReviewRequest
from parser.github_ingest import ingest_github
from analyzer.runner import analyze_changed_files
from evaluation.evaluator import calculate_metrics, evaluate_against_dataset
from evaluation.dataset import EVAL_SAMPLES

try:
    FastAPI = getattr(import_module("fastapi"), "FastAPI")
    CORSMiddleware = getattr(
        import_module("fastapi.middleware.cors"), "CORSMiddleware"
    )
except ImportError as exc:
    raise RuntimeError(
        "FastAPI is required to run this application. Install it with "
        "'pip install fastapi uvicorn'."
    ) from exc

app = FastAPI(
    title="AI Code Review & Release-Risk Assistant",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


@app.get("/health")
def health_check():
    return {
        "status": "success"
    }


@app.get("/api/status")
def api_status():
    return {
        "status": "running",
        "message": "AI Code Review & Release-Risk Assistant backend is running"
    }


@app.post("/api/parse-code")
def parse_code_endpoint(data: dict):
    code = data.get("code", "")
    return parse_code(code)


@app.post("/api/parse-diff")
def parse_diff_endpoint(data: dict):
    diff = data.get("diff", "")
    changed_lines = extract_changed_lines(diff)
    return {
        "changed_lines": changed_lines,
        "total_changed_lines": len(changed_lines)
    }


@app.post("/api/analyze")
def analyze_endpoint(data: dict):
    code = data.get("code", "")
    issues = analyze_code(code)
    return {
        "total_issues": len(issues),
        "issues": issues
    }


# CONTEXTUAL AI CODE REVIEW ENDPOINT (STAGE 3)
@app.post("/api/review")
async def review_endpoint(req: ReviewRequest):
    """
    Perform contextual code review. Runs static analysis as ground truth,
    then queries Anthropic API for contextual findings, deduplicates,
    validates via Pydantic, and returns combined findings with risk.
    """
    url = req.url
    files = req.files
    code = req.code
    diff = req.diff
    truncated_files = []

    if url and not files:
        ingest_res = await ingest_github(url)
        files = [f.model_dump() if hasattr(f, "model_dump") else f for f in ingest_res.files]
        truncated_files = getattr(ingest_res, "truncated_files", [])

    if files:
        static_findings, _, _ = analyze_changed_files(files)
        review = review_code(files=files, static_issues=static_findings, diff=diff)
    else:
        code_str = code or ""
        static_issues = analyze_code(code_str)
        review = review_code(code=code_str, static_issues=static_issues, diff=diff)

    risk = calculate_risk(review["issues"])
    ordered_findings = risk.get("ordered_findings", review.get("findings", review["issues"]))

    # Stage 5 — evaluation metrics
    custom_expected = req.expected
    if custom_expected is not None:
        eval_metrics = calculate_metrics(ordered_findings, custom_expected)
    else:
        eval_metrics = evaluate_against_dataset(ordered_findings)

    return {
        "summary": review["summary"],
        "findings": ordered_findings,
        "total_findings": len(ordered_findings),
        "issues": ordered_findings,
        "total_issues": len(ordered_findings),
        "risk": risk,
        "truncated_files": truncated_files,
        "evaluation": {
            "true_positives": eval_metrics["true_positives"],
            "false_positives": eval_metrics["false_positives"],
            "false_negatives": eval_metrics["false_negatives"],
            "precision": eval_metrics["precision"],
            "recall": eval_metrics["recall"],
            "actionable_findings": eval_metrics["actionable_findings"],
            "total_findings": eval_metrics["total_findings"],
            "signal_ratio": eval_metrics["signal_ratio"],
            "signal_ratio_pct": eval_metrics["signal_ratio_pct"],
        },
        "precision": eval_metrics["precision"],
        "recall": eval_metrics["recall"],
        "signal_ratio": eval_metrics["signal_ratio"],
        "actionable_findings": eval_metrics["actionable_findings"],
        "fallback_to_static": review.get("fallback_to_static", False),
        "provider": review.get("provider", "static"),
        "errors": review.get("errors", []),
    }


# GITHUB PR / COMMIT INGESTION ENDPOINT
@app.post("/api/ingest", response_model=IngestResponse)
async def ingest_endpoint(req: IngestRequest) -> IngestResponse:
    return await ingest_github(req.url)


# STAGE 2 — STATIC ANALYSIS ENDPOINT
@app.post("/api/analyze-files", response_model=AnalyzeFilesResponse)
def analyze_files_endpoint(req: AnalyzeFilesRequest) -> AnalyzeFilesResponse:
    """
    Run static analysis over changed files from a Stage 1 /api/ingest response.

    Accepts the ``files`` array directly from the ingest response and returns
    normalized findings from Ruff, Bandit (Python) and ESLint (JS/TS).
    This endpoint must be called BEFORE any LLM integration.
    """
    findings, skipped, tool_errors = analyze_changed_files(req.files)
    return AnalyzeFilesResponse(
        total_findings=len(findings),
        findings=findings,
        skipped_files=skipped,
        tool_errors=tool_errors,
    )


# STAGE 5 — TEST HARNESS / EVALUATION METRICS ENDPOINT
@app.post("/api/evaluate")
def evaluate_endpoint(data: dict):
    """
    Evaluate system findings against the hand-tagged ground-truth dataset.

    Accepts:
      - ``findings``     (list) — system findings to evaluate
      - ``use_dataset``  (bool) — if True (default), evaluate against the
                                  built-in EVAL_SAMPLES ground truth
      - ``expected``     (list) — optional override expected issues list

    Returns precision, recall, signal_ratio, TP/FP/FN counts.
    """
    findings = data.get("findings", [])
    use_dataset = data.get("use_dataset", True)
    custom_expected = data.get("expected", None)

    if custom_expected is not None:
        metrics = calculate_metrics(findings, custom_expected)
    elif use_dataset:
        metrics = evaluate_against_dataset(findings)
    else:
        metrics = calculate_metrics(findings, [])

    # Strip private _tp_items/_fp_items/_fn_items from public response
    public = {k: v for k, v in metrics.items() if not k.startswith("_")}
    return public