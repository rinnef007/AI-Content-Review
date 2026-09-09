from __future__ import annotations
import io,os,re
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
import fitz,pytesseract
from fastapi import Depends,FastAPI,File,Form,HTTPException,UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse,Response
from PIL import Image,ImageOps
from pydantic import BaseModel,Field
from pypdf import PdfReader
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.ai_provider import analyze_with_openai
from app.database import get_db,init_db
from app.exporter import script_html,script_text
from app.job_queue import enqueue,get_job
from app.knowledge import build_timeline
from app.models import Character as CharacterModel,Episode,Event as EventModel,Project,Relationship,ReviewScript
UPLOAD_DIR=Path(os.getenv("UPLOAD_DIR","/data/uploads"));UPLOAD_DIR.mkdir(parents=True,exist_ok=True)
@asynccontextmanager
async def lifespan(_:FastAPI): init_db();yield
app=FastAPI(title="AI Content Review API",version="1.4.0",lifespan=lifespan)
CORS_ORIGINS=[x.strip() for x in os.getenv("CORS_ORIGINS","http://localhost:3000").split(",") if x.strip()];app.add_middleware(CORSMiddleware,allow_origins=CORS_ORIGINS,allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
DOCUMENT_EXTENSIONS={".pdf",".png",".jpg",".jpeg",".webp",".bmp",".tiff"};MEDIA_EXTENSIONS={".mp4",".mov",".mkv",".webm",".avi",".m4v",".mp3",".wav",".m4a",".aac",".flac",".ogg"};MAX_UPLOAD_BYTES=25*1024*1024;MAX_MEDIA_BYTES=1024*1024*1024;MAX_PDF_PAGES=30;AI_PROVIDER=os.getenv("AI_PROVIDER","local").strip().lower()
class Character(BaseModel):name:str;role:str|None=None;evidence:str|None=None
class Event(BaseModel):event:str;characters:list[str]=Field(default_factory=list);evidence:str|None=None
class RelationshipPayload(BaseModel):from_:str=Field(alias="from");to:str;relation:str;evidence:str|None=None;model_config={"populate_by_name":True}
class StructuredAnalysis(BaseModel):summary:str;review:str;keywords:list[str]=Field(default_factory=list);characters:list[Character]=Field(default_factory=list);events:list[Event]=Field(default_factory=list);relationships:list[RelationshipPayload]=Field(default_factory=list);conflicts:list[str]=Field(default_factory=list);key_details:list[str]=Field(default_factory=list)
class AnalyzeRequest(BaseModel):title:str=Field(min_length=1,max_length=300);content:str=Field(min_length=1);mode:str=Field(default="review",pattern="^(summary|review|script)$");spoiler:bool=False
class ProjectCreate(BaseModel):name:str=Field(min_length=1,max_length=300);description:str|None=None
class EpisodeCreate(BaseModel):title:str=Field(min_length=1,max_length=300);content:str|None=None;source_type:str="text"
class ReviewScriptUpdate(BaseModel):hook:str|None=None;intro:str|None=None;segments:list[dict]=Field(default_factory=list);outro:str|None=None

def local_analyze(p):
 words=p.content.split();sentences=[s.strip() for s in re.split(r"[.!?]+",p.content) if s.strip()];freq=Counter(w.strip(".,!?;:()[]{}\"'").lower() for w in words);keywords=[w for w,_ in freq.most_common(8) if len(w)>3];summary=f"{p.title}: {' '.join(sentences[:3]) or p.content[:500]}";review=f"Đánh giá nhanh về {p.title}: nội dung có khoảng {len(words)} từ và {len(sentences)} câu. Các từ khóa nổi bật: {', '.join(keywords) or 'chưa xác định'}.";return {**StructuredAnalysis(summary=summary,review=review,keywords=keywords).model_dump(by_alias=True),"provider":"local","spoiler":p.spoiler,"stats":{"words":len(words),"sentences":len(sentences)}}
def analyze_content(p):
 if AI_PROVIDER=="openai":
  raw=analyze_with_openai(title=p.title,content=p.content,mode=p.mode,spoiler=p.spoiler);s=StructuredAnalysis.model_validate(raw);return {**s.model_dump(by_alias=True),**{k:v for k,v in raw.items() if k not in StructuredAnalysis.model_fields},"stats":{"words":len(p.content.split())}}
 return local_analyze(p)
def ocr_image(image):image=ImageOps.exif_transpose(image).convert("RGB");image.thumbnail((3000,3000));return pytesseract.image_to_string(image,lang="vie+eng",config="--psm 6").strip()
def extract_pdf(data):
 reader=PdfReader(io.BytesIO(data));pages=len(reader.pages)
 if pages>MAX_PDF_PAGES:raise ValueError(f"PDF vượt quá giới hạn {MAX_PDF_PAGES} trang ở V1")
 text="\n\n".join((p.extract_text() or "").strip() for p in reader.pages if (p.extract_text() or "").strip())
 if text:return text,pages,False
 doc=fitz.open(stream=data,filetype="pdf")
 try:return "\n\n".join(f"[Trang {i+1}]\n{ocr_image(Image.open(io.BytesIO(page.get_pixmap(matrix=fitz.Matrix(1.7,1.7),alpha=False).tobytes('png'))))}" for i,page in enumerate(doc)),pages,True
 finally:doc.close()
def save_upload(file,limit):
 filename=Path(file.filename or "upload").name;data=file.file.read(limit+1)
 if len(data)>limit:raise HTTPException(status_code=413,detail=f"File vượt quá giới hạn {limit//(1024*1024)} MB")
 target=UPLOAD_DIR/f"{uuid4().hex}{Path(filename).suffix.lower()}";target.write_bytes(data);return str(target),filename,len(data)
def project_dict(p):return {"id":p.id,"name":p.name,"description":p.description,"created_at":p.created_at}
def script_dict(s):return {"id":s.id,"episode_id":s.episode_id,"version":s.version,"style":s.style,"title":s.title,"hook":s.hook,"intro":s.intro,"segments":s.segments,"outro":s.outro,"provider":s.provider,"model":s.model,"status":s.status,"created_at":s.created_at,"updated_at":s.updated_at}
@app.get("/health")
def health():return {"status":"ok","service":"api","version":"1.4.0","ocr":"tesseract","ai_provider":AI_PROVIDER,"queue":"redis","media":"ffmpeg","srt":True,"review_script":True,"export":True,"review_script_versions":True}
@app.get("/api/v1/projects")
def list_projects(db:Session=Depends(get_db)):return [project_dict(p) for p in db.scalars(select(Project).order_by(Project.created_at.desc())).all()]
@app.post("/api/v1/projects")
def create_project(payload:ProjectCreate,db:Session=Depends(get_db)):p=Project(name=payload.name,description=payload.description);db.add(p);db.commit();db.refresh(p);return project_dict(p)
@app.get("/api/v1/projects/{project_id}")
def get_project(project_id:str,db:Session=Depends(get_db)):
 p=db.get(Project,project_id)
 if not p:raise HTTPException(404,"Project not found")
 return {**project_dict(p),"episodes":[{"id":e.id,"title":e.title,"source_type":e.source_type,"source_filename":e.source_filename,"created_at":e.created_at,"review_script":bool((e.analysis or {}).get("review_script"))} for e in p.episodes],"characters":[{"id":c.id,"name":c.name,"role":c.role,"aliases":c.aliases} for c in p.characters],"events":[{"id":e.id,"title":e.title,"episode_id":e.episode_id,"evidence":e.evidence} for e in p.events]}
@app.post("/api/v1/projects/{project_id}/episodes")
def create_episode(project_id:str,payload:EpisodeCreate,db:Session=Depends(get_db)):
 if not db.get(Project,project_id):raise HTTPException(404,"Project not found")
 e=Episode(project_id=project_id,title=payload.title,content=payload.content,source_type=payload.source_type);db.add(e);db.commit();db.refresh(e);return {"id":e.id,"project_id":project_id,"title":e.title,"source_type":e.source_type,"created_at":e.created_at}
@app.post("/api/v1/projects/{project_id}/episodes/upload")
def upload_episode(project_id:str,file:UploadFile=File(...),title:str|None=Form(default=None),db:Session=Depends(get_db)):
 if not db.get(Project,project_id):raise HTTPException(404,"Project not found")
 filename=Path(file.filename or "upload").name
 if Path(filename).suffix.lower() not in DOCUMENT_EXTENSIONS:raise HTTPException(415,"Định dạng tài liệu không được hỗ trợ")
 path,filename,_=save_upload(file,MAX_UPLOAD_BYTES);e=Episode(project_id=project_id,title=title or Path(filename).stem,source_type="file",source_filename=filename);db.add(e);db.commit();db.refresh(e);return {"episode":{"id":e.id,"title":e.title},"job":enqueue({"kind":"upload_episode_analysis","project_id":project_id,"episode_id":e.id,"file_path":path,"filename":filename,"title":e.title,"mode":"review","spoiler":False})}
@app.post("/api/v1/projects/{project_id}/episodes/media")
def upload_media_episode(project_id:str,file:UploadFile=File(...),title:str|None=Form(default=None),db:Session=Depends(get_db)):
 if not db.get(Project,project_id):raise HTTPException(404,"Project not found")
 filename=Path(file.filename or "media").name;suffix=Path(filename).suffix.lower()
 if suffix not in MEDIA_EXTENSIONS:raise HTTPException(415,"Định dạng media không được hỗ trợ")
 path,filename,size=save_upload(file,MAX_MEDIA_BYTES);typ="video" if suffix in {".mp4",".mov",".mkv",".webm",".avi",".m4v"} else "audio";e=Episode(project_id=project_id,title=title or Path(filename).stem,source_type=typ,source_filename=filename);db.add(e);db.commit();db.refresh(e);return {"episode":{"id":e.id,"title":e.title,"source_type":typ,"size":size},"job":enqueue({"kind":"media_episode_analysis","project_id":project_id,"episode_id":e.id,"file_path":path,"filename":filename,"title":e.title})}
@app.post("/api/v1/projects/{project_id}/episodes/{episode_id}/analyze")
def analyze_episode(project_id:str,episode_id:str,db:Session=Depends(get_db)):
 e=db.get(Episode,episode_id)
 if not e or e.project_id!=project_id:raise HTTPException(404,"Episode not found")
 if not e.content:raise HTTPException(422,"Episode chưa có nội dung")
 return {"job":enqueue({"kind":"episode_analysis","project_id":project_id,"episode_id":episode_id,"title":e.title,"content":e.content,"mode":"review","spoiler":False}),"episode_id":episode_id}
@app.post("/api/v1/projects/{project_id}/episodes/{episode_id}/review-script")
def create_review_script(project_id:str,episode_id:str,style:str=Form(default="youtube"),db:Session=Depends(get_db)):
 e=db.get(Episode,episode_id);t=(e.analysis or {}).get("transcript") if e else None
 if not e or e.project_id!=project_id:raise HTTPException(404,"Episode not found")
 if not t or not t.get("segments"):raise HTTPException(422,"Episode chưa có timestamp transcript")
 return {"job":enqueue({"kind":"review_script","project_id":project_id,"episode_id":episode_id,"title":e.title,"segments":t["segments"],"style":style}),"episode_id":episode_id,"style":style}
@app.get("/api/v1/jobs/{job_id}")
def job_status(job_id:str):
 j=get_job(job_id)
 if not j:raise HTTPException(404,"Job not found")
 return j
@app.get("/api/v1/projects/{project_id}/episodes/{episode_id}/transcript")
def transcript(project_id:str,episode_id:str,db:Session=Depends(get_db)):
 e=db.get(Episode,episode_id)
 if not e or e.project_id!=project_id:raise HTTPException(404,"Episode not found")
 t=(e.analysis or {}).get("transcript")
 if not t:raise HTTPException(404,"Transcript chưa có")
 return {"episode_id":episode_id,"title":e.title,"transcript":t,"review_script":(e.analysis or {}).get("review_script")}
@app.get("/api/v1/projects/{project_id}/episodes/{episode_id}/srt",response_class=PlainTextResponse)
def srt(project_id:str,episode_id:str,db:Session=Depends(get_db)):
 e=db.get(Episode,episode_id);text=((e.analysis or {}).get("transcript") or {}).get("srt") if e and e.project_id==project_id else None
 if not text:raise HTTPException(404,"SRT chưa có")
 return Response(content=text,media_type="application/x-subrip",headers={"Content-Disposition":f'attachment; filename="{Path(e.title).stem}.srt"'})
@app.get("/api/v1/projects/{project_id}/episodes/{episode_id}/review-script")
def get_review_script(project_id:str,episode_id:str,db:Session=Depends(get_db)):
 e=db.get(Episode,episode_id)
 if not e or e.project_id!=project_id:raise HTTPException(404,"Episode not found")
 latest=db.scalar(select(ReviewScript).where(ReviewScript.episode_id==episode_id).order_by(ReviewScript.version.desc()).limit(1))
 if latest:return script_dict(latest)
 script=(e.analysis or {}).get("review_script")
 if not script:raise HTTPException(404,"Review Script chưa có")
 return {**script,"episode_id":episode_id,"status":"legacy"}
@app.get("/api/v1/projects/{project_id}/episodes/{episode_id}/review-script/versions")
def review_script_versions(project_id:str,episode_id:str,db:Session=Depends(get_db)):
 e=db.get(Episode,episode_id)
 if not e or e.project_id!=project_id:raise HTTPException(404,"Episode not found")
 return [script_dict(s) for s in db.scalars(select(ReviewScript).where(ReviewScript.episode_id==episode_id).order_by(ReviewScript.version.desc())).all()]
@app.put("/api/v1/projects/{project_id}/episodes/{episode_id}/review-script/{script_id}")
def update_review_script(project_id:str,episode_id:str,script_id:str,payload:ReviewScriptUpdate,db:Session=Depends(get_db)):
 e=db.get(Episode,episode_id);s=db.get(ReviewScript,script_id)
 if not e or e.project_id!=project_id or not s or s.episode_id!=episode_id:raise HTTPException(404,"Review Script not found")
 s.hook=payload.hook;s.intro=payload.intro;s.segments=payload.segments;s.outro=payload.outro;s.status="draft";db.commit();db.refresh(s);return script_dict(s)
@app.post("/api/v1/projects/{project_id}/episodes/{episode_id}/review-script/{script_id}/approve")
def approve_review_script(project_id:str,episode_id:str,script_id:str,db:Session=Depends(get_db)):
 e=db.get(Episode,episode_id);s=db.get(ReviewScript,script_id)
 if not e or e.project_id!=project_id or not s or s.episode_id!=episode_id:raise HTTPException(404,"Review Script not found")
 for other in db.scalars(select(ReviewScript).where(ReviewScript.episode_id==episode_id,ReviewScript.id!=script_id)).all(): other.status="archived"
 s.status="approved";db.commit();db.refresh(s);return script_dict(s)
@app.get("/api/v1/projects/{project_id}/episodes/{episode_id}/review-script.txt",response_class=PlainTextResponse)
def export_txt(project_id:str,episode_id:str,db:Session=Depends(get_db)):
 e=db.get(Episode,episode_id);s=db.scalar(select(ReviewScript).where(ReviewScript.episode_id==episode_id).order_by(ReviewScript.version.desc()).limit(1)) if e and e.project_id==project_id else None;script=script_dict(s) if s else ((e.analysis or {}).get("review_script") if e else None)
 if not script:raise HTTPException(404,"Review Script chưa có")
 return Response(content=script_text({**script,"title":e.title}),media_type="text/plain; charset=utf-8",headers={"Content-Disposition":f'attachment; filename="{Path(e.title).stem}-review-script.txt"'})
@app.get("/api/v1/projects/{project_id}/episodes/{episode_id}/review-script.html")
def export_html(project_id:str,episode_id:str,db:Session=Depends(get_db)):
 e=db.get(Episode,episode_id);s=db.scalar(select(ReviewScript).where(ReviewScript.episode_id==episode_id).order_by(ReviewScript.version.desc()).limit(1)) if e and e.project_id==project_id else None;script=script_dict(s) if s else ((e.analysis or {}).get("review_script") if e else None)
 if not script:raise HTTPException(404,"Review Script chưa có")
 return Response(content=script_html({**script,"title":e.title}),media_type="text/html; charset=utf-8")
@app.get("/api/v1/projects/{project_id}/characters")
def characters(project_id:str,db:Session=Depends(get_db)):
 if not db.get(Project,project_id):raise HTTPException(404,"Project not found")
 return [{"id":c.id,"name":c.name,"role":c.role,"aliases":c.aliases,"created_at":c.created_at} for c in db.scalars(select(CharacterModel).where(CharacterModel.project_id==project_id).order_by(CharacterModel.name)).all()]
@app.get("/api/v1/projects/{project_id}/events")
def events(project_id:str,db:Session=Depends(get_db)):
 if not db.get(Project,project_id):raise HTTPException(404,"Project not found")
 return [{"id":e.id,"episode_id":e.episode_id,"title":e.title,"evidence":e.evidence,"metadata":e.event_metadata,"created_at":e.created_at} for e in db.scalars(select(EventModel).where(EventModel.project_id==project_id).order_by(EventModel.created_at)).all()]
@app.get("/api/v1/projects/{project_id}/relationships")
def relationships(project_id:str,db:Session=Depends(get_db)):
 if not db.get(Project,project_id):raise HTTPException(404,"Project not found")
 rs=db.scalars(select(Relationship).where(Relationship.project_id==project_id)).all();cs={c.id:c.name for c in db.scalars(select(CharacterModel).where(CharacterModel.project_id==project_id)).all()};return [{"id":r.id,"from":cs.get(r.from_character_id,r.from_character_id),"to":cs.get(r.to_character_id,r.to_character_id),"relation":r.relation,"evidence":r.evidence} for r in rs]
@app.get("/api/v1/projects/{project_id}/timeline")
def timeline(project_id:str,db:Session=Depends(get_db)):return build_timeline(db,project_id)
@app.post("/api/v1/analyze")
def analyze(p:AnalyzeRequest):return enqueue({"kind":"analysis",**p.model_dump()})
@app.post("/api/v1/analyze/upload")
def analyze_upload(file:UploadFile=File(...),title:str=Form(default="Tài liệu tải lên"),mode:str=Form(default="review"),spoiler:bool=Form(default=False)):
 filename=Path(file.filename or "upload").name
 if Path(filename).suffix.lower() not in DOCUMENT_EXTENSIONS:raise HTTPException(415,"Định dạng tài liệu không được hỗ trợ")
 path,filename,_=save_upload(file,MAX_UPLOAD_BYTES);return enqueue({"kind":"upload_analysis","file_path":path,"filename":filename,"title":title,"mode":mode,"spoiler":spoiler})
