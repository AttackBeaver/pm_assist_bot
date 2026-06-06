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
    if not PLAYWRIGHT_AVAILABLE:
        logger.error("capture_audio_with_ffmpeg вызвана при отсутствии playwright")
        return False
    cmd = [
        "ffmpeg", "-y",
        "-f", "pulse",
        "-i", "loopback",
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
            stderr=asyncio.subprocess.PIPE
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
                "--autoplay-policy=no-user-gesture-required"
            ]
        )
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(meet_url)
        await page.wait_for_load_state("networkidle")
        try:
            await page.wait_for_selector("button:has-text('Подключиться')", timeout=15000)
            await page.click("button:has-text('Подключиться')")
            logger.info("Кнопка 'Подключиться' нажата")
        except Exception as e:
            logger.warning(f"Не удалось найти/нажать кнопку 'Подключиться': {e}")
        await asyncio.sleep(10)
        success = await capture_audio_with_ffmpeg(duration_seconds, output_wav_path)
        await browser.close()
        return success