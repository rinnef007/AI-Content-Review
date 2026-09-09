from __future__ import annotations

from pathlib import Path

from app.ai_provider import transcribe_audio
from app.database import SessionLocal
from app.job_queue import process_jobs
from app.knowledge import persist_analysis
from app.main import AnalyzeRequest, analyze_content, extract_upload
from app.media import extract_audio, media_kind, probe_media
from app.models import Episode


def handle(payload: dict) -> dict:
    kind = payload.get("kind", "analysis")
    file_path = payload.get("file_path")

    if kind == "media_episode_analysis":
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Media file not found: {file_path}")
        media_type = media_kind(payload.get("filename", path.name))
        metadata = probe_media(str(path))
        audio_path = path.with_suffix(".wav")
        extract_audio(str(path), str(audio_path))
        transcript = transcribe_audio(str(audio_path))
        content = transcript.get("text", "").strip()
        if not content:
            raise ValueError("STT không nhận diện được lời thoại trong media")

        request = AnalyzeRequest(title=payload["title"], content=content, mode="review", spoiler=False)
        result = analyze_content(request)
        result["media"] = {"type": media_type, "filename": payload.get("filename"), "metadata": metadata}
        result["transcript"] = transcript

        db = SessionLocal()
        try:
            episode = db.get(Episode, payload["episode_id"])
            if not episode or episode.project_id != payload["project_id"]:
                raise ValueError("Episode not found")
            episode.content = content
            episode.analysis = result
            persisted = persist_analysis(db, payload["project_id"], episode, result)
            db.commit()
            return {"episode_id": episode.id, "analysis": result, "persisted": persisted}
        finally:
            db.close()

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
