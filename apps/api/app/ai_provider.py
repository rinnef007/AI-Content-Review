from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI


def analyze_with_openai(*, title: str, content: str, mode: str, spoiler: bool) -> dict[str, Any]:
    api_key = os.getenv("AI_API_KEY", "").strip()
    model = os.getenv("AI_MODEL", "gpt-5.6-luna").strip()
    if not api_key:
        raise RuntimeError("AI_PROVIDER=openai nhưng AI_API_KEY chưa được cấu hình")

    client = OpenAI(api_key=api_key)
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

    response = client.responses.create(model=model, input=prompt)
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
