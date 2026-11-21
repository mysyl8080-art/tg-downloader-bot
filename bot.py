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
    status = await msg.reply_text("⏳ جارٍ التحميل...")
    async with _sem:
        await ctx.bot.send_chat_action(msg.chat_id, ChatAction.UPLOAD_DOCUMENT)
        result = None
        try:
            result = await asyncio.to_thread(download_url, url)
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
            if result.is_video:
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
    threading.Thread(target=run_health_server, daemon=True).start()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler(["start", "help"], cmd_start))
    app.add_handler(MessageHandler(filters.TEXT | filters.CAPTION, handle))
    log.info("bot starting (long polling)")
    app.run_polling(drop_pending_updates=True, allowed_updates=["message"])

if __name__ == "__main__":
    main()
