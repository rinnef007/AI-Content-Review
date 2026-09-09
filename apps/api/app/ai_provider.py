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
Bạn là biên tập viên nội dung tiếng Việt. Phân tích tài liệu người dùng cung cấp và trả về DUY NHẤT JSON hợp lệ.
Không bịa chi tiết không có trong nội dung. Nếu thông tin không rõ, ghi null hoặc [] .

Tiêu đề: {title}
Chế độ đầu ra: {mode}
Spoiler được phép: {spoiler}

Nội dung:
{content}

JSON bắt buộc có các khóa:
summary: string
review: string
keywords: string[]
characters: object[] với name, role, evidence
characters_events: object[] với event, characters, evidence
relationships: object[] với from, to, relation, evidence
conflicts: string[]
key_details: string[]
"""

    response = client.responses.create(
        model=model,
        input=prompt,
    )
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
