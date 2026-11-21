"""Telegram link-downloader bot: send any link, get the file back."""
import asyncio, logging, os, re, threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, Update, WebAppInfo
from telegram.constants import ChatAction
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from downloader import DownloadError, cleanup, download_url, split_file, TG_LIMIT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

BOT_TOKEN = os.environ["BOT_TOKEN"]
MAX_TG_BYTES = 49 * 1024 * 1024  # Bot API upload cap
_sem = asyncio.Semaphore(2)
URL_RE = re.compile(r"https?://[^\s<>\"]+", re.I)

HELP = (
    "أرسل لي أي رابط وسأحمّله وأرسله لك هنا.\n\n"
    "• فيديو من يوتيوب، تيك توك، إنستغرام، تويتر/X، فيسبوك ومئات المواقع\n"
    "• أو رابط ملف مباشر (PDF, ZIP, صور...)\n\n"
    "بعد إرسال الرابط اختر فيديو (360/480/720/1080) أو MP3 (128/192/320).\nالحد الأقصى 49 ميجا (حد تيليجرام للبوتات)."
)

def extract_url(text: str):
    m = URL_RE.search(text or "")
    return m.group(0) if m else None

MUSHAF_URL = os.environ.get("MUSHAF_URL", "https://almushaf.surge.sh/")

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("📖 افتح المصحف", web_app=WebAppInfo(url=MUSHAF_URL))]])
    await update.message.reply_text(HELP, reply_markup=kb)

async def post_init(app):
    try:
        await app.bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="افتح المصحف", web_app=WebAppInfo(url=MUSHAF_URL)))
    except Exception:
        log.exception("set menu button failed")

import uuid

def menu_kb(key):
    rows = [
        [InlineKeyboardButton("🎬 360p", callback_data=f"v|360|{key}"),
         InlineKeyboardButton("🎬 480p", callback_data=f"v|480|{key}")],
        [InlineKeyboardButton("🎬 720p", callback_data=f"v|720|{key}"),
         InlineKeyboardButton("🎬 1080p", callback_data=f"v|1080|{key}")],
        [InlineKeyboardButton("🎵 MP3 128", callback_data=f"a|128|{key}"),
         InlineKeyboardButton("🎵 MP3 192", callback_data=f"a|192|{key}"),
         InlineKeyboardButton("🎵 MP3 320", callback_data=f"a|320|{key}")],
        [InlineKeyboardButton("📎 ملف مباشر (رابط ملف)", callback_data=f"d|0|{key}")],
    ]
    return InlineKeyboardMarkup(rows)

async def handle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    text = msg.text or msg.caption or ""
    url = extract_url(text)
    if not url:
        await msg.reply_text("أرسل رابطًا يبدأ بـ http أو https وسأحمّله لك.")
        return
    key = uuid.uuid4().hex[:10]
    ctx.bot_data[key] = url
    if len(ctx.bot_data) > 500:
        for k in list(ctx.bot_data)[:100]:
            ctx.bot_data.pop(k, None)
    await msg.reply_text("اختر الصيغة والجودة:", reply_markup=menu_kb(key), reply_to_message_id=msg.message_id)

async def on_choice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        kind, qual, key = q.data.split("|")
    except ValueError:
        return
    url = ctx.bot_data.get(key)
    if not url:
        await q.edit_message_text("انتهت صلاحية الزر. أرسل الرابط مرة أخرى.")
        return
    msg = q.message
    label = {"v": f"فيديو {qual}p", "a": f"MP3 {qual}", "d": "ملف مباشر"}[kind]
    await q.edit_message_text(f"⏳ جارٍ التحميل ({label})...")
    status = msg
    async with _sem:
        await ctx.bot.send_chat_action(msg.chat_id, ChatAction.UPLOAD_DOCUMENT)
        result = None
        try:
            result = await asyncio.to_thread(download_url, url, kind == "a", int(qual) or None, kind == "d")
        except DownloadError as e:
            if str(e) == "TOOBIG":
                await status.edit_text("❌ الملف أكبر من 49 ميجا (حد تيليجرام للبوتات). اختر جودة أقل أو MP3.",
                                       reply_markup=menu_kb(key))
            else:
                await status.edit_text(f"❌ {e}")
            return
        except Exception:
            log.exception("download failed")
            await status.edit_text("❌ حدث خطأ غير متوقع أثناء التحميل.")
            return
    try:
        size = os.path.getsize(result.path)
        title = result.title or "file"
        is_media = result.path.lower().endswith((".mp3", ".m4a", ".ogg", ".wav", ".opus", ".mp4", ".mkv", ".webm", ".mov"))
        if size > MAX_TG_BYTES:
            await status.edit_text(f"✂️ الملف كبير ({size/1024/1024:.0f} ميجا). سأقسمه إلى أجزاء وأرسلها...")
            try:
                parts = await asyncio.to_thread(split_file, result.path)
            except Exception:
                log.exception("split failed")
                await status.edit_text("❌ فشل تقسيم الملف. اختر جودة أقل.", reply_markup=menu_kb(key))
                return
        else:
            parts = [result.path]
        n = len(parts)
        for i, p in enumerate(parts, 1):
            await status.edit_text(f"📤 جارٍ الإرسال... ({i}/{n})" if n > 1 else "📤 جارٍ الإرسال...")
            cap = (title if n == 1 else f"{title}\nجزء {i}/{n}")[:1000]
            low = p.lower()
            with open(p, "rb") as f:
                if low.endswith((".mp3", ".m4a", ".ogg", ".wav", ".opus")):
                    await ctx.bot.send_audio(msg.chat_id, f, caption=cap, title=title[:64],
                                             read_timeout=300, write_timeout=300)
                elif low.endswith((".mp4", ".mkv", ".webm", ".mov")):
                    await ctx.bot.send_video(msg.chat_id, f, caption=cap, supports_streaming=True,
                                             read_timeout=300, write_timeout=300)
                else:
                    await ctx.bot.send_document(msg.chat_id, f, caption=cap,
                                                read_timeout=300, write_timeout=300)
        if n > 1 and not is_media:
            await ctx.bot.send_message(msg.chat_id,
                "ℹ️ هذا ملف مقسّم. لدمج الأجزاء: على ويندوز افتح CMD وشغّل: copy /b *.001 الاسم_الأصلي — "
                "وعلى الأندرويد/لينكس: cat *.0* > الاسم_الأصلي")
        elif n > 1:
            await ctx.bot.send_message(msg.chat_id, f"ℹ️ تم تقسيمه إلى {n} أجزاء، كل جزء يعمل لوحده بالترتيب.")
        await status.delete()
    except Exception:
        log.exception("send failed")
        await status.edit_text("❌ تم التحميل لكن فشل الإرسال.")
    finally:
        cleanup(result)

def run_health_server():
    port = int(os.environ.get("PORT", "8080"))
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
        def log_message(self, *a): pass
    HTTPServer(("0.0.0.0", port), H).serve_forever()

def main():
    if not (os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("PUBLIC_URL")):
        threading.Thread(target=run_health_server, daemon=True).start()
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler(["start", "help"], cmd_start))
    app.add_handler(MessageHandler(filters.TEXT | filters.CAPTION, handle))
    app.add_handler(CallbackQueryHandler(on_choice))
    url = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("PUBLIC_URL")
    if url:
        # webhook mode (free web hosts sleep when idle; Telegram retries delivery)
        port = int(os.environ.get("PORT", "8080"))
        secret = os.environ.get("WEBHOOK_SECRET", BOT_TOKEN.split(":")[-1][:24])
        log.info("bot starting (webhook %s) PORT=%s", url, os.environ.get("PORT"))
        def selfcheck():
            import time, socket, urllib.request
            time.sleep(8)
            try:
                s_ = socket.create_connection(("127.0.0.1", port), 3); s_.close(); log.info("selfcheck: port %s open", port)
            except Exception as e:
                log.info("selfcheck: port %s closed: %s", port, e)
            try:
                r = urllib.request.urlopen("http://127.0.0.1:%s/tg" % port, timeout=5)
                log.info("selfcheck GET /tg %s", r.status)
            except Exception as e:
                log.info("selfcheck GET /tg: %s", e)
        threading.Thread(target=selfcheck, daemon=True).start()
        app.run_webhook(listen="0.0.0.0", port=port, url_path="tg", webhook_url=url.rstrip("/") + "/tg",
                        secret_token=secret, allowed_updates=["message", "callback_query"])
    else:
        log.info("bot starting (long polling)")
        app.run_polling(drop_pending_updates=True, allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    main()
