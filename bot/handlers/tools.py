"""Audio/video tools: operate on the last downloaded or uploaded file."""
import asyncio
import logging
import os

from config import settings
from media import audio as ma, video as mv, thumbnails as mt
from media.ffmpeg_base import MediaError, probe_media
from downloader import engine
from ..state import last_file, pending
from ..text import t

log = logging.getLogger("udv3.tools")


def _target(uid, is_video):
    f = last_file.get(uid)
    if not f or not os.path.exists(f[0]):
        return None
    return f


async def on_tool(q, ctx, uid, lang, data):
    domain, _, action = data.partition(":")
    _, _, action = action.partition(":")
    tgt = _target(uid, domain == "vt")
    if not tgt:
        await q.answer(t(lang, "tools_need_file"), show_alert=True)
        return
    path, is_video = tgt

    # actions needing text input -> park state and ask
    if action in ("trim",):
        pending[uid] = {"await_input": f"{domain}:trim", "path": path, "is_video": is_video}
        await q.message.reply_text(t(lang, "ask_trim"), parse_mode="HTML")
        return
    if action == "vol":
        pending[uid] = {"await_input": "at:vol", "path": path}
        await q.message.reply_text(t(lang, "ask_volume"))
        return
    if action == "speed":
        pending[uid] = {"await_input": "vt:speed", "path": path}
        await q.message.reply_text(t(lang, "ask_speed"))
        return
    if action == "gif":
        pending[uid] = {"await_input": "vt:gif", "path": path}
        await q.message.reply_text(t(lang, "ask_gif"), parse_mode="HTML")
        return
    if action == "merge":
        pending[uid] = {"await_input": "vt:merge", "path": path}
        await q.message.reply_text("أرسل رابط أو ملف الصوت المراد دمجه:")
        return

    await q.message.reply_text(t(lang, "working"))
    try:
        if domain == "at":
            out = await _audio_action(action, path, uid)
        else:
            out = await _video_action(action, path, uid)
    except MediaError as e:
        await q.message.reply_text(t(lang, f"err_{e.key}") if e.key in
                                   ("timeout", "failed", "badtime") else t(lang, "err_failed"))
        return
    except Exception:
        log.exception("tool failed")
        await q.message.reply_text(t(lang, "err_failed"))
        return
    if out:
        await _send_result(q, out, is_video_result=(domain == "vt" and action != "shot"
                                                    and action != "meta"))


async def _audio_action(action, path, uid):
    workdir = os.path.join(settings.TMP_DIR, f"tool_{uid}")
    if action == "extract":
        return await asyncio.to_thread(ma.extract_audio, path, workdir, "mp3")
    if action == "comp":
        return await asyncio.to_thread(ma.compress_audio, path, workdir)
    if action == "voice":
        return await asyncio.to_thread(ma.to_voice, path, workdir)
    return None


async def _video_action(action, path, uid):
    workdir = os.path.join(settings.TMP_DIR, f"tool_{uid}")
    if action == "comp":
        return await asyncio.to_thread(mv.compress, path, workdir)
    if action == "mute":
        return await asyncio.to_thread(mv.remove_audio, path, workdir)
    if action == "mkv":
        return await asyncio.to_thread(mv.convert, path, workdir, "mkv")
    if action == "shot":
        out = await asyncio.to_thread(mt.thumbnail, path, workdir)
        return out
    if action == "meta":
        info = await asyncio.to_thread(probe_media, path)
        fmt = info.get("format", {})
        streams = info.get("streams", [])
        lines = [f"⏱ {float(fmt.get('duration', 0)):.1f}s",
                 f"💾 {int(fmt.get('size', 0)) / 1e6:.1f} MB",
                 f"📶 {int(fmt.get('bit_rate', 0)) / 1e3:.0f} kbps"]
        for s in streams:
            if s.get("codec_type") == "video":
                lines.append(f"🎬 {s.get('codec_name')} {s.get('width')}x{s.get('height')}")
            elif s.get("codec_type") == "audio":
                lines.append(f"🎵 {s.get('codec_name')}")
        return "\n".join(lines)
    return None


async def handle_input(msg, ctx, pend, lang):
    """Free-text input for parked tool actions. True if consumed."""
    action = pend.get("await_input")
    path = pend.get("path")
    if not action or not path or not os.path.exists(path):
        pending.pop(msg.from_user.id, None)
        return False
    text = (msg.text or "").strip()
    uid = msg.from_user.id
    workdir = os.path.join(settings.TMP_DIR, f"tool_{uid}")
    try:
        if action.endswith(":trim"):
            parts = text.split()
            start = parts[0]
            end = parts[1] if len(parts) > 1 else None
            fn = mv.trim if action.startswith("vt") else ma.trim
            out = await asyncio.to_thread(fn, path, workdir, start, end)
        elif action == "at:vol":
            out = await asyncio.to_thread(ma.volume, path, workdir, float(text))
        elif action == "vt:speed":
            out = await asyncio.to_thread(mv.change_speed, path, workdir, float(text))
        elif action == "vt:gif":
            parts = text.split()
            start = float(parts[0]) if parts and parts[0] != "go" else 0.0
            dur = float(parts[1]) if len(parts) > 1 else 5.0
            out = await asyncio.to_thread(mv.to_gif, path, workdir, start, dur)
        elif action == "vt:merge":
            from downloader.platforms import extract_urls
            urls = extract_urls(text)
            if not urls:
                await msg.reply_text("أرسل رابط ملف الصوت:")
                return True
            from downloader import engine as eng
            adir = os.path.join(workdir, "merge_src")
            res = await asyncio.to_thread(eng.download, urls[0], adir, kind="audio")
            out = await asyncio.to_thread(mv.merge_audio_video, path, res.paths[0], workdir)
        else:
            return False
    except (MediaError, ValueError):
        await msg.reply_text(t(lang, "err_badtime"))
        return True
    except Exception:
        log.exception("tool input failed")
        await msg.reply_text(t(lang, "err_failed"))
        pending.pop(uid, None)
        return True
    pending.pop(uid, None)
    await _send_result_msg(msg, out, is_video_result=action.startswith("vt")
                           and not action.endswith("gif"))
    return True


async def _send_result(q_or_msg, out, is_video_result):
    msg = q_or_msg.message if hasattr(q_or_msg, "message") else q_or_msg
    await _send_result_msg(msg, out, is_video_result)


async def _send_result_msg(msg, out, is_video_result):
    if out is None:
        return
    if isinstance(out, str) and "\n" in out and not os.path.exists(out):
        await msg.reply_text(f"ℹ️\n{out}")
        return
    try:
        with open(out, "rb") as f:
            if out.endswith((".jpg", ".png")):
                await msg.reply_photo(f)
            elif out.endswith(".gif"):
                await msg.reply_animation(f)
            elif out.endswith(".ogg"):
                await msg.reply_voice(f)
            elif is_video_result:
                await msg.reply_video(f, supports_streaming=True,
                                      read_timeout=300, write_timeout=300)
            else:
                await msg.reply_audio(f, read_timeout=300, write_timeout=300)
    finally:
        engine.cleanup(out)
