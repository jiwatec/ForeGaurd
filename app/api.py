"""Local assessment and authenticated review API. No command execution."""

import os
from hmac import compare_digest
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

from fastapi import FastAPI, Header, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.store import ApprovalError, Store


app = FastAPI(title="ForeGuard", docs_url=None, redoc_url=None)
ASSETS = Path(__file__).parent / "dashboard"


@app.middleware("http")
async def private_responses(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )
    return response


class CommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    command: str = Field(min_length=1, max_length=4096)
    cwd: str = Field(min_length=1, max_length=4096)
    source: str = Field(min_length=1, max_length=128)

    @field_validator("command", "cwd", "source")
    @classmethod
    def nonempty(cls, value):
        if not value.strip() or "\x00" in value:
            raise ValueError("Invalid text")
        return value

    @field_validator("cwd")
    @classmethod
    def absolute_directory(cls, value):
        if not PurePosixPath(value).is_absolute() or ".." in PurePosixPath(value).parts:
            raise ValueError("An absolute working directory is required")
        return value


class DecisionRequest(CommandRequest):
    decision: str = Field(pattern="^(APPROVE|REJECT)$")


def audit_store():
    path = os.environ.get("FOREGUARD_DB_PATH")
    if not path or not os.path.isabs(path):
        raise RuntimeError("Audit storage is not configured")
    return Store(path)


def authorized(authorization):
    token = os.environ.get("FOREGUARD_ADMIN_TOKEN")
    if not token or not authorization or not authorization.startswith("Bearer "):
        return False
    return compare_digest(authorization[7:], token)


def blocked_error(status, reason):
    return JSONResponse(status_code=status, content={
        "request_id": str(uuid4()), "category": "UNKNOWN", "risk_score": 100,
        "decision": "BLOCK", "reasons": [reason], "requires_approval": False,
    })


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    # Do not echo raw input, which may contain secrets, in error responses.
    return blocked_error(422, "Invalid analysis request")


@app.exception_handler(Exception)
async def processing_failure(request, exc):
    return blocked_error(500, "Analysis unavailable")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/review", include_in_schema=False)
def dashboard():
    return FileResponse(ASSETS / "index.html")


@app.get("/review/app.js", include_in_schema=False)
def dashboard_script():
    return FileResponse(ASSETS / "app.js", media_type="application/javascript")


@app.get("/review/style.css", include_in_schema=False)
def dashboard_style():
    return FileResponse(ASSETS / "style.css", media_type="text/css")


@app.post("/api/commands/analyze")
def analyze(payload: CommandRequest):
    store = audit_store()
    request_id = store.submit(payload.command, payload.cwd, payload.source)
    assessment = store.get(request_id)["assessment"]
    return {
        "request_id": request_id, **assessment,
        "requires_approval": assessment["decision"] == "REVIEW",
    }


@app.get("/api/requests")
def history(authorization: str | None = Header(default=None),
            limit: int = Query(default=50, ge=1, le=100),
            offset: int = Query(default=0, ge=0)):
    if not authorized(authorization):
        return blocked_error(401, "Review access denied")
    return {"requests": audit_store().history(limit=limit, offset=offset)}


@app.post("/api/requests/{request_id}/decide")
def decide(request_id: UUID, payload: DecisionRequest,
           authorization: str | None = Header(default=None)):
    if not authorized(authorization):
        return blocked_error(401, "Review access denied")
    try:
        return audit_store().decide(str(request_id), payload.decision,
                                    command=payload.command, cwd=payload.cwd,
                                    source=payload.source)
    except ApprovalError:
        return blocked_error(409, "Request cannot be decided")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765, access_log=False)
