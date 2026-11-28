"""Entry points: /start /help, guards, message routing."""
import logging

from telegram import Update
from telegram.ext import ContextTypes

from database import db
from downloader.platforms import extract_urls
from config import settings
from .. import keyboards as kb
from ..state import maintenance, rate_limited, pending
from ..text import t
from . import downloads, tools

log = logging.getLogger("udv3.core")


def lang_of(user_id):
    u = db.get_user(user_id)
    return (u["lang"] if u else "ar") or "ar"


async def guard(update: Update) -> bool:
    """False = stop handling. Registers the user, enforces ban/maintenance."""
    user = update.effective_user
    if not user:
        return False
    if db.get_user(user.id) is None:
        log.info("new user joined id=%s username=%s", user.id, user.username)
    db.upsert_user(user)
    lang = lang_of(user.id)
    if db.is_banned(user.id):
        if update.message:
            await update.message.reply_text(t(lang, "banned"))
        return False
    if maintenance and user.id not in settings.ADMIN_IDS:
        if update.message:
            await update.message.reply_text(t(lang, "maintenance"))
        return False
    return True


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    lang = lang_of(update.effective_user.id)
    await update.message.reply_text(t(lang, "welcome"), parse_mode="HTML",
                                    reply_markup=kb.main_menu(lang))


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    msg = update.message
    uid = msg.from_user.id
    lang = lang_of(uid)
    text = (msg.text or msg.caption or "").strip()

    urls = extract_urls(text)
    if urls:
        if rate_limited(uid):
            await msg.reply_text(t(lang, "rate_limited"))
            return
        if len(urls) == 1:
            await downloads.start_probe(msg, ctx, urls[0], lang)
        else:
            urls = urls[:settings.MULTI_URL_MAX]
            u = db.get_user(uid)
            q = u["def_quality"] if u else 720
            a = u["def_audio"] if u else "mp3"
            await msg.reply_text(t(lang, "multi_start", n=len(urls), q=q))
            for url in urls:
                status = await msg.reply_text(f"🔗 {url[:70]}")
                await downloads.run_download_task(ctx.bot, msg.chat_id, uid, url,
                                                  "video", q, a, status.message_id, lang)
        return

    # pending tool input (trim times, volume factor, ...)
    if uid in pending and pending[uid].get("await_input"):
        if await tools.handle_input(msg, ctx, pending[uid], lang):
            return

    await msg.reply_text(t(lang, "send_link"))


async def on_media(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """A media file sent to the bot: remember it as the tools target."""
    if not await guard(update):
        return
    msg = update.message
    uid = msg.from_user.id
    media = msg.video or msg.audio or msg.voice or msg.document or msg.video_note
    if not media:
        return
    lang = lang_of(uid)
    try:
        tg_file = await media.get_file()
        import os
        ext = os.path.splitext(getattr(media, "file_name", "") or "")[1] or \
            (".mp4" if (msg.video or msg.video_note) else ".mp3")
        path = os.path.join(settings.TMP_DIR, f"up_{uid}_{media.file_unique_id}{ext}")
        await tg_file.download_to_drive(path)
        from ..state import last_file
        last_file[uid] = (path, bool(msg.video or msg.video_note or
                                     (msg.document and (msg.document.mime_type or "").startswith("video"))))
        await msg.reply_text("📎 " + t(lang, "done"), reply_markup=kb.back_kb(lang))
    except Exception:
        log.exception("media save failed")
        await msg.reply_text(t(lang, "err_failed"))
