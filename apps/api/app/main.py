from __future__ import annotations

import io
import os
import re
from collections import Counter
from datetime import datetime, timezone
from uuid import uuid4

import fitz
import pytesseract
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageOps
from pydantic import BaseModel, Field
from pypdf import PdfReader

from app.ai_provider import analyze_with_openai

app = FastAPI(title="AI Content Review API", version="0.4.1")
CORS_ORIGINS = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if item.strip()]
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
jobs: dict[str, dict] = {}
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_PDF_PAGES = 30
AI_PROVIDER = os.getenv("AI_PROVIDER", "local").strip().lower()

class AnalyzeRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1)
    mode: str = Field(default="review", pattern="^(summary|review|script)$")
    spoiler: bool = False

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
    return {"summary": summary, "review": review, "keywords": keywords, "stats": {"words": len(words), "sentences": len(sentences)}, "provider": "local", "spoiler": payload.spoiler}

def analyze_content(payload: AnalyzeRequest) -> dict:
    if AI_PROVIDER == "openai":
        try:
            return analyze_with_openai(title=payload.title, content=payload.content, mode=payload.mode, spoiler=payload.spoiler)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"AI provider lỗi: {exc}") from exc
    return local_analyze(payload)

def ocr_image(image: Image.Image) -> str:
    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail((3000, 3000))
    return pytesseract.image_to_string(image, lang="vie+eng", config="--psm 6").strip()

def extract_pdf(data: bytes) -> tuple[str, int, bool]:
    reader = PdfReader(io.BytesIO(data))
    pages = len(reader.pages)
    if pages > MAX_PDF_PAGES: raise HTTPException(status_code=413, detail=f"PDF vượt quá giới hạn {MAX_PDF_PAGES} trang ở V1")
    text_parts = [(page.extract_text() or "").strip() for page in reader.pages]
    text = "\n\n".join(p for p in text_parts if p)
    if text: return text, pages, False
    document = fitz.open(stream=data, filetype="pdf")
    ocr_parts: list[str] = []
    for index, page in enumerate(document):
        pixmap = page.get_pixmap(matrix=fitz.Matrix(1.7, 1.7), alpha=False)
        image = Image.open(io.BytesIO(pixmap.tobytes("png")))
        page_text = ocr_image(image)
        if page_text: ocr_parts.append(f"[Trang {index + 1}]\n{page_text}")
    return "\n\n".join(ocr_parts), pages, True

def extract_upload(data: bytes, filename: str) -> tuple[str, dict]:
    lower = filename.lower()
    suffix = "." + lower.rsplit(".", 1)[-1] if "." in lower else ""
    if suffix not in ALLOWED_EXTENSIONS: raise HTTPException(status_code=415, detail="Chỉ hỗ trợ PDF, PNG, JPG, JPEG, WEBP, BMP, TIFF")
    if len(data) > MAX_UPLOAD_BYTES: raise HTTPException(status_code=413, detail="File vượt quá giới hạn 25 MB")
    if suffix == ".pdf":
        text, pages, ocr_used = extract_pdf(data)
        if not text: raise HTTPException(status_code=422, detail="OCR không nhận diện được văn bản trong PDF")
        return text, {"type": "pdf", "pages": pages, "ocr_used": ocr_used}
    try: text = ocr_image(Image.open(io.BytesIO(data)))
    except Exception as exc: raise HTTPException(status_code=422, detail=f"Không thể đọc ảnh: {exc}") from exc
    if not text: raise HTTPException(status_code=422, detail="OCR không nhận diện được văn bản trong ảnh")
    return text, {"type": "image", "pages": 1, "ocr_used": True}

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "api", "version": "0.4.1", "ocr": "tesseract", "ai_provider": AI_PROVIDER}

@app.post("/api/v1/analyze")
def analyze(payload: AnalyzeRequest) -> dict:
    job_id = str(uuid4()); result = analyze_content(payload)
    jobs[job_id] = {"id": job_id, "status": "completed", "created_at": datetime.now(timezone.utc).isoformat(), "input": payload.model_dump(), "result": result}
    return jobs[job_id]

@app.post("/api/v1/analyze/upload")
def analyze_upload(file: UploadFile = File(...), title: str = Form(default="Tài liệu tải lên"), mode: str = Form(default="review"), spoiler: bool = Form(default=False)) -> dict:
    if mode not in {"summary", "review", "script"}: raise HTTPException(status_code=422, detail="mode phải là summary, review hoặc script")
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    content, source = extract_upload(data, file.filename or "upload")
    payload = AnalyzeRequest(title=title, content=content, mode=mode, spoiler=spoiler)
    result = analyze_content(payload); result["source"] = source; result["extracted_text"] = content
    job_id = str(uuid4())
    jobs[job_id] = {"id": job_id, "status": "completed", "created_at": datetime.now(timezone.utc).isoformat(), "input": {"title": title, "mode": mode, "spoiler": spoiler, "filename": file.filename}, "result": result}
    return jobs[job_id]

@app.get("/api/v1/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = jobs.get(job_id)
    if not job: raise HTTPException(status_code=404, detail="Job not found")
    return job
