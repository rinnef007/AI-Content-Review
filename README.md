# AI Content Review

AI-assisted content analysis, summarization, and review-script generation for user-provided text, documents, images/comics, and video.

## V1 scope

- Text/Markdown input
- PDF and image upload
- OCR for Vietnamese + English images and scanned PDFs
- Local deterministic analysis for offline development
- Optional OpenAI analysis provider
- Summary, review, and script modes
- Structured character/event/relationship/conflict fields from the AI provider
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

## PDF / image OCR

`POST /api/v1/analyze/upload` accepts multipart form data with `file`, optional `title`, `mode` (`summary|review|script`) and `spoiler`.

Supported files: PDF, PNG, JPG/JPEG, WEBP, BMP, TIFF. Text PDFs are extracted directly; scanned/image-only PDFs are rendered page-by-page and OCR'd with Tesseract. V1 limits uploads to 25 MB and 30 PDF pages.

The Docker image installs Tesseract with English and Vietnamese language packs.

## AI provider

Default development mode is local and does not require an API key:

```env
AI_PROVIDER=local
```

To enable the OpenAI provider:

```env
AI_PROVIDER=openai
AI_API_KEY=your_api_key
AI_MODEL=gpt-5.6-luna
```

The backend keeps the same upload contract and sends OCR/text content to the configured provider. The provider returns summary, review, keywords, characters, events, relationships, conflicts, and key details.
