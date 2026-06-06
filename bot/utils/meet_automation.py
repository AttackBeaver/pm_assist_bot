import asyncio
import os
import tempfile
import logging
import subprocess
import time
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

# Конфигурация захвата звука
AUDIO_FORMAT = "wav"
AUDIO_RATE = 44100
AUDIO_CHANNELS = 2

async def capture_audio_with_ffmpeg(duration_seconds: int, output_path: str) -> bool:
    """
    Захватывает системный звук через ffmpeg с loopback-устройством PulseAudio.
    Возвращает True при успехе, иначе False.
    """
    # Используем loopback PulseAudio (если он загружен)
    # Команда: ffmpeg -f pulse -i loopback -t duration -acodec pcm_s16le -ar 44100 -ac 2 output.wav
    cmd = [
        "ffmpeg", "-y",
        "-f", "pulse",
        "-i", "loopback",
        "-t", str(duration_seconds),
        "-acodec", "pcm_s16le",
        "-ar", str(AUDIO_RATE),
        "-ac", str(AUDIO_CHANNELS),
        output_path
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            logger.info(f"Аудио захвачено и сохранено в {output_path}")
            return True
        else:
            logger.error(f"Ошибка ffmpeg: {stderr.decode()}")
            return False
    except Exception as e:
        logger.error(f"Исключение при захвате аудио: {e}")
        return False

async def join_and_record_meet(meet_url: str, duration_seconds: int, output_wav_path: str) -> bool:
    """
    Открывает браузер, подключается к Яндекс Телемосту, захватывает звук.
    Возвращает True при успехе, иначе False.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--use-fake-ui-for-media-stream",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--autoplay-policy=no-user-gesture-required"
            ]
        )
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(meet_url)
        # Ждём загрузки страницы
        await page.wait_for_load_state("networkidle")
        # Пытаемся найти кнопку "Подключиться" (селекторы могут обновляться)
        try:
            # Стандартный селектор Яндекс Телемоста
            await page.wait_for_selector("button:has-text('Подключиться')", timeout=15000)
            await page.click("button:has-text('Подключиться')")
            logger.info("Кнопка 'Подключиться' нажата")
        except Exception as e:
            logger.warning(f"Не удалось найти/нажать кнопку 'Подключиться': {e}")
        # Даём время на установку соединения
        await asyncio.sleep(10)
        # Захватываем аудио
        success = await capture_audio_with_ffmpeg(duration_seconds, output_wav_path)
        await browser.close()
        return success