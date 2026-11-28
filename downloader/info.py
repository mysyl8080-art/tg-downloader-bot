"""Preview metadata: title, duration, uploader, thumbnail, sizes, subtitles."""
import re


def _fmt_bytes(n):
    if not n:
        return None
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return None


def _fmt_dur(s):
    if s is None:
        return "؟"
    s = int(s)
    return f"{s // 60}:{s % 60:02d}" if s < 3600 else f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


class Preview:
    def __init__(self, info, platform):
        self.title = (info.get("title") or "—")[:150]
        self.uploader = info.get("uploader") or info.get("channel") or ""
        self.duration = info.get("duration")
        self.thumbnail = info.get("thumbnail")
        self.platform = platform
        self.webpage = info.get("webpage_url") or ""
        self.is_playlist = info.get("_type") == "playlist" or bool(info.get("entries"))
        self.entries = list(info.get("entries") or [])
        self.subtitles = sorted((info.get("subtitles") or {}).keys())
        heights = sorted({f["height"] for f in info.get("formats") or []
                          if f.get("height")}, reverse=True)
        self.qualities = heights
        # rough size estimate for the best <=1080 video + best audio
        est = 0
        for f in info.get("formats") or []:
            if f.get("height") and f["height"] <= 1080 and (f.get("filesize") or f.get("filesize_approx")):
                est = max(est, f.get("filesize") or f.get("filesize_approx") or 0)
        self.size_est = est or None

    @property
    def count(self):
        return len(self.entries)

    def summary_ar(self):
        lines = [f"🎬 <b>{self.title}</b>"]
        if self.uploader:
            lines.append(f"👤 {self.uploader}")
        if self.is_playlist:
            lines.append(f"📚 قائمة تشغيل: {self.count} عنصر")
        if self.duration:
            lines.append(f"⏱ المدة: {_fmt_dur(self.duration)}")
        if self.size_est:
            lines.append(f"💾 الحجم التقريبي: {_fmt_bytes(self.size_est)}")
        if self.subtitles:
            lines.append(f"💬 ترجمات: {', '.join(self.subtitles[:6])}")
        return "\n".join(lines)


_AR_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def ar_num(n):
    return str(n).translate(_AR_DIGITS)
