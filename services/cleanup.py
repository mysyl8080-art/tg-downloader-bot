"""Tmp hygiene: sweep stale workdirs."""
import os
import time

from config import settings


def sweep_tmp(max_age=3600):
    now = time.time()
    try:
        entries = os.listdir(settings.TMP_DIR)
    except FileNotFoundError:
        return
    for name in entries:
        p = os.path.join(settings.TMP_DIR, name)
        try:
            if now - os.path.getmtime(p) < max_age:
                continue
            if os.path.isdir(p):
                import shutil
                shutil.rmtree(p, ignore_errors=True)
            else:
                os.remove(p)
        except FileNotFoundError:
            pass
