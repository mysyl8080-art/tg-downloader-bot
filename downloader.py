"""Download engine: yt-dlp for social/media sites, plain HTTP for direct file links."""
import os, re, shutil, tempfile
import requests
import yt_dlp
from yt_dlp.utils import DownloadError as YtDlpError

MAX_BYTES = 1900 * 1024 * 1024  # hard abort: 1.9 GB
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

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

def _ytdlp(url, audio_only=False):
    tmp = _tmpdir()
    opts = {
        "outtmpl": os.path.join(tmp, "%(title).80s.%(ext)s"),
        "format": ("bestaudio/best" if audio_only else
                   "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"),
        "merge_output_format": None if audio_only else "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 3,
        "http_headers": UA,
        "max_filesize": MAX_BYTES,
    }
    if audio_only:
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(url, download=True)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    files = [os.path.join(tmp, f) for f in os.listdir(tmp) if not f.endswith(".part")]
    if not files:
        raise DownloadError("yt-dlp finished but produced no file")
    path = max(files, key=os.path.getsize)
    title = (info.get("title") or "video").strip()
    ext = os.path.splitext(path)[1].lower()
    is_video = ext in (".mp4", ".mkv", ".webm", ".mov", ".avi")
    if audio_only and ext != ".mp3":
        cand = [f for f in files if f.endswith(".mp3")]
        if cand:
            path = cand[0]
    return Result(path, title, is_video, "yt-dlp")

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

def download_url(url, audio_only=False):
    """Try yt-dlp first (social/media sites); fall back to direct HTTP download."""
    looks_direct = bool(re.search(r"\.[A-Za-z0-9]{1,5}([?#].*)?$", url.split("/")[-1]))
    try:
        return _ytdlp(url, audio_only)
    except YtDlpError as e:
        msg = str(e)
        if "Unsupported URL" in msg or "no suitable InfoExtractor" in msg or looks_direct:
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
