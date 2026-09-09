from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}


def probe_media(path: str) -> dict:
    command = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,size:stream=index,codec_type,codec_name,channels,sample_rate,width,height",
        "-of", "json", path,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    return json.loads(result.stdout or "{}")


def extract_audio(input_path: str, output_path: str) -> None:
    command = [
        "ffmpeg", "-y", "-i", input_path,
        "-map", "0:a:0?", "-vn", "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le", output_path,
    ]
    subprocess.run(command, capture_output=True, text=True, check=True)


def media_kind(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
    raise ValueError("Định dạng media chưa được hỗ trợ")


def _timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def normalize_segments(transcript: dict) -> list[dict]:
    segments = transcript.get("segments") or []
    normalized: list[dict] = []
    for index, segment in enumerate(segments):
        if hasattr(segment, "model_dump"):
            segment = segment.model_dump()
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        start = float(segment.get("start") or 0)
        end = float(segment.get("end") or start)
        if end < start:
            end = start
        normalized.append({"index": len(normalized) + 1, "start": start, "end": end, "text": text})
    if normalized:
        return normalized

    text = str(transcript.get("text") or "").strip()
    if not text:
        return []
    # Fallback when the provider returns text without segments.
    chunks = [chunk.strip() for chunk in re.split(r"(?<=[.!?])\s+", text) if chunk.strip()]
    duration = float(transcript.get("duration") or 0)
    step = duration / len(chunks) if duration and chunks else 0
    return [{"index": i + 1, "start": i * step, "end": (i + 1) * step, "text": chunk} for i, chunk in enumerate(chunks)]


def transcript_to_srt(segments: list[dict]) -> str:
    blocks = []
    for index, segment in enumerate(segments, start=1):
        blocks.append(f"{index}\n{_timestamp(segment['start'])} --> {_timestamp(segment['end'])}\n{segment['text']}\n")
    return "\n".join(blocks)
