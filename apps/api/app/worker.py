from __future__ import annotations

from app.database import SessionLocal
from app.job_queue import process_jobs
from app.knowledge import persist_analysis
from app.main import AnalyzeRequest, analyze_content
from app.models import Episode


def handle(payload: dict) -> dict:
    kind = payload.get("kind", "analysis")
    request = AnalyzeRequest.model_validate({k: payload[k] for k in ("title", "content", "mode", "spoiler") if k in payload})
    if kind != "episode_analysis":
        return analyze_content(request)

    db = SessionLocal()
    try:
        episode = db.get(Episode, payload["episode_id"])
        if not episode or episode.project_id != payload["project_id"]:
            raise ValueError("Episode not found")
        result = analyze_content(request)
        persisted = persist_analysis(db, payload["project_id"], episode, result)
        db.commit()
        return {"episode_id": episode.id, "analysis": result, "persisted": persisted}
    finally:
        db.close()


if __name__ == "__main__":
    process_jobs(handle)
