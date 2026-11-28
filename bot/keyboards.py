"""Inline keyboards."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from downloader.info import ar_num


def main_menu(lang):
    from .text import t
    rows = [
        [InlineKeyboardButton(t(lang, "btn_download"), callback_data="m:dl")],
        [InlineKeyboardButton(t(lang, "btn_audio_tools"), callback_data="m:atools"),
         InlineKeyboardButton(t(lang, "btn_video_tools"), callback_data="m:vtools")],
        [InlineKeyboardButton(t(lang, "btn_history"), callback_data="m:hist"),
         InlineKeyboardButton(t(lang, "btn_favorites"), callback_data="m:fav")],
        [InlineKeyboardButton(t(lang, "btn_settings"), callback_data="m:set"),
         InlineKeyboardButton(t(lang, "btn_help"), callback_data="m:help")],
    ]
    return InlineKeyboardMarkup(rows)


def quality_kb(preview, lang):
    """Quality buttons from available heights + audio formats + subtitles."""
    from .text import t
    rows, row = [], []
    wanted = [2160, 1440, 1080, 720, 480, 360, 240, 144]
    avail = set(preview.qualities or [])
    show = [h for h in wanted if any(a >= h for a in avail)] or [720]
    if avail and max(avail) > 1080:
        show = [h for h in show if h <= 1080] + ["best"]
    else:
        show = show + ["best"]
    for q in show[:6]:
        label = "⭐ الأفضل" if q == "best" else f"{ar_num(q)}p"
        row.append(InlineKeyboardButton(label, callback_data=f"dl:v:{q}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("🎵 MP3", callback_data="dl:a:mp3"),
                 InlineKeyboardButton("M4A", callback_data="dl:a:m4a"),
                 InlineKeyboardButton("WAV", callback_data="dl:a:wav"),
                 InlineKeyboardButton("FLAC", callback_data="dl:a:flac")])
    if preview.subtitles:
        rows.append([InlineKeyboardButton("💬 ملف الترجمة", callback_data="dl:sub")])
    rows.append([InlineKeyboardButton(t(lang, "btn_cancel"), callback_data="dl:cancel")])
    return InlineKeyboardMarkup(rows)


def playlist_kb(lang):
    from .text import t
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 فيديو", callback_data="pl:v"),
         InlineKeyboardButton("🎵 صوت MP3", callback_data="pl:a")],
        [InlineKeyboardButton(t(lang, "btn_cancel"), callback_data="dl:cancel")],
    ])


def progress_kb(task_id, lang):
    from .text import t
    return InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_cancel"),
                                                       callback_data=f"t:cancel:{task_id}")]])


def result_kb(url, lang, failed=False, task_label=None):
    from .text import t
    rows = []
    if failed:
        rows.append([InlineKeyboardButton(t(lang, "btn_retry"), callback_data="t:retry")])
    else:
        rows.append([InlineKeyboardButton(t(lang, "btn_fav"), callback_data="t:fav")])
    return InlineKeyboardMarkup(rows)


def back_kb(lang, to="m:menu"):
    from .text import t
    return InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data=to)]])


def settings_kb(user, lang):
    q = user["def_quality"] if user else 720
    a = user["def_audio"] if user else "mp3"
    other_lang = "English" if lang == "ar" else "العربية"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🌐 {other_lang}", callback_data="s:lang")],
        [InlineKeyboardButton(f"🎬 الجودة الافتراضية: {ar_num(q)}p", callback_data="s:q")],
        [InlineKeyboardButton(f"🎵 الصوت الافتراضي: {a.upper()}", callback_data="s:a")],
        [InlineKeyboardButton("⬅️", callback_data="m:menu")],
    ])


def audio_tools_kb(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎵 استخراج الصوت MP3", callback_data="at:extract")],
        [InlineKeyboardButton("✂️ قص", callback_data="at:trim"),
         InlineKeyboardButton("🔊 مستوى الصوت", callback_data="at:vol")],
        [InlineKeyboardButton("🗜 ضغط", callback_data="at:comp"),
         InlineKeyboardButton("🎙 رسالة صوتية", callback_data="at:voice")],
        [InlineKeyboardButton("⬅️", callback_data="m:menu")],
    ])


def video_tools_kb(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✂️ قص", callback_data="vt:trim"),
         InlineKeyboardButton("🗜 ضغط", callback_data="vt:comp")],
        [InlineKeyboardButton("🎞 GIF", callback_data="vt:gif"),
         InlineKeyboardButton("⏩ سرعة", callback_data="vt:speed")],
        [InlineKeyboardButton("🔇 إزالة الصوت", callback_data="vt:mute"),
         InlineKeyboardButton("🔀 دمج صوت+فيديو", callback_data="vt:merge")],
        [InlineKeyboardButton("📸 لقطة", callback_data="vt:shot"),
         InlineKeyboardButton("ℹ️ معلومات", callback_data="vt:meta")],
        [InlineKeyboardButton("🔄 تحويل MKV", callback_data="vt:mkv"),
         InlineKeyboardButton("⬅️", callback_data="m:menu")],
    ])
