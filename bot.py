"""Telegram link-downloader bot: send any link, get the file back."""
import asyncio, logging, os, re, threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from downloader import DownloadError, cleanup, download_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot")

BOT_TOKEN = os.environ["BOT_TOKEN"]
MAX_TG_BYTES = 49 * 1024 * 1024  # Bot API upload cap
_sem = asyncio.Semaphore(2)
URL_RE = re.compile(r"https?://[^\s<>\"]+", re.I)

HELP = (
    "أرسل لي أي رابط وسأحمّله وأرسله لك هنا.\n\n"
    "• فيديو من يوتيوب، تيك توك، إنستغرام، تويتر/X، فيسبوك ومئات المواقع\n"
    "• أو رابط ملف مباشر (PDF, ZIP, صور...)\n\n"
    "الحد الأقصى 49 ميجا (حد تيليجرام للبوتات)."
)

def extract_url(text: str):
    m = URL_RE.search(text or "")
    return m.group(0) if m else None

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP)

async def handle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    text = msg.text or msg.caption or ""
    url = extract_url(text)
    if not url:
        await msg.reply_text("أرسل رابطًا يبدأ بـ http أو https وسأحمّله لك.")
        return
    audio_only = any(w in text for w in ("صوت", "mp3", "MP3", "audio"))
    status = await msg.reply_text("⏳ جارٍ التحميل" + (" (صوت فقط)..." if audio_only else "..."))
    async with _sem:
        await ctx.bot.send_chat_action(msg.chat_id, ChatAction.UPLOAD_DOCUMENT)
        result = None
        try:
            result = await asyncio.to_thread(download_url, url, audio_only)
        except DownloadError as e:
            await status.edit_text(f"❌ {e}")
            return
        except Exception:
            log.exception("download failed")
            await status.edit_text("❌ حدث خطأ غير متوقع أثناء التحميل.")
            return
    try:
        size = os.path.getsize(result.path)
        if size > MAX_TG_BYTES:
            await status.edit_text(
                f"❌ الملف كبير ({size/1024/1024:.0f} ميجا). الحد الأقصى للبوتات 49 ميجا.")
            return
        await status.edit_text("📤 جارٍ الإرسال...")
        title = result.title or "file"
        with open(result.path, "rb") as f:
            if result.path.lower().endswith((".mp3", ".m4a", ".ogg", ".wav", ".opus")):
                await msg.reply_audio(f, caption=title[:1000], title=title[:64],
                                      read_timeout=300, write_timeout=300)
            elif result.is_video:
                await msg.reply_video(f, caption=title[:1000], supports_streaming=True,
                                      read_timeout=300, write_timeout=300)
            else:
                await msg.reply_document(f, caption=title[:1000],
                                         read_timeout=300, write_timeout=300)
        await status.delete()
    except Exception:
        log.exception("send failed")
        await status.edit_text("❌ تم التحميل لكن فشل الإرسال (ربما الملف كبير جدًا).")
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
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler(["start", "help"], cmd_start))
    app.add_handler(MessageHandler(filters.TEXT | filters.CAPTION, handle))
    url = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("PUBLIC_URL")
    if url:
        # webhook mode (free web hosts sleep when idle; Telegram retries delivery)
        port = int(os.environ.get("PORT", "8080"))
        secret = os.environ.get("WEBHOOK_SECRET", BOT_TOKEN.split(":")[-1][:24])
        log.info("bot starting (webhook %s)", url)
        app.run_webhook(listen="0.0.0.0", port=port, url_path="tg", webhook_url=url.rstrip("/") + "/tg",
                        secret_token=secret, allowed_updates=["message"])
    else:
        log.info("bot starting (long polling)")
        app.run_polling(drop_pending_updates=True, allowed_updates=["message"])

if __name__ == "__main__":
    main()
