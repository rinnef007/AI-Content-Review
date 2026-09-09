# AI Content Review

AI-assisted content analysis, summarization, and review-script generation for user-provided text, documents, images/comics, and video.

## V1 scope

- Project and episode management
- Text/Markdown input
- Document/image upload endpoint
- OCR/AI/STT provider adapters with safe local fallbacks
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

## Current implementation

The first slice is intentionally provider-agnostic. The API can create analysis jobs and execute deterministic local analysis without an external AI key. Provider adapters can be enabled later through environment variables.
