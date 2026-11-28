"""Download flow: probe -> preview -> quality pick -> queued download -> send."""
import asyncio
import logging
import os
import threading
import time

from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ChatAction

from config import settings
from database import db
from downloader import engine
from downloader.info import Preview, ar_num
from downloader.platforms import detect_platform, is_playlist, PLATFORM_AR
from media.ffmpeg_base import probe_media
from services.queue import Task
from .. import keyboards as kb
from ..state import queue, pending, last_file
from ..text import t

log = logging.getLogger("udv3.dl")


def lang_of(update, ctx):
    u = db.get_user(update.effective_user.id)
    return (u["lang"] if u else "ar") or "ar"


async def start_probe(message, ctx, url, lang):
    """Probe a single URL and show the preview card with quality options."""
    status = await message.reply_text(t(lang, "probing"))
    try:
        playlist = is_playlist(url)
        info = await asyncio.to_thread(engine.probe, url, playlist)
    except engine.DownloadError as e:
        await status.edit_text(t(lang, f"err_{e.key}"))
        db.log_download(message.from_user.id, url, detect_platform(url), "probe", None, "failed", e.key)
        return
    except Exception:
        log.exception("probe failed")
        await status.edit_text(t(lang, "err_failed"))
        return

    pv = Preview(info, detect_platform(url))
    uid = message.from_user.id
    if pv.is_playlist and pv.count > 1:
        pending[uid] = {"kind": "playlist", "url": url, "count": pv.count}
        await status.edit_text(
            t(lang, "playlist_pick", n=ar_num(pv.count), m=ar_num(settings.PLAYLIST_MAX)),
            reply_markup=kb.playlist_kb(lang))
        return

    pending[uid] = {"kind": "single", "url": url,
                    "qualities": pv.qualities, "subtitles": pv.subtitles}
    text = pv.summary_ar() + "\n\n" + t(lang, "choose")
    sent_preview = False
    if pv.thumbnail:
        try:
            await message.reply_photo(pv.thumbnail, caption=text, parse_mode="HTML",
                                      reply_markup=kb.quality_kb(pv, lang))
            await status.delete()
            sent_preview = True
        except Exception:
            pass
    if not sent_preview:
        await status.edit_text(text, parse_mode="HTML",
                               reply_markup=kb.quality_kb(pv, lang))


async def run_download_task(bot, chat_id, user_id, url, kind, quality, audio_fmt,
                            status_msg_id, lang):
    """The queued job body. Edits the status message, sends the files."""

    async def job(task: Task):
        cancel = threading.Event()
        loop = asyncio.get_running_loop()
        workdir = os.path.join(settings.TMP_DIR, f"u{user_id}_{task.id}")

        def _cancel_watcher():
            while not task.cancel_event.is_set():
                if task.cancelled:
                    cancel.set()
                    return
                time.sleep(0.3)
            cancel.set()

        threading.Thread(target=_cancel_watcher, daemon=True).start()

        last_edit = [0.0]

        def progress(done, total, speed):
            now = time.time()
            if now - last_edit[0] < 3:
                return
            last_edit[0] = now
            pct = f" {done * 100 // total}%" if total else ""
            spd = f" • {speed / 1e6:.1f} MB/s" if speed else ""
            eta = ""
            if total and speed:
                eta_s = int((total - done) / speed)
                eta = f" • ⏳ {ar_num(eta_s)}s"
            txt = f"⬇️ {t(lang, 'downloading')}{pct}{spd}{eta}"
            asyncio.run_coroutine_threadsafe(
                _safe_edit(bot, chat_id, status_msg_id, txt,
                           kb.progress_kb(task.id, lang)), loop)

        try:
            res = await asyncio.to_thread(
                engine.download, url, workdir,
                kind=kind, quality=quality, audio_fmt=audio_fmt,
                cancel=cancel, progress=progress)
        except engine.Cancelled:
            await _safe_edit(bot, chat_id, status_msg_id, t(lang, "cancelled"))
            db.log_download(user_id, url, detect_platform(url), kind, None, "cancelled")
            engine.cleanup(workdir)
            return None
        except engine.DownloadError as e:
            await _safe_edit(bot, chat_id, status_msg_id,
                             t(lang, f"err_{e.key}"), kb.result_kb(url, lang, failed=True))
            db.log_download(user_id, url, detect_platform(url), kind, None, "failed", e.key)
            pending[user_id] = {"kind": "retry", "url": url, "dl_kind": kind,
                                "quality": quality, "audio_fmt": audio_fmt}
            engine.cleanup(workdir)
            return None

        await _safe_edit(bot, chat_id, status_msg_id, t(lang, "uploading"))
        try:
            await bot.send_chat_action(chat_id, ChatAction.UPLOAD_VIDEO if res.is_video
                                       else ChatAction.UPLOAD_VOICE)
            sent_any = False
            for i, path in enumerate(res.paths):
                caption = f"🎬 {res.title}" if i == 0 else None
                if len(res.paths) > 1:
                    caption = (caption or "") + f" ({i+1}/{len(res.paths)})"
                await _send_file(bot, chat_id, path, res, caption)
                sent_any = True
            if sent_any:
                last_file[user_id] = (res.paths[0], res.is_video)
                db.log_download(user_id, url, res.platform, kind, res.title, "ok",
                                nbytes=sum(os.path.getsize(p) for p in res.paths))
                await _safe_edit(bot, chat_id, status_msg_id,
                                 f"✅ {res.title}", kb.result_kb(url, lang))
                pending.setdefault(user_id, {})
                pending[user_id].update({"kind": "done", "url": url})
            return res
        except Exception:
            log.exception("send failed")
            await _safe_edit(bot, chat_id, status_msg_id, t(lang, "err_failed"),
                             kb.result_kb(url, lang, failed=True))
            db.log_download(user_id, url, res.platform, kind, res.title, "failed", "send")
            return None
        finally:
            # keep the first file briefly for tools; remove the rest
            for p in res.paths[1:]:
                engine.cleanup(p)

    label = f"{kind}:{url[:60]}"
    task = queue.submit(job, label, user_id)
    await _safe_edit(bot, chat_id, status_msg_id,
                     t(lang, "queued"), kb.progress_kb(task.id, lang))
    return task


async def _send_file(bot, chat_id, path, res, caption):
    with open(path, "rb") as f:
        if res.is_video:
            w, h, dur = None, None, None
            try:
                info = probe_media(path)
                vs = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
                if vs:
                    w, h = vs[0].get("width"), vs[0].get("height")
                dur = float(info["format"]["duration"])
            except Exception:
                pass
            await bot.send_video(chat_id, f, caption=caption, width=w, height=h,
                                 duration=int(dur) if dur else None,
                                 supports_streaming=True,
                                 read_timeout=300, write_timeout=300)
        else:
            await bot.send_audio(chat_id, f, caption=caption, title=res.title[:64],
                                 read_timeout=300, write_timeout=300)


async def _safe_edit(bot, chat_id, msg_id, text, markup=None):
    try:
        await bot.edit_message_text(text, chat_id, msg_id, reply_markup=markup,
                                    parse_mode="HTML")
    except Exception:
        pass
