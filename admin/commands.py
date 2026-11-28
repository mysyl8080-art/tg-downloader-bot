"""Admin commands: /admin /ban /unban /broadcast /maintenance /stats."""
import logging
import os
import time

from telegram import Update
from telegram.ext import ContextTypes

from config import settings
from database import db
from bot import state
from bot.text import t
from bot.handlers.core import lang_of

log = logging.getLogger("udv3.admin")


def _is_admin(update):
    return update.effective_user and update.effective_user.id in settings.ADMIN_IDS


def _sys_status():
    try:
        with open("/proc/meminfo") as f:
            mem = f.read()
        total = int(next(l.split()[1] for l in mem.splitlines() if l.startswith("MemTotal"))) // 1024
        avail = int(next(l.split()[1] for l in mem.splitlines() if l.startswith("MemAvailable"))) // 1024
        ram = f"{total - avail}/{total} MB"
    except Exception:
        ram = "?"
    try:
        st = os.statvfs(settings.DATA_DIR)
        disk = f"{(st.f_blocks - st.f_bavail) * st.f_frsize // 2**20}/" \
               f"{st.f_blocks * st.f_frsize // 2**20} MB"
    except Exception:
        disk = "?"
    try:
        with open("/proc/loadavg") as f:
            load = f.read().split()[:3]
        cpu = " ".join(load)
    except Exception:
        cpu = "?"
    return ram, disk, cpu


async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        await update.message.reply_text(t("ar", "admin_only"))
        return
    s = db.stats()
    ram, disk, cpu = _sys_status()
    lines = [
        "📊 <b>لوحة المشرف</b>",
        f"👥 المستخدمون: {s['users']} (نشط ٢٤س: {s['active_24h']})",
        f"⬇️ التحميلات: {s['downloads']} (اليوم: {s['downloads_24h']})",
        f"❌ الفاشلة: {s['failed']}",
        "🏆 المنصات: " + (", ".join(f"{r['platform']}({r['c']})" for r in s["platforms"]) or "—"),
        f"🧠 RAM: {ram} • 💽 Disk: {disk} • ⚙️ Load: {cpu}",
        f"🔧 صيانة: {'مفعّلة' if state.maintenance else 'مطفأة'} • مهام جارية: {state.queue.active_count()}",
        "",
        "/ban &lt;id&gt; • /unban &lt;id&gt; • /broadcast نص • /maintenance on|off",
    ]
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_ban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    try:
        uid = int(ctx.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("استخدم: /ban <user_id>")
        return
    db.ban(uid, " ".join(ctx.args[1:]) or None)
    await update.message.reply_text(f"🚫 حُظر {uid}")


async def cmd_unban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    try:
        uid = int(ctx.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("استخدم: /unban <user_id>")
        return
    db.unban(uid)
    await update.message.reply_text(f"✅ أُلغي حظر {uid}")


async def cmd_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    text = " ".join(ctx.args)
    if not text:
        await update.message.reply_text("استخدم: /broadcast <نص>")
        return
    users = db._q("SELECT user_id FROM users")
    ok = fail = 0
    await update.message.reply_text(f"📢 إرسال إلى {len(users)} مستخدم...")
    for row in users:
        try:
            await ctx.bot.send_message(row["user_id"], text)
            ok += 1
        except Exception:
            fail += 1
    await update.message.reply_text(f"📢 تم: {ok} نجح، {fail} فشل")


async def cmd_maintenance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    arg = (ctx.args[0].lower() if ctx.args else "")
    state.maintenance = arg == "on"
    await update.message.reply_text(f"🔧 وضع الصيانة: {'مفعّل' if state.maintenance else 'مطفأ'}")
