from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI


def generate_review_script(*, title: str, segments: list[dict[str, Any]], style: str = "youtube") -> dict[str, Any]:
    if not segments:
        raise ValueError("Transcript chưa có timestamp segment")
    provider = os.getenv("AI_PROVIDER", "local").strip().lower()
    if provider != "openai":
        items = [{"start": s["start"], "end": s["end"], "hook": "", "script": s["text"], "evidence": s["text"]} for s in segments]
        return {"title": title, "style": style, "provider": "local", "segments": items}

    key = os.getenv("AI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("AI_PROVIDER=openai nhưng AI_API_KEY chưa được cấu hình")
    model = os.getenv("AI_MODEL", "gpt-5.6-luna").strip()
    transcript = "\n".join(f"[{s['start']:.3f}-{s['end']:.3f}] {s['text']}" for s in segments)
    prompt = f"""Bạn là biên tập viên video tiếng Việt. Tạo review script dựa CHỈ trên transcript có timestamp dưới đây.
Không được bịa thông tin. Mỗi ý quan trọng phải giữ timestamp và evidence.
Style: {style}. Tiêu đề: {title}.
Trả về DUY NHẤT JSON hợp lệ:
{{"hook":"string","intro":"string","segments":[{{"start":0,"end":0,"hook":"string","script":"string","evidence":"string"}}],"outro":"string"}}
Transcript:
{transcript}
"""
    response = OpenAI(api_key=key).responses.create(model=model, input=prompt)
    raw = response.output_text.strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("AI review script trả về JSON không hợp lệ") from exc
    result["title"] = title
    result["style"] = style
    result["provider"] = "openai"
    result["model"] = model
    return result
