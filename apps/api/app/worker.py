from __future__ import annotations

from pathlib import Path

from app.database import SessionLocal
from app.job_queue import process_jobs
from app.job_queue import update_job
from app.knowledge import persist_analysis
from app.main import AnalyzeRequest, analyze_content, extract_upload
from app.models import Episode


def handle(payload: dict) -> dict:
    kind = payload.get("kind", "analysis")
    file_path = payload.get("file_path")

    if file_path:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Uploaded file not found: {file_path}")
        content, source = extract_upload(path.read_bytes(), payload.get("filename", path.name))
        request = AnalyzeRequest(title=payload["title"], content=content, mode=payload.get("mode", "review"), spoiler=payload.get("spoiler", False))
        result = analyze_content(request)
        result["source"] = source
        result["extracted_text"] = content

        if kind == "upload_episode_analysis":
            db = SessionLocal()
            try:
                episode = db.get(Episode, payload["episode_id"])
                if not episode or episode.project_id != payload["project_id"]:
                    raise ValueError("Episode not found")
                episode.content = content
                episode.source_filename = payload.get("filename")
                episode.source_type = source["type"]
                persisted = persist_analysis(db, payload["project_id"], episode, result)
                db.commit()
                return {"episode_id": episode.id, "analysis": result, "persisted": persisted}
            finally:
                db.close()
        return result

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
