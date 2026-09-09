from __future__ import annotations

from app.job_queue import process_jobs
from app.main import AnalyzeRequest, analyze_content


def handle(payload: dict) -> dict:
    request = AnalyzeRequest.model_validate(payload)
    return analyze_content(request)


if __name__ == "__main__":
    process_jobs(handle)
