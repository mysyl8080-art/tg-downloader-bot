"""Build designed verse videos: cinematic styles (word reveal + parallax) and chat style."""
import hashlib
import math
import os
import subprocess
import shutil
import logging
import resource
import gc

log = logging.getLogger("quran_video")

import requests

from quran_meta import RECITERS, AUDIO_URL
from PIL import Image

from quran_bg import make_layers
from quran_render import render_base, render_word_overlays
from quran_chat import audio_bars, render_chat_base, render_player_patch

W, H = 1080, 1920
FPS = 24
STRIP_FPS = 8
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
    log.info("ffmpeg done peak_child_rss=%.0fMB self_rss=%s",
             resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024, _self_rss())
    return p


def _self_rss():
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS"):
                    return str(round(int(line.split()[1]) / 1024)) + "MB"
    except Exception:
        pass
    return "?"


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
    word_imgs = [(Image.open(p).copy(), x, y, t, f) for (p, x, y, t, f) in words]

    _b, far, near, rays, _l = make_layers(style, solid)
    far = far.crop((0, 0, W + int(MAX_SECONDS * 4) + 8, H))
    near = near.crop((0, 0, W + int(MAX_SECONDS * 7) + 8, H))
    if rays is not None:
        rays = rays.crop((0, 0, W + 60, H))

    n_frames = max(1, int(round(dur * STRIP_FPS)))

    def strip_frames():
        for k in range(n_frames):
            t = k / STRIP_FPS
            frame = Image.new("RGBA", (W, H))
            frame.paste(far, (-int(t * 4), 0), far)
            frame.paste(near, (-int(t * 7), 0), near)
            if rays is not None:
                frame.paste(rays, (int(t * 1.5) - 40, 0), rays)
            for img, x, y, tk, fade in word_imgs:
                a = (t - tk) / fade
                if a >= 1:
                    frame.paste(img, (x, y), img)
                elif a > 0:
                    tmp = img.copy()
                    tmp.putalpha(img.getchannel("A").point(lambda v: int(v * a)))
                    frame.paste(tmp, (x, y), tmp)
            yield frame.tobytes()

    # pass 1: animated overlay strip to a small qtrle movie (light ffmpeg)
    strip = os.path.join(work, f"strip_{tag}.mov")
    errp = os.path.join(work, f"err_{tag}.log")
    cmd1 = ["ffmpeg", "-y", "-threads", "2", "-thread_queue_size", "4",
            "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}",
            "-framerate", str(STRIP_FPS), "-i", "pipe:0",
            "-frames:v", str(n_frames), "-c:v", "qtrle", strip]
    with open(errp, "wb") as errf:
        p = subprocess.Popen(cmd1, stdin=subprocess.PIPE, stderr=errf)
        try:
            for fr in strip_frames():
                p.stdin.write(fr)
            p.stdin.close()
        except BrokenPipeError:
            pass
        try:
            rc = p.wait(timeout=900)
        except subprocess.TimeoutExpired:
            p.kill()
            raise VideoError("ffmpeg", "timeout")
    if rc != 0:
        with open(errp, "r", errors="replace") as f:
            raise VideoError("ffmpeg", f.read()[-400:])
    log.info("strip done peak_child_rss=%.0fMB self_rss=%s",
             resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024, _self_rss())

    # free the PIL layers before the heavy encode
    del far, near, rays, word_imgs
    gc.collect()

    # pass 2: static base + strip + audio (same shape as the light chat path)
    script = os.path.join(work, f"filter_{tag}.txt")
    with open(script, "w") as f:
        f.write(
            f"[0:v]loop=loop=-1:size=1,fps={FPS},scale={W}:{H},"
            f"zoompan=z='min(1+0.00012*on,1.07)':x='iw/2-(iw/zoom)/2':y='ih/2-(ih/zoom)/2':d=1:s={W}x{H},"
            f"format=yuv420p[bg];\n"
            f"[bg][1:v]overlay=0:0:format=yuv420,fade=t=in:st=0:d=0.4,"
            f"fade=t=out:st={max(0.0, dur-0.4):.2f}:d=0.4,null[vout]")

    seg = os.path.join(work, f"seg_{tag}.mp4")
    _run(["ffmpeg", "-y", "-threads", "2", "-filter_threads", "2", "-filter_complex_threads", "2",
          "-i", base_p, "-i", strip, "-i", apath,
          "-filter_complex_script", script, "-map", "[vout]", "-map", "2:a",
          "-af", _finish(seg, dur),
          "-c:v", "libx264", "-preset", "superfast", "-crf", "21",
          "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-t", f"{dur:.3f}", seg])
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
    _run(["ffmpeg", "-y", "-threads", "2", "-i", os.path.join(work, f"cp_{tag}_%03d.png"),
          "-frames:v", str(steps), "-c:v", "qtrle", strip])

    seg = os.path.join(work, f"seg_{tag}.mp4")
    script = os.path.join(work, f"filter_{tag}.txt")
    with open(script, "w") as f:
        f.write(f"[0:v]loop=loop=-1:size=1,fps={FPS},format=yuv420p[bg];[bg][1:v]overlay=0:0:format=yuv420,"
                f"fade=t=in:st=0:d=0.3,fade=t=out:st={max(0.0,dur-0.3):.2f}:d=0.3,"
                f"null[vout]")
    _run(["ffmpeg", "-y", "-threads", "2", "-filter_threads", "2", "-filter_complex_threads", "2", "-i", base_p,
          "-i", strip, "-i", apath,
          "-filter_complex_script", script, "-map", "[vout]", "-map", "2:a",
          "-af", _finish(seg, dur),
          "-c:v", "libx264", "-preset", "superfast", "-crf", "21",
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

    for stale in os.listdir(CACHE):
        if stale.startswith("w_"):
            shutil.rmtree(os.path.join(CACHE, stale), ignore_errors=True)
    work = os.path.join(CACHE, f"w_{key}")
    os.makedirs(work, exist_ok=True)
    log.info("render start reciter=%s surah=%s %s-%s style=%s dur=%.1f self_rss=%s", reciter, surah, a1, a2, style, total, _self_rss())
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
        shutil.rmtree(work, ignore_errors=True)
        log.info("render done %s (%.1fs, %dKB)", final, total, os.path.getsize(final) // 1024)
    else:
        lst = os.path.join(work, "list.txt")
        with open(lst, "w") as f:
            for s in segs:
                f.write(f"file '{s}'\n")
        _run(["ffmpeg", "-y", "-threads", "2", "-f", "concat", "-safe", "0", "-i", lst,
              "-c", "copy", "-movflags", "+faststart", final])
    shutil.rmtree(work, ignore_errors=True)
    log.info("render done %s (%.1fs, %dKB)", final, total, os.path.getsize(final) // 1024)
    return final, total


if __name__ == "__main__":
    import sys
    reciter, surah, a1, a2, style = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
    solid = sys.argv[6] if len(sys.argv) > 6 else None
    path, dur = make_verse_video(reciter, surah, a1, a2, style, solid,
                                 progress=lambda i, n: print(f"seg {i}/{n}", flush=True))
    print(path, round(dur, 1), "s", os.path.getsize(path) // 1024, "KB")
