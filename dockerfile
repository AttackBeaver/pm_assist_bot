FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg \
    chromium \
    chromium-driver \
    pulseaudio \
    pulseaudio-utils \
    xvfb \
    dbus-x11 \
    procps \
    portaudio19-dev \
    python3-pyaudio \
    && rm -rf /var/lib/apt/lists/*

# Загружаем модуль loopback для захвата системного звука (может потребоваться запуск pulseaudio)
RUN pactl load-module module-null-sink sink_name=virtual_sink 2>/dev/null || true

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir python-multipart playwright && \
    playwright install chromium

COPY . .

ENV DATA_DIR=/app/data
RUN mkdir -p /app/data && chmod 777 /app/data

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["python", "main.py"]