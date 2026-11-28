# Ultimate Downloader Bot V3

Telegram media downloader: send a link, pick a quality, get the file.
Arabic-first UI, SQLite persistence, in-process task queue, Docker/Railway ready.

## Features
- Platform auto-detect (YouTube*, TikTok, Instagram, Facebook, X, Reddit, Pinterest,
  SoundCloud, Twitch, Vimeo, Dailymotion, direct files, and every yt-dlp site)
- Preview before download: title, duration, size estimate, thumbnail, subtitles
- Quality buttons 144p-1080p + best; MP3/M4A/WAV/FLAC audio; MP4/MKV
- Playlists (capped, default 20) and up to 5 URLs per message
- Progress bar (%, speed, ETA), cancel + retry buttons
- Audio tools: extract, trim, volume, compress, voice message
- Video tools: trim, compress, GIF, speed, mute, merge, screenshot, metadata, MKV
- History, favorites, per-user settings (language, default quality/audio)
- Admin: stats, ban/unban, broadcast, maintenance mode, system status
- Security: env-only secrets, rate limiting, size caps, safe filenames,
  path-traversal and command-injection safe (argv-only ffmpeg), tmp cleanup

*YouTube/Instagram/Facebook: datacenter IPs are bot-blocked by those platforms.
Set `YT_COOKIES` (cookies.txt export) or `PROXY_URL` (residential proxy) to enable.

## Deploy (Railway)
1. Create a bot with @BotFather, copy the token.
2. New Railway service from this repo (Dockerfile detected automatically).
3. Variables: `BOT_TOKEN`, `ADMIN_IDS`. Attach a volume at `/data` for SQLite persistence.
4. Health endpoint: `GET :8080/` → `ok`.

## Local run
```
pip install -r requirements.txt   # needs ffmpeg installed
BOT_TOKEN=... python main.py
```

## Tests
```
python tests/run_all.py
```
