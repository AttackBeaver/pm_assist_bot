FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей для Chromium, PulseAudio, ffmpeg
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
    libnss3 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxi6 \
    libxtst6 \
    libxrandr2 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    && rm -rf /var/lib/apt/lists/*

# Создаём виртуальный звуковой кабель (loopback) – может не работать без привилегий, но для кода достаточно
RUN pactl load-module module-null-sink sink_name=virtual_sink 2>/dev/null || true

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Установка playwright и браузера Chromium
RUN pip install --no-cache-dir playwright && \
    playwright install chromium && \
    playwright install-deps

# Явно устанавливаем python-multipart (если нет в requirements)
RUN pip install --no-cache-dir python-multipart

COPY . .

ENV DATA_DIR=/app/data
RUN mkdir -p /app/data && chmod 777 /app/data

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["python", "main.py"]