"""Platform detection from URLs. Pure functions, no network."""
import re
from urllib.parse import urlparse

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

_PLATFORMS = [
    ("youtube", ("youtube.com", "youtu.be", "music.youtube.com")),
    ("tiktok", ("tiktok.com", "vt.tiktok.com", "vm.tiktok.com")),
    ("instagram", ("instagram.com", "instagr.am")),
    ("facebook", ("facebook.com", "fb.watch", "fb.com")),
    ("x", ("twitter.com", "x.com", "t.co")),
    ("reddit", ("reddit.com", "redd.it")),
    ("pinterest", ("pinterest.com", "pin.it")),
    ("snapchat", ("snapchat.com",)),
    ("linkedin", ("linkedin.com",)),
    ("soundcloud", ("soundcloud.com",)),
    ("twitch", ("twitch.tv",)),
    ("vimeo", ("vimeo.com",)),
    ("dailymotion", ("dailymotion.com", "dai.ly")),
    ("telegram", ("t.me", "telegram.me")),
]

PLATFORM_AR = {
    "youtube": "يوتيوب", "tiktok": "تيك توك", "instagram": "إنستجرام",
    "facebook": "فيسبوك", "x": "إكس (تويتر)", "reddit": "ريديت",
    "pinterest": "بينتيريست", "snapchat": "سناب شات", "linkedin": "لينكدإن",
    "soundcloud": "ساوند كلاود", "twitch": "تويتش", "vimeo": "فيميو",
    "dailymotion": "ديلي موشن", "telegram": "تليجرام", "web": "رابط مباشر",
    "unknown": "غير معروف",
}


def extract_urls(text):
    """All URLs found in a message, order preserved, deduped."""
    seen, out = set(), []
    for m in URL_RE.finditer(text or ""):
        u = m.group(0).rstrip(").,;!")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def host_of(url):
    try:
        return urlparse(url).netloc.lower().split("@")[-1].split(":")[0]
    except Exception:
        return ""


def detect_platform(url):
    """Platform key for a URL; 'web' for direct file links, 'unknown' otherwise."""
    host = host_of(url)
    for name, domains in _PLATFORMS:
        if any(host == d or host.endswith("." + d) for d in domains):
            return name
    if re.search(r"\.[A-Za-z0-9]{1,5}([?#].*)?$", url.split("/")[-1]):
        return "web"
    return "unknown"


def is_playlist(url):
    p = detect_platform(url)
    q = urlparse(url).query.lower()
    path = urlparse(url).path.lower()
    return (p == "youtube" and ("list=" in q or "/playlist" in path)) or \
           (p == "soundcloud" and "/sets/" in path)


def safe_filename(name, fallback="file"):
    """Strip path separators and control chars; bound length."""
    name = re.sub(r"[\\/\x00-\x1f\x7f]+", " ", (name or "")).strip().strip(".")
    name = re.sub(r"\s+", " ", name)
    return (name or fallback)[:120]
