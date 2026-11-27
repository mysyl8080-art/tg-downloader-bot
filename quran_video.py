"""Build a designed verse video: per-ayah image segments + recitation audio."""
import hashlib
import os
import subprocess

import requests

from quran_meta import RECITERS, AUDIO_URL
from quran_render import render_ayah_image

W, H = 1080, 1920
FPS = 24
MAX_SECONDS = 60

CACHE = os.environ.get("QV_CACHE", "/tmp/quran_video_cache")
os.makedirs(CACHE, exist_ok=True)

_UA = {"User-Agent": "quran-video-bot/1.0"}


class VideoError(Exception):
    def __init__(self, code, detail=None):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if p.returncode != 0:
        raise VideoError("ffmpeg", p.stderr[-400:])
    return p


def _download(reciter, surah, ayah):
    folder = RECITERS[reciter][0]
    path = os.path.join(CACHE, f"a_{folder}_{surah}_{ayah}.mp3")
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return path
    url = AUDIO_URL.format(folder=folder, sss=surah, aaa=ayah)
    r = requests.get(url, headers=_UA, timeout=60)
    if r.status_code != 200 or len(r.content) < 1000:
        raise VideoError("audio", f"{r.status_code} {surah}:{ayah}")
    with open(path, "wb") as f:
        f.write(r.content)
    return path


def _duration(path):
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True)
    try:
        return float(p.stdout.strip())
    except ValueError:
        raise VideoError("audio", "bad mp3")


def make_verse_video(reciter, surah, a1, a2, style, solid=None, progress=None):
    """Return (mp4_path, total_seconds). Raises VideoError."""
    if not (0 <= reciter < len(RECITERS)):
        raise VideoError("reciter")
    reciter_ar = RECITERS[reciter][1]

    audios = []
    total = 0.0
    for ayah in range(a1, a2 + 1):
        p = _download(reciter, surah, ayah)
        dur = _duration(p)
        total += dur
        audios.append((ayah, p, dur))
    if total > MAX_SECONDS:
        raise VideoError("toolong", round(total))

    key = hashlib.sha1(
        f"{reciter}|{surah}|{a1}|{a2}|{style}|{solid}".encode()).hexdigest()[:16]
    final = os.path.join(CACHE, f"v_{key}.mp4")
    if os.path.exists(final) and os.path.getsize(final) > 10000:
        return final, total

    work = os.path.join(CACHE, f"w_{key}")
    os.makedirs(work, exist_ok=True)
    segs = []
    for i, (ayah, apath, dur) in enumerate(audios):
        png = os.path.join(work, f"img_{i}.png")
        render_ayah_image(reciter_ar, surah, ayah, a1, a2, style, solid, out_path=png)
        seg = os.path.join(work, f"seg_{i}.mp4")
        fade_out_st = max(0.0, dur - 0.45)
        vf = (
            f"scale={W}:{H},"
            f"zoompan=z='min(1+0.00009*on,1.07)':x='iw/2-(iw/zoom)/2':y='ih/2-(ih/zoom)/2'"
            f":d=1:s={W}x{H}:fps={FPS},"
            f"fade=t=in:st=0:d=0.45,fade=t=out:st={fade_out_st:.2f}:d=0.45,format=yuv420p"
        )
        af = f"afade=t=in:st=0:d=0.2,afade=t=out:st={max(0.0, dur-0.25):.2f}:d=0.25"
        _run(["ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-i", png,
              "-i", apath, "-vf", vf, "-af", af,
              "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
              "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
              "-t", f"{dur:.3f}", seg])
        segs.append(seg)
        if progress:
            progress(i + 1, len(audios))

    if len(segs) == 1:
        os.replace(segs[0], final)
    else:
        lst = os.path.join(work, "list.txt")
        with open(lst, "w") as f:
            for s in segs:
                f.write(f"file '{s}'\n")
        _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
              "-c", "copy", "-movflags", "+faststart", final])
    return final, total


if __name__ == "__main__":
    import sys
    reciter, surah, a1, a2, style = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
    solid = sys.argv[6] if len(sys.argv) > 6 else None
    path, dur = make_verse_video(reciter, surah, a1, a2, style, solid,
                                 progress=lambda i, n: print(f"seg {i}/{n}", flush=True))
    print(path, round(dur, 1), "s", os.path.getsize(path) // 1024, "KB")
