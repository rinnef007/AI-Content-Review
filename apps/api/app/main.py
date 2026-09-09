from __future__ import annotations

import io
import os
import re
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import fitz
import pytesseract
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageOps
from pydantic import BaseModel, Field
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_provider import analyze_with_openai
from app.database import get_db, init_db
from app.job_queue import enqueue, get_job
from app.knowledge import build_timeline
from app.models import Character as CharacterModel
from app.models import Episode, Event as EventModel, Project, Relationship

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/data/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    yield

app = FastAPI(title="AI Content Review API", version="0.9.1", lifespan=lifespan)
CORS_ORIGINS = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if item.strip()]
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_PDF_PAGES = 30
AI_PROVIDER = os.getenv("AI_PROVIDER", "local").strip().lower()

class Character(BaseModel):
    name: str
    role: str | None = None
    evidence: str | None = None

class Event(BaseModel):
    event: str
    characters: list[str] = Field(default_factory=list)
    evidence: str | None = None

class Relationship(BaseModel):
    from_: str = Field(alias="from")
    to: str
    relation: str
    evidence: str | None = None
    model_config = {"populate_by_name": True}

class StructuredAnalysis(BaseModel):
    summary: str
    review: str
    keywords: list[str] = Field(default_factory=list)
    characters: list[Character] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    key_details: list[str] = Field(default_factory=list)

class AnalyzeRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1)
    mode: str = Field(default="review", pattern="^(summary|review|script)$")
    spoiler: bool = False

class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    description: str | None = None

class EpisodeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str | None = None
    source_type: str = "text"

def local_analyze(payload: AnalyzeRequest) -> dict:
    words = payload.content.split()
    sentences = [s.strip() for s in re.split(r"[.!?]+", payload.content) if s.strip()]
    freq = Counter(w.strip(".,!?;:()[]{}\"'").lower() for w in words)
    keywords = [w for w, _ in freq.most_common(8) if len(w) > 3]
    excerpt = " ".join(sentences[:3]) or payload.content[:500]
    summary = f"{payload.title}: {excerpt}"
    review = f"Đánh giá nhanh về {payload.title}: nội dung có khoảng {len(words)} từ và {len(sentences)} câu. Các từ khóa nổi bật: {', '.join(keywords) or 'chưa xác định'}."
    if payload.mode == "summary": review = summary
    elif payload.mode == "script": review = f"Mở đầu: {summary}\n\nĐiểm chính: {', '.join(keywords) or 'chưa xác định'}.\n\nKết: Đây là phần cần tiếp tục phân tích khi bật AI provider."
    structured = StructuredAnalysis(summary=summary, review=review, keywords=keywords)
    return {**structured.model_dump(by_alias=True), "provider": "local", "spoiler": payload.spoiler, "stats": {"words": len(words), "sentences": len(sentences)}}

def analyze_content(payload: AnalyzeRequest) -> dict:
    if AI_PROVIDER == "openai":
        try:
            raw = analyze_with_openai(title=payload.title, content=payload.content, mode=payload.mode, spoiler=payload.spoiler)
            structured = StructuredAnalysis.model_validate(raw)
            extras = {k: v for k, v in raw.items() if k not in StructuredAnalysis.model_fields}
            extras["stats"] = {"words": len(payload.content.split()), "sentences": len([s for s in re.split(r"[.!?]+", payload.content) if s.strip()])}
            return {**structured.model_dump(by_alias=True), **extras}
        except Exception as exc:
            raise RuntimeError(f"AI provider lỗi: {exc}") from exc
    return local_analyze(payload)

def ocr_image(image: Image.Image) -> str:
    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail((3000, 3000))
    return pytesseract.image_to_string(image, lang="vie+eng", config="--psm 6").strip()

def extract_pdf(data: bytes) -> tuple[str, int, bool]:
    reader = PdfReader(io.BytesIO(data))
    pages = len(reader.pages)
    if pages > MAX_PDF_PAGES: raise ValueError(f"PDF vượt quá giới hạn {MAX_PDF_PAGES} trang ở V1")
    text_parts = [(page.extract_text() or "").strip() for page in reader.pages]
    text = "\n\n".join(p for p in text_parts if p)
    if text: return text, pages, False
    document = fitz.open(stream=data, filetype="pdf")
    try:
        ocr_parts: list[str] = []
        for index, page in enumerate(document):
            pixmap = page.get_pixmap(matrix=fitz.Matrix(1.7, 1.7), alpha=False)
            page_text = ocr_image(Image.open(io.BytesIO(pixmap.tobytes("png"))))
            if page_text: ocr_parts.append(f"[Trang {index + 1}]\n{page_text}")
        return "\n\n".join(ocr_parts), pages, True
    finally:
        document.close()

def extract_upload(data: bytes, filename: str) -> tuple[str, dict]:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS: raise ValueError("Chỉ hỗ trợ PDF, PNG, JPEG, WEBP, BMP, TIFF")
    if len(data) > MAX_UPLOAD_BYTES: raise ValueError("File vượt quá giới hạn 25 MB")
    if suffix == ".pdf":
        text, pages, ocr_used = extract_pdf(data)
        if not text: raise ValueError("OCR không nhận diện được văn bản trong PDF")
        return text, {"type": "pdf", "pages": pages, "ocr_used": ocr_used}
    try: text = ocr_image(Image.open(io.BytesIO(data)))
    except Exception as exc: raise ValueError(f"Không thể đọc ảnh: {exc}") from exc
    if not text: raise ValueError("OCR không nhận diện được văn bản trong ảnh")
    return text, {"type": "image", "pages": 1, "ocr_used": True}

def project_dict(project: Project) -> dict:
    return {"id": project.id, "name": project.name, "description": project.description, "created_at": project.created_at}

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "api", "version": "0.9.1", "ocr": "tesseract", "ai_provider": AI_PROVIDER, "queue": "redis"}

@app.get("/api/v1/projects")
def list_projects(db: Session = Depends(get_db)) -> list[dict]:
    return [project_dict(project) for project in db.scalars(select(Project).order_by(Project.created_at.desc())).all()]

@app.post("/api/v1/projects")
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> dict:
    project = Project(name=payload.name, description=payload.description)
    db.add(project); db.commit(); db.refresh(project)
    return project_dict(project)

@app.get("/api/v1/projects/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)) -> dict:
    project = db.get(Project, project_id)
    if not project: raise HTTPException(status_code=404, detail="Project not found")
    return {**project_dict(project), "episodes": [{"id": e.id, "title": e.title, "source_type": e.source_type, "source_filename": e.source_filename, "created_at": e.created_at} for e in project.episodes], "characters": [{"id": c.id, "name": c.name, "role": c.role, "aliases": c.aliases} for c in project.characters], "events": [{"id": e.id, "title": e.title, "episode_id": e.episode_id, "evidence": e.evidence} for e in project.events]}

@app.post("/api/v1/projects/{project_id}/episodes")
def create_episode(project_id: str, payload: EpisodeCreate, db: Session = Depends(get_db)) -> dict:
    if not db.get(Project, project_id): raise HTTPException(status_code=404, detail="Project not found")
    episode = Episode(project_id=project_id, title=payload.title, content=payload.content, source_type=payload.source_type)
    db.add(episode); db.commit(); db.refresh(episode)
    return {"id": episode.id, "project_id": episode.project_id, "title": episode.title, "source_type": episode.source_type, "created_at": episode.created_at}

@app.post("/api/v1/projects/{project_id}/episodes/upload")
def upload_episode(project_id: str, file: UploadFile = File(...), title: str | None = Form(default=None), db: Session = Depends(get_db)) -> dict:
    if not db.get(Project, project_id): raise HTTPException(status_code=404, detail="Project not found")
    filename = Path(file.filename or "upload").name
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS: raise HTTPException(status_code=415, detail="Chỉ hỗ trợ PDF, JPEG, PNG, WEBP, BMP, TIFF")
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES: raise HTTPException(status_code=413, detail="File vượt quá giới hạn 25 MB")
    target = UPLOAD_DIR / f"{uuid4().hex}{suffix}"
    target.write_bytes(data)
    episode = Episode(project_id=project_id, title=title or Path(filename).stem, source_type="file", source_filename=filename)
    db.add(episode); db.commit(); db.refresh(episode)
    job = enqueue({"kind": "upload_episode_analysis", "project_id": project_id, "episode_id": episode.id, "file_path": str(target), "filename": filename, "title": episode.title, "mode": "review", "spoiler": False})
    return {"episode": {"id": episode.id, "project_id": project_id, "title": episode.title, "source_type": episode.source_type, "source_filename": filename}, "job": job}

@app.post("/api/v1/projects/{project_id}/episodes/{episode_id}/analyze")
def analyze_episode(project_id: str, episode_id: str, db: Session = Depends(get_db)) -> dict:
    episode = db.get(Episode, episode_id)
    if not episode or episode.project_id != project_id: raise HTTPException(status_code=404, detail="Episode not found")
    if not episode.content: raise HTTPException(status_code=422, detail="Episode chưa có nội dung")
    job = enqueue({"kind": "episode_analysis", "project_id": project_id, "episode_id": episode_id, "title": episode.title, "content": episode.content, "mode": "review", "spoiler": False})
    return {"job": job, "episode_id": episode_id}

@app.post("/api/v1/jobs")
def create_analysis_job(payload: AnalyzeRequest) -> dict:
    return enqueue({"kind": "analysis", **payload.model_dump()})

@app.get("/api/v1/jobs/{job_id}")
def get_analysis_job(job_id: str) -> dict:
    job = get_job(job_id)
    if not job: raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.get("/api/v1/projects/{project_id}/characters")
def list_characters(project_id: str, db: Session = Depends(get_db)) -> list[dict]:
    if not db.get(Project, project_id): raise HTTPException(status_code=404, detail="Project not found")
    characters = db.scalars(select(CharacterModel).where(CharacterModel.project_id == project_id).order_by(CharacterModel.name.asc())).all()
    return [{"id": c.id, "name": c.name, "role": c.role, "aliases": c.aliases, "created_at": c.created_at} for c in characters]

@app.get("/api/v1/projects/{project_id}/events")
def list_events(project_id: str, db: Session = Depends(get_db)) -> list[dict]:
    if not db.get(Project, project_id): raise HTTPException(status_code=404, detail="Project not found")
    events = db.scalars(select(EventModel).where(EventModel.project_id == project_id).order_by(EventModel.created_at.asc())).all()
    return [{"id": e.id, "episode_id": e.episode_id, "title": e.title, "evidence": e.evidence, "metadata": e.event_metadata, "created_at": e.created_at} for e in events]

@app.get("/api/v1/projects/{project_id}/relationships")
def list_relationships(project_id: str, db: Session = Depends(get_db)) -> list[dict]:
    if not db.get(Project, project_id): raise HTTPException(status_code=404, detail="Project not found")
    relationships = db.scalars(select(Relationship).where(Relationship.project_id == project_id)).all()
    characters = {c.id: c.name for c in db.scalars(select(CharacterModel).where(CharacterModel.project_id == project_id)).all()}
    return [{"id": r.id, "from": characters.get(r.from_character_id, r.from_character_id), "to": characters.get(r.to_character_id, r.to_character_id), "relation": r.relation, "evidence": r.evidence} for r in relationships]

@app.get("/api/v1/projects/{project_id}/timeline")
def project_timeline(project_id: str, db: Session = Depends(get_db)) -> list[dict]:
    if not db.get(Project, project_id): raise HTTPException(status_code=404, detail="Project not found")
    return build_timeline(db, project_id)

@app.post("/api/v1/analyze")
def analyze(payload: AnalyzeRequest) -> dict:
    return enqueue({"kind": "analysis", **payload.model_dump()})

@app.post("/api/v1/analyze/upload")
def analyze_upload(file: UploadFile = File(...), title: str = Form(default="Tài liệu tải lên"), mode: str = Form(default="review"), spoiler: bool = Form(default=False)) -> dict:
    if mode not in {"summary", "review", "script"}: raise HTTPException(status_code=422, detail="mode phải là summary, review hoặc script")
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES: raise HTTPException(status_code=413, detail="File vượt quá giới hạn 25 MB")
    filename = Path(file.filename or "upload").name
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS: raise HTTPException(status_code=415, detail="Chỉ hỗ trợ PDF, JPEG, PNG, WEBP, BMP, TIFF")
    target = UPLOAD_DIR / f"{uuid4().hex}{suffix}"
    target.write_bytes(data)
    return enqueue({"kind": "upload_analysis", "file_path": str(target), "filename": filename, "title": title, "mode": mode, "spoiler": spoiler})
