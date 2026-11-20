# InsaneVoice engine — CPU-only, self-contained.
# Build:  docker build -t insanevoice .
# Run:    docker run -p 8177:8177 -v insanevoice-data:/app/.ivdata insanevoice
# NOTE: first boot downloads model checkpoints (~330MB) into the mounted volume.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libgomp1 curl git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# engine deps first (torch CPU)
COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt playwright \
    && python -m playwright install chromium || true

# engine code + rigs
COPY backend ./backend
COPY scripts ./scripts

ENV INSANEVOICE_HOME=/app/.ivdata
VOLUME /app/.ivdata
EXPOSE 8177

HEALTHCHECK --interval=30s --timeout=5s CMD curl -sf http://127.0.0.1:8177/api/system || exit 1

CMD ["sh", "-c", "python scripts/download_models.py && cd backend && uvicorn main:app --host 0.0.0.0 --port 8177"]
