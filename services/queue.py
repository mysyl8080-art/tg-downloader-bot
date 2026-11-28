"""In-process asyncio download queue.

Concurrency-capped workers, per-task cancellation, one automatic retry with
backoff. Redis can replace this later via REDIS_URL without touching callers:
submit() returns a Task handle either way.
"""
import asyncio
import itertools
import logging
import time

log = logging.getLogger("udv3.queue")

_ids = itertools.count(1)


class Task:
    def __init__(self, coro_factory, label, user_id, retries=1):
        self.id = next(_ids)
        self.coro_factory = coro_factory   # async callable(task) -> result
        self.label = label
        self.user_id = user_id
        self.retries = retries
        self.cancel_event = asyncio.Event()
        self.done = asyncio.Event()
        self.result = None
        self.error = None
        self.started_at = None

    def cancel(self):
        self.cancel_event.set()

    @property
    def cancelled(self):
        return self.cancel_event.is_set()


class Queue:
    def __init__(self, max_concurrent):
        self._sem = asyncio.Semaphore(max_concurrent)
        self._tasks = {}
        self._running = set()

    def submit(self, coro_factory, label, user_id, retries=1) -> Task:
        t = Task(coro_factory, label, user_id, retries)
        self._tasks[t.id] = t
        asyncio.get_running_loop().create_task(self._run(t))
        return t

    def get(self, task_id):
        return self._tasks.get(task_id)

    def cancel(self, task_id):
        t = self._tasks.get(task_id)
        if t and not t.done.is_set():
            t.cancel()
            return True
        return False

    def active_count(self):
        return len(self._running)

    async def _run(self, t: Task):
        async with self._sem:
            if t.cancelled:
                t.done.set()
                return
            self._running.add(t.id)
            t.started_at = time.time()
            try:
                attempt = 0
                while True:
                    try:
                        t.result = await t.coro_factory(t)
                        return
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:  # retry with backoff
                        t.error = e
                        attempt += 1
                        if t.cancelled or attempt > t.retries:
                            raise
                        wait = min(2 ** attempt * 2, 20)
                        log.info("task %s retry %s in %ss: %s", t.id, attempt, wait, e)
                        try:
                            await asyncio.wait_for(t.cancel_event.wait(), wait)
                        except asyncio.TimeoutError:
                            pass
            except Exception as e:
                t.error = e
                log.warning("task %s failed: %s", t.id, e)
            finally:
                self._running.discard(t.id)
                t.done.set()

    def reap(self, older_than=3600):
        for tid in [k for k, v in self._tasks.items()
                    if v.done.is_set() and v.started_at and time.time() - v.started_at > older_than]:
            self._tasks.pop(tid, None)
