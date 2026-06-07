import asyncio
import os
import tempfile
import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

# Проверяем доступность playwright
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright не установлен. Функции meet_automation будут заглушками.")


async def capture_audio_with_ffmpeg(duration_seconds: int, output_path: str) -> bool:
    """Захватывает аудио с PulseAudio устройства virtual_sink.monitor."""
    if not PLAYWRIGHT_AVAILABLE:
        logger.error("capture_audio_with_ffmpeg вызвана при отсутствии playwright")
        return False

    # Передаём переменную окружения для PulseAudio (берём из окружения бота)
    env = os.environ.copy()
    pulse_server = env.get('PULSE_SERVER')
    if not pulse_server:
        logger.error("Переменная PULSE_SERVER не установлена, ffmpeg не сможет захватить звук")
        return False

    cmd = [
        "ffmpeg", "-y",
        "-f", "pulse",
        "-i", "virtual_sink.monitor",
        "-t", str(duration_seconds),
        "-acodec", "pcm_s16le",
        "-ar", "44100",
        "-ac", "2",
        output_path
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        _, stderr = await proc.communicate()
        if proc.returncode == 0:
            logger.info(f"Аудио сохранено: {output_path}")
            return True
        else:
            logger.error(f"Ошибка ffmpeg: {stderr.decode()}")
            return False
    except Exception as e:
        logger.error(f"Ошибка захвата аудио: {e}")
        return False


async def join_and_record_meet(meet_url: str, duration_seconds: int, output_wav_path: str) -> bool:
    if not PLAYWRIGHT_AVAILABLE:
        logger.error("join_and_record_meet вызвана при отсутствии playwright")
        return False

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--use-fake-ui-for-media-stream",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--autoplay-policy=no-user-gesture-required",
                "--alsa-output-device=virtual_sink",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
            ]
        )
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(meet_url)
        await page.wait_for_load_state("networkidle")

        # Попытка закрыть модальное окно (если появляется)
        try:
            close_btn = await page.wait_for_selector("button[aria-label='Закрыть']", timeout=5000)
            if close_btn:
                await close_btn.click()
                logger.info("Модальное окно закрыто")
        except Exception as e:
            logger.info(f"Модального окна не было или не удалось закрыть: {e}")

        # Принудительный клик по кнопке подключения
        try:
            button = await page.wait_for_selector("button:has-text('Подключиться')", timeout=30000)
            await button.click(force=True, timeout=5000)
            logger.info("Кнопка 'Подключиться' нажата принудительно")
        except Exception as e:
            logger.error(f"Не удалось нажать кнопку 'Подключиться': {e}")
            await browser.close()
            return False

        await asyncio.sleep(10)  # ждём подключения к аудио
        success = await capture_audio_with_ffmpeg(duration_seconds, output_wav_path)
        await browser.close()
        return success