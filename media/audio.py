"""Audio tools: extract, convert, trim, volume, compress, voice message."""
import os

from .ffmpeg_base import run, safe_out, parse_time, MediaError

CODECS = {
    "mp3": ["-c:a", "libmp3lame", "-q:a", "4"],
    "m4a": ["-c:a", "aac", "-b:a", "160k"],
    "wav": ["-c:a", "pcm_s16le"],
    "flac": ["-c:a", "flac"],
    "ogg": ["-c:a", "libopus", "-b:a", "96k"],   # Telegram voice
}


def extract_audio(src, workdir, fmt="mp3"):
    out = safe_out(workdir, f"audio.{fmt}")
    run(["ffmpeg", "-y", "-i", src, "-vn"] + CODECS[fmt] + [out])
    return out


def trim(src, workdir, start, end=None):
    st = parse_time(start)
    out = safe_out(workdir, "trimmed" + os.path.splitext(src)[1])
    cmd = ["ffmpeg", "-y", "-ss", f"{st:.3f}", "-i", src]
    if end is not None:
        dur = parse_time(end) - st
        if dur <= 0:
            raise MediaError("badtime")
        cmd += ["-t", f"{dur:.3f}"]
    run(cmd + ["-c", "copy", out])
    return out


def volume(src, workdir, factor):
    factor = max(0.0, min(float(factor), 5.0))
    out = safe_out(workdir, "vol" + os.path.splitext(src)[1])
    run(["ffmpeg", "-y", "-i", src, "-af", f"volume={factor}", "-c:v", "copy", out])
    return out


def compress_audio(src, workdir, bitrate="96k"):
    if not bitrate.endswith("k"):
        bitrate += "k"
    out = safe_out(workdir, f"small_{bitrate}.mp3")
    run(["ffmpeg", "-y", "-i", src, "-c:a", "libmp3lame", "-b:a", bitrate, out])
    return out


def to_voice(src, workdir):
    """Telegram voice message (opus/ogg)."""
    out = safe_out(workdir, "voice.ogg")
    run(["ffmpeg", "-y", "-i", src] + CODECS["ogg"] + [out])
    return out
