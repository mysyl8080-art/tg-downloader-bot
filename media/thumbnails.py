"""Thumbnails and screenshots."""
from .ffmpeg_base import run, safe_out, parse_time


def thumbnail(src, workdir):
    out = safe_out(workdir, "thumb.jpg")
    run(["ffmpeg", "-y", "-i", src, "-frames:v", "1", "-q:v", "3", out])
    return out


def screenshot(src, workdir, at=0.0):
    out = safe_out(workdir, "shot.jpg")
    run(["ffmpeg", "-y", "-ss", f"{parse_time(str(at)):.3f}", "-i", src,
         "-frames:v", "1", "-q:v", "3", out])
    return out
