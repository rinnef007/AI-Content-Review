from __future__ import annotations

from html import escape
from typing import Any


def script_text(script: dict[str, Any]) -> str:
    lines = [script.get("title", "Review Script"), "", f"HOOK: {script.get('hook', '')}", "", f"INTRO: {script.get('intro', '')}", ""]
    for i, segment in enumerate(script.get("segments", []), 1):
        lines += [f"{i}. {segment.get('start', 0):.3f}s → {segment.get('end', 0):.3f}s", segment.get("script", ""), f"Evidence: {segment.get('evidence', '')}", ""]
    lines += [f"OUTRO: {script.get('outro', '')}"]
    return "\n".join(lines)


def script_html(script: dict[str, Any]) -> str:
    parts = [f"<h1>{escape(str(script.get('title', 'Review Script')))}</h1>", f"<h2>Hook</h2><p>{escape(str(script.get('hook', '')))}</p>", f"<h2>Intro</h2><p>{escape(str(script.get('intro', '')))}</p>"]
    for i, segment in enumerate(script.get("segments", []), 1):
        parts.append(f"<h3>{i}. {float(segment.get('start', 0)):.3f}s → {float(segment.get('end', 0)):.3f}s</h3><p>{escape(str(segment.get('script', '')))}</p><p><b>Evidence:</b> {escape(str(segment.get('evidence', '')))}</p>")
    parts.append(f"<h2>Outro</h2><p>{escape(str(script.get('outro', '')))}</p>")
    return "<html><body>" + "".join(parts) + "</body></html>"
