"""Ultimate Downloader Bot V3 — entry point."""
import os
# Limit native thread pools on small containers (reference: video-downloader-music-remover).
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import asyncio
import logging
import signal
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from config import settings

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("udv3")
# httpx logs request URLs containing the bot token at INFO level.
logging.getLogger("httpx").setLevel(logging.WARNING)

if settings.SENTRY_DSN:
    try:
        import sentry_sdk
        sentry_sdk.init(settings.SENTRY_DSN, traces_sample_rate=0.1)
        log.info("sentry enabled")
    except Exception:
        log.exception("sentry init failed")


def run_health_server():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *a):
            pass

    srv = HTTPServer(("0.0.0.0", settings.HEALTH_PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log.info("health server on :%s", settings.HEALTH_PORT)


def _reaper(app):
    async def loop():
        while True:
            await asyncio.sleep(1800)
            from bot.state import queue
            queue.reap()
            from services.cleanup import sweep_tmp
            sweep_tmp()
    return loop


def main():
    if not settings.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is required")

    from bot.handlers import core, callbacks
    from admin import commands as admin

    app = Application.builder().token(settings.BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", core.cmd_start))
    app.add_handler(CommandHandler("help", core.cmd_start))
    app.add_handler(CommandHandler("admin", admin.cmd_admin))
    app.add_handler(CommandHandler("ban", admin.cmd_ban))
    app.add_handler(CommandHandler("unban", admin.cmd_unban))
    app.add_handler(CommandHandler("broadcast", admin.cmd_broadcast))
    app.add_handler(CommandHandler("maintenance", admin.cmd_maintenance))
    app.add_handler(CallbackQueryHandler(callbacks.on_callback))
    app.add_handler(MessageHandler(filters.TEXT | filters.CAPTION, core.on_text))
    app.add_handler(MessageHandler(filters.VIDEO | filters.AUDIO | filters.VOICE |
                                   filters.VIDEO_NOTE | filters.Document.ALL,
                                   core.on_media))

    async def post_init(application):
        application.create_task(_reaper(application)())

    app.post_init = post_init
    run_health_server()
    log.info("bot starting (long polling)")
    app.run_polling(drop_pending_updates=True,
                    stop_signals=(signal.SIGINT, signal.SIGTERM))


if __name__ == "__main__":
    main()
