"""Callback query routing: menu, downloads, tools, settings, admin."""
import logging

from telegram import Update
from telegram.ext import ContextTypes

from config import settings
from database import db
from downloader.info import Preview
from .. import keyboards as kb
from ..state import queue, pending, maintenance
from ..text import t
from . import downloads, tools, user as user_h
from .core import lang_of

log = logging.getLogger("udv3.cb")


async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    uid = q.from_user.id
    db.upsert_user(q.from_user)
    lang = lang_of(uid)
    data = q.data or ""

    # --- main menu ---
    if data == "m:menu":
        await q.edit_message_text(t(lang, "main_menu"), reply_markup=kb.main_menu(lang))
    elif data == "m:dl":
        await q.edit_message_text(t(lang, "send_link"), reply_markup=kb.back_kb(lang))
    elif data == "m:help":
        await q.edit_message_text(t(lang, "help"), parse_mode="HTML",
                                  reply_markup=kb.back_kb(lang))
    elif data == "m:hist":
        await user_h.show_history(q, lang)
    elif data == "m:fav":
        await user_h.show_favorites(q, lang)
    elif data == "m:set":
        await user_h.show_settings(q, uid, lang)
    elif data == "m:atools":
        await q.edit_message_text("🎧 " + t(lang, "btn_audio_tools"),
                                  reply_markup=kb.audio_tools_kb(lang))
    elif data == "m:vtools":
        await q.edit_message_text("🎬 " + t(lang, "btn_video_tools"),
                                  reply_markup=kb.video_tools_kb(lang))

    # --- settings ---
    elif data.startswith("s:"):
        await user_h.on_setting(q, uid, lang, data[2:])

    # --- downloads ---
    elif data.startswith("dl:"):
        await on_download_choice(q, ctx, uid, lang, data)
    elif data.startswith("pl:"):
        await on_playlist_choice(q, ctx, uid, lang, data[3:])
    elif data.startswith("t:"):
        await on_task_action(q, ctx, uid, lang, data[2:])

    # --- tools ---
    elif data.startswith("at:") or data.startswith("vt:"):
        await tools.on_tool(q, ctx, uid, lang, data)

    # --- favorites ---
    elif data.startswith("f:"):
        await user_h.on_favorite(q, uid, lang, data[2:])


async def on_download_choice(q, ctx, uid, lang, data):
    parts = data.split(":")
    action = parts[1]
    pend = pending.get(uid)
    if action == "cancel":
        pending.pop(uid, None)
        await q.edit_message_text(t(lang, "cancelled"))
        return
    if not pend or pend.get("kind") != "single":
        await q.edit_message_text(t(lang, "send_link"))
        return
    url = pend["url"]
    if action == "sub":
        subs = pend.get("subtitles") or []
        if not subs:
            await q.answer(t(lang, "subtitles_none"), show_alert=True)
            return
        await q.edit_message_text("💬 اختر الترجمة:", reply_markup=_subs_kb(url, subs, lang))
        return
    if action == "v":
        quality = parts[2]
        quality = 4320 if quality == "best" else int(quality)
        await run(q, ctx, uid, lang, url, "video", quality, "mp3")
    elif action == "a":
        await run(q, ctx, uid, lang, url, "audio", 0, parts[2])


def _subs_kb(url, subs, lang):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    rows = [[InlineKeyboardButton(s, callback_data=f"sub:{s}")] for s in subs[:8]]
    rows.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="dl:back")])
    return InlineKeyboardMarkup(rows)


async def run(q, ctx, uid, lang, url, kind, quality, audio_fmt):
    await q.edit_message_text(t(lang, "downloading"))
    await downloads.run_download_task(ctx.bot, q.message.chat_id, uid, url,
                                      kind, quality, audio_fmt, q.message.message_id, lang)


async def on_playlist_choice(q, ctx, uid, lang, action):
    pend = pending.pop(uid, None)
    if not pend or pend.get("kind") != "playlist":
        await q.edit_message_text(t(lang, "send_link"))
        return
    url, count = pend["url"], min(pend["count"], settings.PLAYLIST_MAX)
    kind = "video" if action == "v" else "audio"
    u = db.get_user(uid)
    quality = (u["def_quality"] if u else 720) if kind == "video" else 0
    audio_fmt = u["def_audio"] if u else "mp3"
    await q.edit_message_text(f"📚 {count} → {t(lang, 'downloading')}")
    # one queued task per item keeps cancellation granular
    for i in range(1, count + 1):
        status = await ctx.bot.send_message(q.message.chat_id, f"📚 {i}/{count}")
        await _run_playlist_item(ctx, q.message.chat_id, uid, url, i, kind,
                                 quality, audio_fmt, status.message_id, lang)


async def _run_playlist_item(ctx, chat_id, uid, url, idx, kind, quality, audio_fmt,
                             msg_id, lang):
    from downloader import engine
    async def job(task):
        import asyncio, os, threading, time
        cancel = threading.Event()
        workdir = os.path.join(settings.TMP_DIR, f"u{uid}_{task.id}")
        def watch():
            task.cancel_event.wait()
            cancel.set()
        threading.Thread(target=watch, daemon=True).start()
        try:
            res = await asyncio.to_thread(
                engine.download, url, workdir, kind=kind, quality=quality,
                audio_fmt=audio_fmt, cancel=cancel, playlist_items=str(idx))
            for path in res.paths:
                await downloads._send_file(ctx.bot, chat_id, path, res, f"📚 {idx} • {res.title}")
                engine.cleanup(path)
            db.log_download(uid, url, res.platform, kind, res.title, "ok")
            await downloads._safe_edit(ctx.bot, chat_id, msg_id, f"✅ {idx}. {res.title}")
        except engine.Cancelled:
            await downloads._safe_edit(ctx.bot, chat_id, msg_id, t(lang, "cancelled"))
            engine.cleanup(workdir)
        except engine.DownloadError as e:
            await downloads._safe_edit(ctx.bot, chat_id, msg_id, f"❌ {idx}. " + t(lang, f"err_{e.key}"))
            db.log_download(uid, url, None, kind, None, "failed", e.key)
            engine.cleanup(workdir)
    from ..state import queue as q_
    q_.submit(job, f"pl:{idx}:{url[:50]}", uid, retries=0)


async def on_task_action(q, ctx, uid, lang, data):
    action, _, arg = data.partition(":")
    if action == "cancel":
        if queue.cancel(int(arg)):
            await q.edit_message_text(t(lang, "cancelled"))
        else:
            await q.answer("انتهى بالفعل")
    elif action == "retry":
        pend = pending.get(uid)
        if not pend or pend.get("kind") != "retry":
            await q.edit_message_text(t(lang, "send_link"))
            return
        await run(q, ctx, uid, lang, pend["url"], pend["dl_kind"],
                  pend["quality"], pend["audio_fmt"])
    elif action == "fav":
        pend = pending.get(uid) or {}
        url = pend.get("url")
        if url:
            db.add_favorite(uid, url, None)
            await q.answer(t(lang, "fav_added"), show_alert=True)
