# AI Content Review

AI-assisted content analysis, summarization, and review-script generation for user-provided text, documents, images/comics, and video.

## V1 scope

- Project and episode management
- Text/Markdown input
- PDF and image upload
- OCR for Vietnamese + English images and scanned PDFs
- Structured content analysis
- Summary and review-script generation
- Job/status model ready for asynchronous workers
- PostgreSQL-ready persistence
- Docker Compose development environment
- Vietnamese-first API/UI foundation

> Only process content you own or are authorized to process. URL ingestion, when added, will be limited to publicly accessible/authorized content and will not bypass DRM, paywalls, authentication, or access controls.

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

API: http://localhost:8000 · Docs: http://localhost:8000/docs · Web: http://localhost:3000

## Upload API

`POST /api/v1/analyze/upload` accepts multipart form data with `file`, optional `title`, `mode` (`summary|review|script`) and `spoiler`.

Supported files: PDF, PNG, JPG/JPEG, WEBP, BMP, TIFF. Text PDFs are extracted directly; scanned/image-only PDFs are rendered page-by-page and OCR'd with Tesseract. V1 limits uploads to 25 MB and 30 PDF pages.

The current analysis provider is local/deterministic for end-to-end testing. A real AI provider can replace `local_analyze()` without changing the upload contract.
