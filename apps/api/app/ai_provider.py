from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI


def client() -> OpenAI:
    api_key = os.getenv("AI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("AI_PROVIDER=openai nhưng AI_API_KEY chưa được cấu hình")
    return OpenAI(api_key=api_key)


def transcribe_audio(audio_path: str) -> dict[str, Any]:
    model = os.getenv("STT_MODEL", "gpt-4o-transcribe").strip()
    with open(audio_path, "rb") as audio_file:
        response = client().audio.transcriptions.create(
            model=model,
            file=audio_file,
            response_format="verbose_json",
        )
    data = response.model_dump() if hasattr(response, "model_dump") else dict(response)
    segments = data.get("segments") or []
    normalized = []
    for index, segment in enumerate(segments, start=1):
        if hasattr(segment, "model_dump"):
            segment = segment.model_dump()
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        start = float(segment.get("start") or 0)
        end = float(segment.get("end") or start)
        normalized.append({"index": index, "start": start, "end": max(start, end), "text": text})
    return {
        "text": data.get("text", ""),
        "duration": data.get("duration"),
        "language": data.get("language"),
        "segments": normalized,
        "model": model,
        "provider": "openai",
    }


def analyze_with_openai(*, title: str, content: str, mode: str, spoiler: bool) -> dict[str, Any]:
    model = os.getenv("AI_MODEL", "gpt-5.6-luna").strip()
    prompt = f"""
Bạn là biên tập viên nội dung tiếng Việt. Phân tích tài liệu người dùng cung cấp.
Chỉ sử dụng thông tin có bằng chứng trong nội dung; không tự bịa tên, sự kiện hoặc quan hệ.
Nếu không xác định được thông tin, trả về [] hoặc null.
Trả về DUY NHẤT một JSON object hợp lệ, không Markdown.

Tiêu đề: {title}
Chế độ: {mode}
Cho phép spoiler: {spoiler}

Nội dung:
{content}

Schema JSON bắt buộc:
{{
  "summary": "string",
  "review": "string",
  "keywords": ["string"],
  "characters": [{{"name":"string","role":"string|null","evidence":"string|null"}}],
  "events": [{{"event":"string","characters":["string"],"evidence":"string|null"}}],
  "relationships": [{{"from":"string","to":"string","relation":"string","evidence":"string|null"}}],
  "conflicts": ["string"],
  "key_details": ["string"]
}}
"""
    response = client().responses.create(model=model, input=prompt)
    raw = response.output_text.strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("AI provider trả về dữ liệu không phải JSON hợp lệ") from exc
    if not isinstance(result, dict):
        raise RuntimeError("AI provider trả về cấu trúc JSON không hợp lệ")
    result["provider"] = "openai"
    result["model"] = model
    result["spoiler"] = spoiler
    return result
