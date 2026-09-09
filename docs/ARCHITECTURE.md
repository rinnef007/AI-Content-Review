# Architecture

```text
Browser
  ↓
Next.js Web
  ↓ REST
FastAPI API ─── PostgreSQL
      │
      └── Redis queue → OCR / transcription / video / AI workers

Object files → MinIO (planned)
```

## Processing pipeline

1. Ingest authorized text, document, image, or video.
2. Normalize content into a common representation.
3. OCR images/scanned documents or transcribe audio/video when required.
4. Build structured facts: characters, entities, events, timeline, relationships, and evidence snippets.
5. Generate summary/review/script from the structured representation.
6. Persist the job, result, provider metadata, and processing status.

The V1 local provider is deterministic and exists for development. External AI/OCR/STT providers should be adapters selected by configuration.
