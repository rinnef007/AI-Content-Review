from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="AI Content Review API", version="0.1.0")

jobs: dict[str, dict] = {}


class AnalyzeRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1)
    mode: str = Field(default="review", pattern="^(summary|review|script)$")
    spoiler: bool = False


def local_analyze(payload: AnalyzeRequest) -> dict:
    words = payload.content.split()
    sentences = [s.strip() for s in payload.content.replace("!", ".").replace("?", ".").split(".") if s.strip()]
    freq = Counter(w.strip(".,!?;:()[]{}\"'").lower() for w in words)
    keywords = [w for w, _ in freq.most_common(8) if len(w) > 3]
    excerpt = " ".join(sentences[:3])
    if not excerpt:
        excerpt = payload.content[:500]
    summary = f"{payload.title}: {excerpt}"
    review = (
        f"Đánh giá nhanh về {payload.title}: nội dung có khoảng {len(words)} từ "
        f"và {len(sentences)} câu. Các từ khóa nổi bật: {', '.join(keywords) or 'chưa xác định'}."
    )
    if payload.mode == "summary":
        review = summary
    elif payload.mode == "script":
        review = f"Mở đầu: {summary}\n\nĐiểm chính: {', '.join(keywords) or 'chưa xác định'}.\n\nKết: Đây là phần cần tiếp tục phân tích khi bật AI provider."
    return {
        "summary": summary,
        "review": review,
        "keywords": keywords,
        "stats": {"words": len(words), "sentences": len(sentences)},
        "provider": "local",
        "spoiler": payload.spoiler,
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "api", "version": "0.1.0"}


@app.post("/api/v1/analyze")
def analyze(payload: AnalyzeRequest) -> dict:
    job_id = str(uuid4())
    result = local_analyze(payload)
    jobs[job_id] = {
        "id": job_id,
        "status": "completed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input": payload.model_dump(),
        "result": result,
    }
    return jobs[job_id]


@app.get("/api/v1/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
