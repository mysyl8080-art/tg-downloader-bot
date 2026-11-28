"""Shared runtime state (module singletons)."""
import time

from services.queue import Queue
from config import settings

queue = Queue(settings.MAX_CONCURRENT)
maintenance = False
_last_action = {}          # user_id -> ts (rate limiting)
last_file = {}             # user_id -> (path, is_video)
pending = {}               # user_id -> dict (pending URL/preview/tool input)
_tasks_by_msg = {}         # (chat_id, message_id) -> task_id


def rate_limited(user_id):
    now = time.time()
    last = _last_action.get(user_id, 0)
    _last_action[user_id] = now
    return now - last < settings.RATE_LIMIT_SECONDS
