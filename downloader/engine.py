"""yt-dlp download engine: formats, progress, cancellation, splitting.

Everything CPU/network bound here is synchronous; callers run it in a thread.
Cancellation works via a threading.Event checked in the progress hook.
"""
import logging
import os
import re
import shutil
import subprocess
import threading

import yt_dlp

from config import settings
from .platforms import detect_platform, safe_filename

log = logging.getLogger("udv3.engine")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


class DownloadError(Exception):
    """User-facing failure. `key` selects the Arabic message, `detail` is logged."""

    def __init__(self, key, detail=None):
        super().__init__(key if detail is None else f"{key}: {detail}")
        self.key = key
        self.detail = detail


class Cancelled(Exception):
    pass


class Result:
    def __init__(self, paths, title, platform, is_video, duration=None, thumb=None):
        self.paths = paths            # list of files to send (already split if needed)
        self.title = title
        self.platform = platform
        self.is_video = is_video
        self.duration = duration
        self.thumb = thumb


def _base_opts():
    opts = {
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 3,
        "http_headers": UA,
        "max_filesize": settings.MAX_FILE_BYTES,
        "restrictfilenames": False,
    }
    if settings.PROXY_URL:
        opts["proxy"] = settings.PROXY_URL
    if settings.YT_COOKIES and os.path.exists(settings.YT_COOKIES):
        opts["cookiefile"] = settings.YT_COOKIES
    return opts


def video_format(height, container="mp4"):
    """yt-dlp format selector for a target height with graceful fallback."""
    if height and height > 0:
        sel = (f"bestvideo[height<={height}][ext={container}]+bestaudio[ext=m4a]/"
               f"bestvideo[height<={height}]+bestaudio/"
               f"best[height<={height}][ext={container}]/best[height<={height}]/best")
    else:
        sel = f"bestvideo[ext={container}]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext={container}]/best"
    return sel


def _map_error(e):
    msg = str(e)
    low = msg.lower()
    if "cancelled" in low:
        raise Cancelled()
    if "sign in to confirm" in low or "login_required" in low:
        return DownloadError("blocked", msg[-200:])
    if "private" in low or "members-only" in low:
        return DownloadError("private", msg[-200:])
    if "404" in msg or "not found" in low or "has been removed" in low:
        return DownloadError("gone", msg[-200:])
    if "unsupported url" in low or "no suitable infoextractor" in low:
        return DownloadError("unsupported", msg[-200:])
    if "file is larger than" in low:
        return DownloadError("toobig", msg[-200:])
    if "timed out" in low or "timeout" in low:
        return DownloadError("timeout", msg[-200:])
    return DownloadError("failed", msg[-300:])


def probe(url, playlist=False):
    """Metadata without downloading. Returns the info dict (flat for playlists)."""
    opts = _base_opts()
    opts.update({"extract_flat": "in_playlist" if playlist else False,
                 "noplaylist": not playlist})
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            return y.extract_info(url, download=False)
    except Exception as e:
        raise _map_error(e)


def list_qualities(info):
    """Heights actually available, descending."""
    heights = sorted({f["height"] for f in info.get("formats") or []
                      if f.get("height")}, reverse=True)
    return heights


def download(url, workdir, *, kind="video", quality=720, audio_fmt="mp3",
             container="mp4", cancel=None, progress=None, playlist_items=None):
    """Download one URL. Returns Result. Runs in a worker thread.

    kind: 'video' | 'audio'
    progress(downloaded_bytes, total_bytes_or_None, speed_Bps) — called from this thread.
    """
    cancel = cancel or threading.Event()
    os.makedirs(workdir, exist_ok=True)

    def hook(d):
        if cancel.is_set():
            raise yt_dlp.utils.DownloadError("cancelled")
        if d.get("status") == "downloading" and progress:
            try:
                progress(d.get("downloaded_bytes", 0),
                         d.get("total_bytes") or d.get("total_bytes_estimate"),
                         d.get("speed"))
            except Exception:
                pass

    opts = _base_opts()
    opts.update({
        "outtmpl": os.path.join(workdir, "%(title).80s.%(ext)s"),
        "progress_hooks": [hook],
        "noplaylist": playlist_items is None,
    })
    if playlist_items:
        opts["playlist_items"] = playlist_items
    if kind == "audio":
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": audio_fmt,
            "preferredquality": "192" if audio_fmt == "mp3" else None,
        }]
        if audio_fmt in ("wav", "flac", "m4a"):
            opts["postprocessors"][0].pop("preferredquality", None)
    else:
        opts["format"] = video_format(quality, container)
        opts["merge_output_format"] = container

    try:
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as e:
        if cancel.is_set():
            raise Cancelled()
        if detect_platform(url) == "tiktok" and not playlist_items:
            return _tikwm(url, workdir, kind)
        raise _map_error(e)
    except Exception as e:
        if cancel.is_set():
            raise Cancelled()
        if detect_platform(url) == "tiktok" and not playlist_items:
            return _tikwm(url, workdir, kind)
        raise _map_error(e)

    files = sorted(
        (os.path.join(workdir, f) for f in os.listdir(workdir)
         if not f.endswith((".part", ".ytdl", ".description"))),
        key=os.path.getmtime)
    files = [f for f in files if os.path.isfile(f) and os.path.getsize(f) > 0]
    if not files:
        raise DownloadError("toobig")

    title = safe_filename((info or {}).get("title") or os.path.basename(files[0]))
    is_video = kind == "video"
    duration = (info or {}).get("duration")
    thumb = _find_thumb(workdir)
    paths = []
    for f in files:
        paths.extend(split_if_needed(f))
    return Result(paths, title, detect_platform(url), is_video, duration, thumb)


def _tikwm(url, workdir, kind):
    """TikTok fallback via the public tikwm API (yt-dlp is often blocked on datacenter IPs)."""
    import requests
    try:
        r = requests.post("https://www.tikwm.com/api/", data={"url": url, "hd": 1},
                          headers=UA, timeout=30)
        d = r.json().get("data") or {}
    except Exception:
        raise DownloadError("failed", "tikwm api")
    title = safe_filename(d.get("title") or "tiktok")
    music = d.get("music")

    def _get(u, name):
        p = os.path.join(workdir, name)
        with requests.get(u, headers=UA, stream=True, timeout=(15, 60)) as rr:
            rr.raise_for_status()
            with open(p, "wb") as f:
                for c in rr.iter_content(1024 * 256):
                    f.write(c)
        return p

    try:
        if kind == "audio":
            if not music:
                raise DownloadError("failed", "tikwm: no audio")
            p = _get(music, "audio.mp3")
            return Result([p], title, "tiktok", False)
        images = d.get("images") or []
        if images:
            imgs = [_get(u, f"img_{i:03d}.jpg") for i, u in enumerate(images)]
            audio = _get(music, "music.mp3") if music else None
            lst = os.path.join(workdir, "list.txt")
            with open(lst, "w") as f:
                for p in imgs:
                    f.write(f"file '{p}'\nduration 3\n")
                f.write(f"file '{imgs[-1]}'\n")
            out = os.path.join(workdir, "slideshow.mp4")
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst]
            if audio:
                cmd += ["-i", audio, "-shortest"]
            cmd += ["-vf", "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
                    "-r", "25", "-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart", out]
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if p.returncode != 0:
                raise DownloadError("failed", "tikwm slideshow ffmpeg")
            return Result([out], title, "tiktok", True)
        play = d.get("hdplay") or d.get("play")
        if play:
            p = _get(play, "video.mp4")
            return Result([p], title, "tiktok", True, d.get("duration"), d.get("cover"))
        raise DownloadError("failed", "tikwm: no streams")
    except DownloadError:
        raise
    except Exception as e:
        raise DownloadError("failed", f"tikwm: {e}")


def _find_thumb(workdir):
    for ext in (".jpg", ".webp", ".png"):
        for f in sorted(os.listdir(workdir)):
            if f.endswith(ext):
                return os.path.join(workdir, f)
    return None


def split_if_needed(path):
    """Split into <=SPLIT_BYTES parts when over the send cap. Returns file list."""
    size = os.path.getsize(path)
    if size <= settings.SEND_BYTES:
        return [path]
    if size > settings.MAX_FILE_BYTES:
        raise DownloadError("toobig")
    parts, n = [], (size + settings.SPLIT_BYTES - 1) // settings.SPLIT_BYTES
    base, ext = os.path.splitext(path)
    with open(path, "rb") as src:
        for i in range(n):
            part = f"{base}.part{i+1:02d}{ext}"
            chunk = src.read(settings.SPLIT_BYTES)
            if not chunk:
                break
            with open(part, "wb") as dst:
                dst.write(chunk)
            parts.append(part)
    os.remove(path)
    log.info("split %s into %s parts", path, n)
    return parts


def cleanup(path_or_dir):
    try:
        if os.path.isdir(path_or_dir):
            shutil.rmtree(path_or_dir, ignore_errors=True)
        elif os.path.exists(path_or_dir):
            os.remove(path_or_dir)
    except Exception:
        pass
