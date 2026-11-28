"""Plain-python test runner: python tests/run_all.py (network tests marked)."""
import os, sys, tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="udv3_test_"))
os.environ["BOT_TOKEN"] = "test"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = FAIL = 0
def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok: {name}")
    else:
        FAIL += 1
        print(f"FAIL: {name}")


# ---------- platforms ----------
from downloader.platforms import extract_urls, detect_platform, is_playlist, safe_filename
print("platforms:")
check("extract_urls multi", extract_urls("شوف https://youtu.be/abc وكمان https://tiktok.com/x. de,") ==
      ["https://youtu.be/abc", "https://tiktok.com/x"])
check("detect youtube", detect_platform("https://www.youtube.com/watch?v=x") == "youtube")
check("detect shorts", detect_platform("https://youtube.com/shorts/xyz") == "youtube")
check("detect tiktok", detect_platform("https://vt.tiktok.com/ZSjkw/") == "tiktok")
check("detect x", detect_platform("https://x.com/u/status/1") == "x")
check("detect direct mp4", detect_platform("https://files.example.com/a/b.mp4?x=1") == "web")
check("detect unknown", detect_platform("https://example.com/page") == "unknown")
check("playlist yt", is_playlist("https://www.youtube.com/playlist?list=PLx"))
check("playlist sc", is_playlist("https://soundcloud.com/u/sets/mix"))
check("not playlist", not is_playlist("https://youtu.be/abc"))
check("safe_filename strips path", safe_filename("../../etc/passwd\nx") == "etcpasswd x" or "/" not in safe_filename("../../etc/passwd"))
check("safe_filename len", len(safe_filename("a" * 500)) <= 120)

# ---------- database ----------
from database import db
print("database:")
class U:  id, username, first_name = 42, "mo", "MO"
db.upsert_user(U)
u = db.get_user(42)
check("upsert user", u and u["username"] == "mo" and u["lang"] == "ar")
db.set_lang(42, "en"); db.set_def_quality(42, 1080); db.set_def_audio(42, "flac")
u = db.get_user(42)
check("settings", u["lang"] == "en" and u["def_quality"] == 1080 and u["def_audio"] == "flac")
did = db.log_download(42, "https://x.y/v", "vimeo", "video", "title1", "ok", nbytes=100)
check("log download", did > 0)
check("history", db.history(42)[0]["title"] == "title1")
db.add_favorite(42, "https://x.y/v", "fav1")
check("favorites", db.favorites(42)[0]["url"] == "https://x.y/v")
db.remove_favorite(42, "https://x.y/v")
check("favorite removed", len(db.favorites(42)) == 0)
db.ban(99, "spam")
check("ban", db.is_banned(99))
db.unban(99)
check("unban", not db.is_banned(99))
s = db.stats()
check("stats", s["users"] >= 1 and s["downloads"] >= 1)

# ---------- queue ----------
import asyncio
from services.queue import Queue
print("queue:")
async def qtest():
    q = Queue(2)
    ran = []
    async def good(task):
        ran.append(task.id)
        return 1
    async def bad(task):
        raise RuntimeError("boom")
    t1 = q.submit(good, "g", 1)
    t2 = q.submit(bad, "b", 1, retries=1)   # one retry then fails
    await asyncio.wait_for(t1.done.wait(), 5)
    await asyncio.wait_for(t2.done.wait(), 15)
    check("queue success", t1.result == 1)
    check("queue failure recorded", isinstance(t2.error, RuntimeError))
    async def slow(task):
        for _ in range(40):
            if task.cancelled:
                raise asyncio.CancelledError()
            await asyncio.sleep(0.05)
    t3 = q.submit(slow, "s", 1, retries=0)
    await asyncio.sleep(0.1)
    check("queue cancel", q.cancel(t3.id))
    await asyncio.wait_for(t3.done.wait(), 10)
    q.reap(older_than=0)
    return True
asyncio.run(qtest())

# ---------- engine (offline) ----------
from downloader import engine
print("engine (offline):")
sel = engine.video_format(720)
check("format selector has height cap", "height<=720" in sel)
bigfile = os.path.join(os.environ["DATA_DIR"], "big.bin")
with open(bigfile, "wb") as f:
    f.write(os.urandom(50 * 1024 * 1024))
engine.settings.SEND_BYTES = 10 * 1024 * 1024
engine.settings.SPLIT_BYTES = 10 * 1024 * 1024
parts = engine.split_if_needed(bigfile)
check("split parts", len(parts) == 5 and all(os.path.getsize(p) <= 10 * 1024 * 1024 for p in parts))
for p in parts: os.remove(p)
e = engine._map_error(Exception("Sign in to confirm you're not a bot"))
check("map blocked", e.key == "blocked")
e = engine._map_error(Exception("HTTP Error 404: Not Found"))
check("map 404", e.key == "gone")
e = engine._map_error(Exception("Unsupported URL: https://example.com"))
check("map unsupported", e.key == "unsupported")

# ---------- media tools (real ffmpeg) ----------
print("media (ffmpeg):")
from media import audio as ma, video as mv, thumbnails as mt
from media.ffmpeg_base import probe_media, duration, has_audio, has_video, parse_time, MediaError
workdir = os.path.join(os.environ["DATA_DIR"], "media")
os.makedirs(workdir, exist_ok=True)
src = os.path.join(workdir, "src.mp4")
os.system(f'ffmpeg -y -v error -f lavfi -i testsrc=duration=6:size=320x240:rate=15 '
          f'-f lavfi -i sine=frequency=440:duration=6 -shortest -c:v libx264 -c:a aac "{src}"')
check("fixture created", os.path.exists(src) and abs(duration(src) - 6) < 0.5)
check("parse_time", parse_time("1:30") == 90 and parse_time("0:01:00") == 60 and parse_time("45") == 45)
try:
    parse_time("abc"); check("parse_time bad raises", False)
except MediaError: check("parse_time bad raises", True)
out = mv.trim(src, workdir, "1", "3"); check("vtrim", abs(duration(out) - 2) < 0.6)
out = ma.extract_audio(src, workdir, "mp3"); check("extract mp3", os.path.getsize(out) > 1000 and not has_video(out))
out = ma.compress_audio(src, workdir, "64k"); check("acompress", os.path.getsize(out) > 500)
out = ma.to_voice(src, workdir); check("voice ogg", out.endswith(".ogg") and os.path.getsize(out) > 500)
out = mv.to_gif(src, workdir, 1, 2); check("gif", os.path.getsize(out) > 1000)
out = mv.remove_audio(src, workdir); check("mute", not has_audio(out))
out = mv.compress(src, workdir, 144); check("vcompress", os.path.getsize(out) < os.path.getsize(src))
out = mv.change_speed(src, workdir, 2.0); check("speed 2x", abs(duration(out) - 3) < 0.7)
out = mv.convert(src, workdir, "mkv"); check("mkv", out.endswith(".mkv") and os.path.getsize(out) > 1000)
out = mt.thumbnail(src, workdir); check("thumbnail", os.path.getsize(out) > 500)
info = probe_media(src); check("probe streams", any(s.get("codec_type") == "video" for s in info["streams"]))
a = os.path.join(workdir, "a.mp3")
out = mv.merge_audio_video(src, ma.extract_audio(src, workdir), workdir)
check("merge av", has_video(out) and has_audio(out))

# ---------- network (real downloads; report-only, no assert on flaky) ----------
print("network (real downloads, may fail by sandbox network):")
NET = os.environ.get("NET_TESTS", "1") == "1"
if NET:
    import threading
    wdir = os.path.join(os.environ["DATA_DIR"], "net")
    try:
        res = engine.download("https://download.samplelib.com/mp4/sample-5s.mp4",
                              wdir, kind="video", quality=720,
                              cancel=threading.Event())
        check("direct mp4 download", os.path.getsize(res.paths[0]) > 10000 and res.is_video)
        info = engine.probe("https://download.samplelib.com/mp4/sample-5s.mp4")
        check("direct probe", True)
    except Exception as ex:
        check(f"direct mp4 download ({ex})", False)
    try:
        res = engine.download("https://download.samplelib.com/mp3/sample-3s.mp3",
                              wdir, kind="audio", audio_fmt="mp3",
                              cancel=threading.Event())
        check("direct mp3 download", os.path.getsize(res.paths[0]) > 1000)
    except Exception as ex:
        check(f"direct mp3 download ({ex})", False)

print(f"\n== {PASS} passed, {FAIL} failed ==")
sys.exit(1 if FAIL else 0)
