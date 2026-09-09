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

## Repository layout

```text
apps/
  api/                  FastAPI backend
  web/                  Next.js frontend
workers/
  ai/                   AI processing worker foundation
  ocr/                  OCR worker foundation
  transcription/        Speech-to-text worker foundation
  video/                Video processing worker foundation
packages/
  shared/               Shared contracts
infrastructure/
  postgres/             Database assets
  redis/                Queue assets
  minio/                Object storage assets
docs/                   Architecture and implementation docs
compose.yaml
.env.example
```

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

API: http://localhost:8000
API docs: http://localhost:8000/docs
Web: http://localhost:3000

## Upload API

`POST /api/v1/analyze/upload` accepts `multipart/form-data`:

- `file`: PDF, PNG, JPG/JPEG, WEBP, BMP, TIFF
- `title`: optional title
- `mode`: `summary`, `review`, or `script`
- `spoiler`: boolean

PDFs with a text layer are extracted directly. Scanned/image-only PDFs are rendered page-by-page and OCR'd with Tesseract. V1 limits uploads to 25 MB and 30 PDF pages.

## Current AI behavior

The current analysis provider is intentionally local/deterministic so the complete upload → OCR → analysis flow can be tested without an external API key. The next AI provider layer can replace `local_analyze()` without changing the upload contract.
