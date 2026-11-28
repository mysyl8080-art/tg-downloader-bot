FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY config ./config
COPY downloader ./downloader
COPY media ./media
COPY database ./database
COPY services ./services
COPY bot ./bot
COPY admin ./admin
COPY main.py .
ENV DATA_DIR=/data
VOLUME /data
CMD ["python", "main.py"]
