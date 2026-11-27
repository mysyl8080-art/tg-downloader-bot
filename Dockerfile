FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg nodejs && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py downloader.py quran_meta.py quran_bg.py quran_render.py quran_video.py quran_bot.py quran_uthmani.json ./
COPY fonts ./fonts/
CMD ["python", "bot.py"]
