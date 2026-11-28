"""Shared ffmpeg helpers: safe execution, probing, path validation."""
import json
import logging
import os
import subprocess

log = logging.getLogger("udv3.media")


class MediaError(Exception):
    def __init__(self, key, detail=None):
        super().__init__(key if detail is None else f"{key}: {detail}")
        self.key = key
        self.detail = detail


def run(cmd, timeout=600):
    """Run an ffmpeg/ffprobe command list (never a shell string)."""
    log.debug("run: %s", " ".join(cmd[:3]) + " ...")
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise MediaError("timeout")
    if p.returncode != 0:
        raise MediaError("ffmpeg", (p.stderr or "")[-400:])
    return p


def probe_media(path):
    p = run(["ffprobe", "-v", "error", "-show_entries",
             "format=duration,size,bit_rate:stream=codec_type,codec_name,width,height",
             "-of", "json", path])
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        raise MediaError("ffmpeg", "bad probe output")


def duration(path):
    info = probe_media(path)
    try:
        return float(info["format"]["duration"])
    except (KeyError, ValueError):
        raise MediaError("ffmpeg", "no duration")


def has_video(path):
    return any(s.get("codec_type") == "video" for s in probe_media(path).get("streams", []))


def has_audio(path):
    return any(s.get("codec_type") == "audio" for s in probe_media(path).get("streams", []))


def safe_out(workdir, name):
    os.makedirs(workdir, exist_ok=True)
    out = os.path.join(workdir, name)
    if os.path.exists(out):
        os.remove(out)
    return out


def parse_time(s):
    """'90', '1:30', '00:01:30.5' -> seconds (float). Raises MediaError."""
    s = (s or "").strip()
    try:
        parts = s.split(":")
        if len(parts) == 1:
            return float(parts[0])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except ValueError:
        pass
    raise MediaError("badtime")
