# Telegram link-downloader bot

Send the bot any link; it downloads it and sends the file back.
- Social/media links (TikTok, Instagram, X, Facebook, YouTube*, ...) via yt-dlp
- Direct file links (PDF, ZIP, images, ...) via HTTP download
- Max send size 49 MB (Telegram Bot API cap)

*YouTube blocks many server IPs with a bot check; other sites work.

## Run locally
```
pip install -r requirements.txt   # needs ffmpeg for best-quality merge
BOT_TOKEN=<token> python bot.py
```

## Deploy (Render free web service)
1. Push this repo to a public git URL.
2. Render → New Web Service → Public Git repository → paste URL.
3. Runtime: Docker (uses Dockerfile). Instance: free.
4. Env var: BOT_TOKEN=<token>.
5. Keep-alive: point a free monitor (UptimeRobot/cron-job.org) at the
   service URL every 5 min so the free instance never idles to sleep.

The bot uses long polling (no webhook/domain needed); a tiny HTTP server
on $PORT answers health checks.
