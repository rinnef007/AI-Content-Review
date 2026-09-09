from __future__ import annotations
from pathlib import Path
from app.ai_provider import transcribe_audio
from app.database import SessionLocal
from app.job_queue import process_jobs
from app.knowledge import persist_analysis
from app.main import AnalyzeRequest,analyze_content,extract_upload
from app.media import extract_audio,media_kind,probe_media,normalize_segments,transcript_to_srt
from app.models import Episode,ReviewScript
from app.review_script import generate_review_script

def handle(payload:dict)->dict:
    kind=payload.get("kind","analysis");file_path=payload.get("file_path")
    if kind=="review_script":
        script=generate_review_script(title=payload["title"],segments=payload["segments"],style=payload.get("style","youtube"))
        db=SessionLocal()
        try:
            episode=db.get(Episode,payload["episode_id"])
            if not episode or episode.project_id!=payload["project_id"]:raise ValueError("Episode not found")
            latest=max([s.version for s in episode.review_scripts],default=0)
            row=ReviewScript(episode_id=episode.id,version=latest+1,style=script.get("style",payload.get("style","youtube")),title=script.get("title",episode.title),hook=script.get("hook",""),intro=script.get("intro",""),segments=script.get("segments",[]),outro=script.get("outro",""),provider=script.get("provider"),model=script.get("model"),status="draft")
            db.add(row)
            analysis=dict(episode.analysis or {});analysis["review_script"]={**script,"id":row.id,"version":row.version,"episode_id":episode.id,"status":row.status};episode.analysis=analysis
            db.commit();db.refresh(row)
            return {"episode_id":episode.id,"review_script":{**script,"id":row.id,"version":row.version,"episode_id":episode.id,"status":row.status}}
        finally:db.close()
    if kind=="media_episode_analysis":
        path=Path(file_path)
        if not path.exists():raise FileNotFoundError(f"Media file not found: {file_path}")
        media_type=media_kind(payload.get("filename",path.name));metadata=probe_media(str(path));audio_path=path.with_suffix(".wav");extract_audio(str(path),str(audio_path));transcript=transcribe_audio(str(audio_path));content=transcript.get("text","").strip()
        if not content:raise ValueError("STT không nhận diện được lời thoại trong media")
        segments=normalize_segments(transcript);transcript["segments"]=segments;transcript["srt"]=transcript_to_srt(segments);transcript["segment_count"]=len(segments)
        request=AnalyzeRequest(title=payload["title"],content=content,mode="review",spoiler=False);result=analyze_content(request);result["media"]={"type":media_type,"filename":payload.get("filename"),"metadata":metadata};result["transcript"]=transcript
        db=SessionLocal()
        try:
            episode=db.get(Episode,payload["episode_id"])
            if not episode or episode.project_id!=payload["project_id"]:raise ValueError("Episode not found")
            episode.content=content;episode.source_filename=payload.get("filename");episode.source_type=media_type;episode.analysis=result;persisted=persist_analysis(db,payload["project_id"],episode,result);db.commit();return {"episode_id":episode.id,"analysis":result,"persisted":persisted}
        finally:db.close()
    if file_path:
        path=Path(file_path)
        if not path.exists():raise FileNotFoundError(f"Uploaded file not found: {file_path}")
        content,source=extract_upload(path.read_bytes(),payload.get("filename",path.name));request=AnalyzeRequest(title=payload["title"],content=content,mode=payload.get("mode","review"),spoiler=payload.get("spoiler",False));result=analyze_content(request);result["source"]=source;result["extracted_text"]=content
        if kind=="upload_episode_analysis":
            db=SessionLocal()
            try:
                episode=db.get(Episode,payload["episode_id"])
                if not episode or episode.project_id!=payload["project_id"]:raise ValueError("Episode not found")
                episode.content=content;episode.source_filename=payload.get("filename");episode.source_type=source["type"];persisted=persist_analysis(db,payload["project_id"],episode,result);db.commit();return {"episode_id":episode.id,"analysis":result,"persisted":persisted}
            finally:db.close()
        return result
    request=AnalyzeRequest.model_validate({k:payload[k] for k in ("title","content","mode","spoiler") if k in payload})
    if kind!="episode_analysis":return analyze_content(request)
    db=SessionLocal()
    try:
        episode=db.get(Episode,payload["episode_id"])
        if not episode or episode.project_id!=payload["project_id"]:raise ValueError("Episode not found")
        result=analyze_content(request);persisted=persist_analysis(db,payload["project_id"],episode,result);db.commit();return {"episode_id":episode.id,"analysis":result,"persisted":persisted}
    finally:db.close()
if __name__=="__main__":process_jobs(handle)
