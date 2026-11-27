"""Build designed verse videos: cinematic styles (word reveal + parallax) and chat style."""
import hashlib
import math
import os
import subprocess

import requests

from quran_meta import RECITERS, AUDIO_URL
from quran_render import render_base, render_word_overlays, particle_paths
from quran_chat import audio_bars, render_chat_base, render_player_patch

W, H = 1080, 1920
FPS = 24
MAX_SECONDS = 60

CACHE = os.environ.get("QV_CACHE", "/tmp/quran_video_cache")
os.makedirs(CACHE, exist_ok=True)

_UA = {"User-Agent": "quran-video-bot/2.0"}


class VideoError(Exception):
    def __init__(self, code, detail=None):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if p.returncode != 0:
        raise VideoError("ffmpeg", (p.stderr or "")[-400:])
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
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", path],
                       capture_output=True, text=True)
    try:
        return float(p.stdout.strip())
    except ValueError:
        raise VideoError("audio", "bad mp3")


def _finish(seg, dur, vf_extra=""):
    af = f"afade=t=in:st=0:d=0.2,afade=t=out:st={max(0.0, dur-0.3):.2f}:d=0.3"
    return af


def build_cine_segment(work, tag, reciter_ar, surah, ayah, a1, a2, style, solid, apath, dur):
    base_p = os.path.join(work, f"base_{tag}.png")
    _p, light = render_base(reciter_ar, surah, a1, a2, style, solid, base_p)
    words = render_word_overlays(surah, ayah, a1, dur, light, work, tag)
    far_p, near_p, rays_p = particle_paths(style, solid, work)

    inputs = [base_p, far_p, near_p]
    if rays_p:
        inputs.append(rays_p)
    w0 = len(inputs)
    inputs += [wp for (wp, _x, _y, _t, _f) in words]
    inputs.append(apath)
    ai = len(inputs) - 1

    g = []
    g.append(f"[0:v]scale={W}:{H},zoompan=z='min(1+0.00012*on,1.07)':"
             f"x='iw/2-(iw/zoom)/2':y='ih/2-(ih/zoom)/2':d=1:s={W}x{H}:fps={FPS}[bg]")
    g.append("[bg][1:v]overlay=x=-t*4:y=0[v1]")
    g.append("[v1][2:v]overlay=x=-t*7:y=0[v2]")
    cur = "v2"
    if rays_p:
        g.append(f"[{cur}][3:v]overlay=x='t*1.5-40':y=0[v3]")
        cur = "v3"
    for k, (_p, x, y, t, fade) in enumerate(words):
        g.append(f"[{w0+k}:v]format=rgba,fade=t=in:st={t}:d={fade}:alpha=1[wk{k}]")
        nxt = f"v{k+4}"
        g.append(f"[{cur}][wk{k}]overlay={x}:{y}:enable='gte(t,{t})'[{nxt}]")
        cur = nxt
    g.append(f"[{cur}]fade=t=in:st=0:d=0.4,fade=t=out:st={max(0.0,dur-0.4):.2f}:d=0.4,"
             f"format=yuv420p[vout]")
    script = os.path.join(work, f"filter_{tag}.txt")
    with open(script, "w") as f:
        f.write(";\n".join(g))

    seg = os.path.join(work, f"seg_{tag}.mp4")
    cmd = ["ffmpeg", "-y"]
    for i, p in enumerate(inputs):
        if i == ai:
            cmd += ["-i", p]
        else:
            cmd += ["-loop", "1", "-framerate", str(FPS), "-i", p]
    cmd += ["-filter_complex_script", script, "-map", "[vout]", "-map", f"{ai}:a",
            "-af", _finish(seg, dur),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-t", f"{dur:.3f}", seg]
    _run(cmd)
    return seg


def build_chat_segment(work, tag, surah, ayah, a1, a2, apath, dur):
    bars = audio_bars(apath)
    base_p = os.path.join(work, f"chatbase_{tag}.png")
    _p, geom = render_chat_base(surah, ayah, a1, a2, bars, base_p)

    steps = max(1, math.ceil(dur * 2))
    for k in range(steps):
        t = k / 2
        render_player_patch(bars, min(1.0, t / dur), max(0.0, dur - t), geom,
                            os.path.join(work, f"cp_{tag}_{k:03d}.png"), playing=(k > 0))
    strip = os.path.join(work, f"strip_{tag}.mov")
    _run(["ffmpeg", "-y", "-framerate", "2", "-i", os.path.join(work, f"cp_{tag}_%03d.png"),
          "-frames:v", str(steps), "-c:v", "qtrle", strip])

    seg = os.path.join(work, f"seg_{tag}.mp4")
    script = os.path.join(work, f"filter_{tag}.txt")
    with open(script, "w") as f:
        f.write(f"[0:v][1:v]overlay=0:0:format=auto,"
                f"fade=t=in:st=0:d=0.3,fade=t=out:st={max(0.0,dur-0.3):.2f}:d=0.3,"
                f"format=yuv420p[vout]")
    _run(["ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-i", base_p,
          "-i", strip, "-i", apath,
          "-filter_complex_script", script, "-map", "[vout]", "-map", "2:a",
          "-af", _finish(seg, dur),
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
          "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-t", f"{dur:.3f}", seg])
    return seg


def make_verse_video(reciter, surah, a1, a2, style, solid=None, progress=None):
    """Return (mp4_path, total_seconds). Raises VideoError."""
    if not (0 <= reciter < len(RECITERS)):
        raise VideoError("reciter")
    reciter_ar = RECITERS[reciter][1]

    audios, total = [], 0.0
    for ayah in range(a1, a2 + 1):
        p = _download(reciter, surah, ayah)
        dur = _duration(p)
        total += dur
        audios.append((ayah, p, dur))
    if total > MAX_SECONDS:
        raise VideoError("toolong", round(total))

    key = hashlib.sha1(
        f"v2|{reciter}|{surah}|{a1}|{a2}|{style}|{solid}".encode()).hexdigest()[:16]
    final = os.path.join(CACHE, f"v_{key}.mp4")
    if os.path.exists(final) and os.path.getsize(final) > 10000:
        return final, total

    work = os.path.join(CACHE, f"w_{key}")
    os.makedirs(work, exist_ok=True)
    segs = []
    for i, (ayah, apath, dur) in enumerate(audios):
        if style == "chat":
            seg = build_chat_segment(work, str(i), surah, ayah, a1, a2, apath, dur)
        else:
            seg = build_cine_segment(work, str(i), reciter_ar, surah, ayah, a1, a2,
                                     style, solid, apath, dur)
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
