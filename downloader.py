"""Download engine: yt-dlp for social/media sites, plain HTTP for direct file links."""
import os, re, shutil, tempfile, subprocess
from urllib.parse import urlparse
import requests
import yt_dlp
from yt_dlp.utils import DownloadError as YtDlpError

MAX_BYTES = 1900 * 1024 * 1024  # hard abort: 1.9 GB
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

TG_LIMIT = 49 * 1024 * 1024

def _vfmt(h):
    return (f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={h}]+bestaudio/"
            f"best[height<={h}]/best")

class DownloadError(Exception):
    pass

class Result:
    def __init__(self, path, title, is_video, source):
        self.path, self.title, self.is_video, self.source = path, title, is_video, source

def _tmpdir():
    d = tempfile.mkdtemp(prefix="tgdl_")
    return d

def cleanup(result):
    if result and result.path:
        shutil.rmtree(os.path.dirname(result.path), ignore_errors=True)

def _ytdlp(url, audio_only=False, quality=None):
    tmp = _tmpdir()
    opts = {
        "outtmpl": os.path.join(tmp, "%(title).80s.%(ext)s"),
        "format": ("bestaudio/best" if audio_only else _vfmt(quality or 1080)),
        "merge_output_format": None if audio_only else "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 3,
        "http_headers": UA,
        "max_filesize": MAX_BYTES,
    }
    if os.environ.get("PROXY_URL"):
        opts["proxy"] = os.environ["PROXY_URL"]
    if _is_tiktok(url) and _tiktok_cookies():
        opts["cookiefile"] = _tiktok_cookies()
    if audio_only:
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": str(quality or 192)}]
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(url, download=True)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    files = [os.path.join(tmp, f) for f in os.listdir(tmp) if not f.endswith(".part")]
    if not files:
        raise DownloadError("TOOBIG")
    path = max(files, key=os.path.getsize)
    title = (info.get("title") or "video").strip()
    ext = os.path.splitext(path)[1].lower()
    is_video = ext in (".mp4", ".mkv", ".webm", ".mov", ".avi")
    if audio_only and ext != ".mp3":
        cand = [f for f in files if f.endswith(".mp3")]
        if cand:
            path = cand[0]
    return Result(path, title, is_video, "yt-dlp")

TIKTOK_RE = re.compile(r"(^|\.)tiktok\.com$")
SOCIAL_HTML_HOSTS = ("tiktok.com", "instagram.com", "facebook.com", "fb.watch", "twitter.com", "x.com", "youtube.com", "youtu.be")

def _host(url):
    return (urlparse(url).hostname or "").lower()

def _is_tiktok(url):
    return bool(TIKTOK_RE.search(_host(url)))

def _is_social(url):
    h = _host(url)
    return any(h == d or h.endswith("." + d) for d in SOCIAL_HTML_HOSTS)

def _resolve_tiktok(url):
    """Follow vt./vm. short links and turn /photo/ID into /video/ID (yt-dlp only knows /video/)."""
    if _is_tiktok(url) and _host(url) not in ("www.tiktok.com", "tiktok.com"):
        try:
            r = requests.get(url, headers=UA, allow_redirects=True, timeout=(10, 20), stream=True)
            url = r.url
            r.close()
        except requests.RequestException:
            pass
    return re.sub(r"/photo/(\d+)", r"/video/\1", url) if _is_tiktok(url) else url

def _tiktok_cookies():
    p = os.environ.get("TIKTOK_COOKIES_FILE")
    return p if p and os.path.exists(p) else None

def _tikwm(url, audio_only=False):
    """Fallback for TikTok videos and photo slideshows via the public tikwm API."""
    tmp = _tmpdir()
    try:
        r = requests.post("https://www.tikwm.com/api/", data={"url": url, "hd": 1}, headers=UA, timeout=30)
        d = r.json().get("data") or {}
        title = (d.get("title") or "tiktok").strip()[:80] or "tiktok"
        music = d.get("music")
        images = d.get("images") or []
        def get(u, name):
            p = os.path.join(tmp, name)
            with requests.get(u, headers=UA, stream=True, timeout=(15, 60)) as rr:
                rr.raise_for_status()
                with open(p, "wb") as f:
                    for c in rr.iter_content(1024 * 256):
                        f.write(c)
            return p
        if images:  # photo slideshow -> mp4 (or mp3 if audio only)
            audio = get(music, "music.mp3") if music else None
            if audio_only and audio:
                return Result(audio, title, False, "tikwm")
            imgs = [get(u, f"img_{i:03d}.jpg") for i, u in enumerate(images)]
            per = 3
            lst = os.path.join(tmp, "list.txt")
            with open(lst, "w") as f:
                for p in imgs:
                    f.write(f"file '{p}'\nduration {per}\n")
                f.write(f"file '{imgs[-1]}'\n")
            out = os.path.join(tmp, "slideshow.mp4")
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst]
            if audio:
                cmd += ["-i", audio, "-shortest"]
            cmd += ["-vf", "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
                    "-r", "25", "-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart", out]
            subprocess.run(cmd, check=True, timeout=600)
            return Result(out, title, True, "tikwm")
        play = d.get("hdplay") or d.get("play")
        if audio_only and music:
            return Result(get(music, "music.mp3"), title, False, "tikwm")
        if play:
            return Result(get(play, "video.mp4"), title, True, "tikwm")
        raise DownloadError("تيك توك رفض التحميل من الخادم، جرّب لينك تاني")
    except DownloadError:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise DownloadError("تيك توك رفض التحميل من الخادم، جرّب لينك تاني")

def _tiktok(url, audio_only=False, quality=None):
    orig = url
    url = _resolve_tiktok(url)
    try:
        return _ytdlp(url, audio_only, quality)
    except Exception:
        return _tikwm(url, audio_only)

def _direct(url):
    tmp = _tmpdir()
    try:
        with requests.get(url, stream=True, timeout=(15, 60), headers=UA, allow_redirects=True) as r:
            r.raise_for_status()
            cl = r.headers.get("Content-Length")
            if cl and int(cl) > MAX_BYTES:
                raise DownloadError("الملف أكبر من الحد المسموح")
            cd = r.headers.get("Content-Disposition", "")
            m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', cd)
            name = m.group(1) if m else os.path.basename(r.url.split("?")[0]) or "file"
            name = re.sub(r"[^\w.\- ]+", "_", name)[:100]
            path = os.path.join(tmp, name)
            total = 0
            with open(path, "wb") as f:
                for chunk in r.iter_content(1024 * 256):
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise DownloadError("الملف أكبر من الحد المسموح")
                    f.write(chunk)
        ctype = r.headers.get("Content-Type", "")
        if "text/html" in ctype and not re.search(r"\.\w{1,5}$", name):
            shutil.rmtree(tmp, ignore_errors=True)
            raise DownloadError("الرابط ليس ملفًا مباشرًا")
        return Result(path, name, ctype.startswith("video/"), "direct")
    except requests.RequestException as e:
        shutil.rmtree(tmp, ignore_errors=True)
        raise DownloadError(f"فشل التحميل المباشر: {e}")

def download_url(url, audio_only=False, quality=None, direct=False):
    """Try yt-dlp first (social/media sites); fall back to direct HTTP download."""
    looks_direct = bool(re.search(r"\.[A-Za-z0-9]{1,5}([?#].*)?$", url.split("/")[-1]))
    if direct:
        return _direct(url)
    if _is_tiktok(url):
        return _tiktok(url, audio_only, quality)
    try:
        return _ytdlp(url, audio_only, quality)
    except YtDlpError as e:
        msg = str(e)
        if "Unsupported URL" in msg or "no suitable InfoExtractor" in msg or looks_direct:
            if _is_social(url) and not looks_direct:
                raise DownloadError("الموقع ده مش مدعوم أو اللينك مش فيديو")
            return _direct(url)
        if "Sign in to confirm" in msg or "HTTP Error 403" in msg:
            raise DownloadError("الموقع حظر التحميل من الخادم (حماية ضد الروبوتات). جرّب رابطًا آخر.")
        raise DownloadError("تعذّر تحميل الرابط (قد يكون خاصًا أو محذوفًا)")
    except DownloadError:
        raise
    except Exception as e:
        if looks_direct:
            return _direct(url)
        raise DownloadError(f"خطأ غير متوقع: {e}")


import subprocess, math

PART_BYTES = 44 * 1024 * 1024

def _duration(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=nw=1:nk=1", path], capture_output=True, text=True, timeout=60).stdout
        return float(out.strip())
    except Exception:
        return 0.0

def split_file(path):
    """Return a list of part paths each <= ~44 MB. Media is cut by time (each part plays alone);
    other files are byte-split (.001, .002 ...)."""
    size = os.path.getsize(path)
    if size <= TG_LIMIT:
        return [path]
    base, ext = os.path.splitext(path)
    outdir = os.path.dirname(path)
    dur = _duration(path)
    if dur > 0 and ext.lower() in (".mp4", ".mkv", ".webm", ".mov", ".mp3", ".m4a", ".ogg", ".opus", ".wav"):
        parts = math.ceil(size / PART_BYTES) + 1
        for _ in range(4):
            seg = max(5, int(dur / parts))
            for f in os.listdir(outdir):
                if f.startswith("part_"):
                    os.remove(os.path.join(outdir, f))
            pat = os.path.join(outdir, "part_%03d" + ext)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-c", "copy", "-map", "0",
                            "-f", "segment", "-segment_time", str(seg), "-reset_timestamps", "1", pat],
                           check=True, timeout=1200)
            files = sorted(os.path.join(outdir, f) for f in os.listdir(outdir) if f.startswith("part_"))
            if files and all(os.path.getsize(f) <= TG_LIMIT for f in files):
                os.remove(path)
                return files
            parts = int(parts * 1.5) + 1
    # byte split fallback
    files = []
    with open(path, "rb") as src:
        i = 1
        while True:
            chunk = src.read(PART_BYTES)
            if not chunk:
                break
            p = os.path.join(outdir, f"{os.path.basename(path)}.{i:03d}")
            with open(p, "wb") as o:
                o.write(chunk)
            files.append(p); i += 1
    os.remove(path)
    return files
