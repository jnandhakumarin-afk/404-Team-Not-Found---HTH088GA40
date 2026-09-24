from importlib import import_module

from parser.parser import parse_code, extract_changed_lines
from analyzer.static_analyzer import analyze_code
from ai.reviewer import review_code
from risk.risk_engine import calculate_risk
from models.ingest import IngestRequest, IngestResponse
from parser.github_ingest import ingest_github

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


# DEDUPLICATED /api/review ENDPOINT
@app.post("/api/review")
def review_endpoint(data: dict):
    code = data.get("code", "")
    static_issues = analyze_code(code)
    review = review_code(
        code,
        static_issues
    )
    risk = calculate_risk(review["issues"])
    return {
        "summary": review["summary"],
        "issues": review["issues"],
        "total_issues": review["total_issues"],
        "risk": risk
    }


# GITHUB PR / COMMIT INGESTION ENDPOINT
@app.post("/api/ingest", response_model=IngestResponse)
async def ingest_endpoint(req: IngestRequest) -> IngestResponse:
    return await ingest_github(req.url)