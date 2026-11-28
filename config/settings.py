"""Central configuration. Every value comes from the environment; see .env.example."""
import os

# --- required ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# --- access control ---
ADMIN_IDS = {int(x) for x in os.environ.get("ADMIN_IDS", "").replace(" ", "").split(",") if x}

# --- limits ---
MAX_FILE_BYTES = int(os.environ.get("MAX_FILE_MB", "1900")) * 1024 * 1024  # hard abort download
SEND_BYTES = int(os.environ.get("SEND_MB", "49")) * 1024 * 1024           # Telegram bot upload cap
SPLIT_BYTES = 44 * 1024 * 1024                                            # part size when splitting
PLAYLIST_MAX = int(os.environ.get("PLAYLIST_MAX", "20"))
MULTI_URL_MAX = int(os.environ.get("MULTI_URL_MAX", "5"))
MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT", "2"))
RATE_LIMIT_SECONDS = float(os.environ.get("RATE_LIMIT_SECONDS", "3"))
DOWNLOAD_TIMEOUT = int(os.environ.get("DOWNLOAD_TIMEOUT", "1800"))

# --- optional integrations ---
PROXY_URL = os.environ.get("PROXY_URL") or None
YT_COOKIES = os.environ.get("YT_COOKIES") or None        # path to cookies.txt inside the container
REDIS_URL = os.environ.get("REDIS_URL") or None          # reserved; in-process queue is the default
SENTRY_DSN = os.environ.get("SENTRY_DSN") or None

# --- storage ---
DATA_DIR = os.environ.get("DATA_DIR", "/tmp/udv3")
DB_PATH = os.environ.get("DB_PATH", os.path.join(DATA_DIR, "udv3.db"))
TMP_DIR = os.environ.get("TMP_DIR", os.path.join(DATA_DIR, "tmp"))

# --- runtime ---
HEALTH_PORT = int(os.environ.get("HEALTH_PORT", "8080"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(TMP_DIR, exist_ok=True)
