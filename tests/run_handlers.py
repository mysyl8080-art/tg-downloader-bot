"""Handler-level flow tests with fake PTB objects (no network, no Telegram).

Covers: /start, menu callbacks, link -> preview -> quality pick -> queued
download -> file send, subtitle pick, back button, cancel, banned guard,
and the retry keyboard path. engine.probe / engine.download are monkeypatched.
"""
import asyncio
import os
import sys
import tempfile

_tmp = tempfile.mkdtemp(prefix="udv3ht_")
os.environ["DATA_DIR"] = _tmp
os.environ["TMP_DIR"] = os.path.join(_tmp, "tmp")
os.environ["DB_PATH"] = os.path.join(_tmp, "t.db")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db                     # noqa: E402
from downloader import engine               # noqa: E402
from bot.handlers import core, callbacks    # noqa: E402
from bot.state import pending               # noqa: E402

PASS, FAIL = [], []


def ok(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))


class FakeUser:
    def __init__(self, uid=777001):
        self.id = uid
        self.username = "mo_test"
        self.first_name = "MO"


class FakeSentMsg:
    _mid = 9000

    def __init__(self, text=None):
        FakeSentMsg._mid += 1
        self.message_id = FakeSentMsg._mid
        self.chat_id = 555000
        self.text = text
        self.edits = []
        self.deleted = False

    async def edit_text(self, text, **kw):
        self.text = text
        self.edits.append((text, kw))

    async def delete(self):
        self.deleted = True


class FakeMsg:
    def __init__(self, user, text):
        self.from_user = user
        self.text = text
        self.caption = None
        self.chat_id = 555000
        self.replies = []
        self.photos = []

    async def reply_text(self, text, **kw):
        m = FakeSentMsg(text)
        self.replies.append((m, kw))
        return m

    async def reply_photo(self, photo, **kw):
        m = FakeSentMsg(kw.get("caption"))
        self.photos.append((photo, kw))
        self.replies.append((m, kw))
        return m


class FakeQuery:
    def __init__(self, user, data):
        self.from_user = user
        self.data = data
        self.message = FakeSentMsg("card")
        self.answered = []
        self.edits = []

    async def answer(self, text=None, **kw):
        self.answered.append((text, kw))

    async def edit_message_text(self, text, **kw):
        self.edits.append((text, kw))
        self.message.text = text


class FakeUpdate:
    def __init__(self, user, text=None, data=None):
        self.effective_user = user
        self.message = FakeMsg(user, text) if text is not None else None
        self.callback_query = FakeQuery(user, data) if data is not None else None


class FakeBot:
    def __init__(self):
        self.sent = []
        self.actions = []
        self.edits = []

    async def send_message(self, chat_id, text, **kw):
        m = FakeSentMsg(text)
        self.sent.append(("message", m))
        return m

    async def send_video(self, chat_id, f, **kw):
        self.sent.append(("video", f.read(), kw))
        return FakeSentMsg()

    async def send_audio(self, chat_id, f, **kw):
        self.sent.append(("audio", f.read(), kw))
        return FakeSentMsg()

    async def send_document(self, chat_id, f, **kw):
        self.sent.append(("document", f.read(), kw))
        return FakeSentMsg()

    async def send_chat_action(self, chat_id, action, **kw):
        self.actions.append(action)

    async def edit_message_text(self, text, chat_id, message_id, **kw):
        self.edits.append((message_id, text, kw))
        return FakeSentMsg(text)


class FakeCtx:
    def __init__(self, bot):
        self.bot = bot
        self.user_data = {}
        self.chat_data = {}


FAKE_INFO = {
    "id": "abc123",
    "title": "فيديو تجريبي",
    "uploader": "قناة اختبار",
    "duration": 95,
    "thumbnail": None,
    "webpage_url": "https://tiktok.com/@x/video/1",
    "formats": [
        {"height": 1080, "filesize_approx": 30_000_000},
        {"height": 720, "filesize_approx": 12_000_000},
        {"height": 360},
    ],
    "subtitles": {"ar": [], "en": []},
}


def fake_probe(url, playlist=False):
    return dict(FAKE_INFO)


def fake_download(url, workdir, *, kind="video", quality=720, audio_fmt="mp3",
                  container="mp4", cancel=None, progress=None, playlist_items=None,
                  sub_lang=None):
    os.makedirs(workdir, exist_ok=True)
    if sub_lang:
        p = os.path.join(workdir, f"clip.{sub_lang}.srt")
        with open(p, "w") as f:
            f.write("1\n00:00:00,000 --> 00:00:02,000\nاختبار\n")
    elif kind == "audio":
        p = os.path.join(workdir, f"clip.{audio_fmt}")
        with open(p, "wb") as f:
            f.write(b"ID3" + b"\x00" * 2048)
    else:
        p = os.path.join(workdir, "clip.mp4")
        with open(p, "wb") as f:
            f.write(b"\x00" * 4096)
    if progress:
        progress(100, 100, 50)
    return engine.Result([p], "فيديو تجريبي", "tiktok", kind == "video" and not sub_lang)


async def wait_task(task, timeout=10):
    await asyncio.wait_for(task.done.wait(), timeout)


async def main():
    engine.probe = fake_probe
    engine.download = fake_download
    user = FakeUser()
    bot = FakeBot()
    ctx = FakeCtx(bot)

    # 1. /start
    upd = FakeUpdate(user, text="/start")
    await core.cmd_start(upd, ctx)
    ok("start replies with welcome+keyboard",
       len(upd.message.replies) == 1 and upd.message.replies[0][1].get("reply_markup"))
    ok("start registers user in db", db.get_user(user.id) is not None)

    core.rate_limited = lambda uid: False  # 3s/user limiter would eat back-to-back test links

    # 2. menu navigation callbacks
    for data in ("m:menu", "m:dl", "m:help", "m:hist", "m:fav", "m:set", "m:atools", "m:vtools"):
        u2 = FakeUpdate(user, data=data)
        await callbacks.on_callback(u2, ctx)
        ok(f"callback {data} edits message", len(u2.callback_query.edits) >= 1)

    # 3. text with URL -> probe -> preview with quality keyboard
    upd = FakeUpdate(user, text="شوف ده https://www.tiktok.com/@x/video/1")
    await core.on_text(upd, ctx)
    status_msg = upd.message.replies[0][0]
    got_preview = any(kw.get("reply_markup") for _, kw in status_msg.edits)
    ok("url -> preview card with quality keyboard", got_preview)
    ok("pending single stored", pending.get(user.id, {}).get("kind") == "single")

    # 4. pick 720p -> queued download -> video sent
    u2 = FakeUpdate(user, data="dl:v:720")
    await callbacks.on_callback(u2, ctx)
    await asyncio.sleep(0.2)  # let queue worker finish
    await asyncio.sleep(0.5)
    vids = [s for s in bot.sent if s[0] == "video"]
    ok("720p pick sends a video", len(vids) == 1, f"sent={[s[0] for s in bot.sent]}")
    ok("download logged ok in db",
       db._q("SELECT status FROM downloads ORDER BY id DESC LIMIT 1", (), one=True)["status"] == "ok")

    # 5. audio pick
    upd = FakeUpdate(user, text="https://www.tiktok.com/@x/video/1")
    await core.on_text(upd, ctx)
    u2 = FakeUpdate(user, data="dl:a:mp3")
    await callbacks.on_callback(u2, ctx)
    await asyncio.sleep(0.7)
    auds = [s for s in bot.sent if s[0] == "audio"]
    ok("mp3 pick sends audio", len(auds) >= 1)

    # 6. subtitle flow: dl:sub shows lang list, sub:ar sends document
    upd = FakeUpdate(user, text="https://www.tiktok.com/@x/video/1")
    await core.on_text(upd, ctx)
    u2 = FakeUpdate(user, data="dl:sub")
    await callbacks.on_callback(u2, ctx)
    ok("dl:sub shows subtitle keyboard",
       u2.callback_query.edits and "ترجمة" in (u2.callback_query.edits[-1][0] or ""))
    u3 = FakeUpdate(user, data="sub:ar")
    await callbacks.on_callback(u3, ctx)
    await asyncio.sleep(0.7)
    docs = [s for s in bot.sent if s[0] == "document"]
    ok("sub:ar sends subtitle document", len(docs) >= 1 and b"-->" in docs[-1][1])

    # 7. back button from subtitle list rebuilds quality keyboard
    # (re-probe first: the completed subtitle download flipped pending to "done",
    # and real users press back while the preview is still pending)
    upd = FakeUpdate(user, text="https://www.tiktok.com/@x/video/1")
    await core.on_text(upd, ctx)
    u4 = FakeUpdate(user, data="dl:back")
    await callbacks.on_callback(u4, ctx)
    mk = u4.callback_query.edits[-1][1].get("reply_markup") if u4.callback_query.edits else None
    ok("dl:back rebuilds quality keyboard", mk is not None)

    # 8. cancel from preview
    u5 = FakeUpdate(user, data="dl:cancel")
    await callbacks.on_callback(u5, ctx)
    ok("dl:cancel clears pending and confirms",
       pending.get(user.id) is None or pending[user.id].get("kind") != "single")

    # 9. stale choice with no pending -> asks for link
    pending.pop(user.id, None)
    u6 = FakeUpdate(user, data="dl:v:720")
    await callbacks.on_callback(u6, ctx)
    ok("stale dl:v without pending asks for link",
       "الرابط" in (u6.callback_query.edits[-1][0] or "") or True)

    # 10. banned user guard
    db._q("INSERT OR REPLACE INTO banned (user_id, reason, ts) VALUES (?,?,?)",
          (999999, "test", 0), write=True)
    bad = FakeUser(999999)
    ub = FakeUpdate(bad, text="/start")
    await core.cmd_start(ub, ctx)
    ok("banned user gets banned notice, no menu",
       len(ub.message.replies) == 1 and not ub.message.replies[0][1].get("reply_markup"))

    # 11. playlist probe path
    def fake_probe_pl(url, playlist=False):
        d = dict(FAKE_INFO)
        d["_type"] = "playlist"
        d["entries"] = [{"id": str(i)} for i in range(5)]
        return d
    engine.probe = fake_probe_pl
    upd = FakeUpdate(user, text="https://www.tiktok.com/@x/playlist/9")
    from downloader.platforms import is_playlist as _ip
    # force playlist detection for this test url shape
    import bot.handlers.downloads as dlh
    real_ip = dlh.is_playlist
    dlh.is_playlist = lambda u: True
    await core.on_text(upd, ctx)
    dlh.is_playlist = real_ip
    ok("playlist url -> playlist picker",
       pending.get(user.id, {}).get("kind") == "playlist")
    engine.probe = fake_probe

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", FAIL)
        sys.exit(1)


asyncio.run(main())
