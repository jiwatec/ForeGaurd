"""Local analysis API. No execution or approval endpoints exist here."""

from pathlib import PurePosixPath
from uuid import uuid4

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.classifier import assess_command


app = FastAPI(title="ForeGuard", docs_url=None, redoc_url=None)


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


@app.post("/api/commands/analyze")
def analyze(payload: CommandRequest):
    assessment = assess_command(payload.command)
    return {
        "request_id": str(uuid4()), **assessment,
        "requires_approval": assessment["decision"] == "REVIEW",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765, access_log=False)
