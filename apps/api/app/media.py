from __future__ import annotations

import json
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
