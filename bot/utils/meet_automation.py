import asyncio
import os
import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

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

    env = os.environ.copy()
    pulse_server = env.get('PULSE_SERVER')
    if not pulse_server:
        logger.error("Переменная PULSE_SERVER не установлена")
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

    # Добавим параметр имени, если Телемост поддерживает
    if "?" in meet_url:
        meet_url += "&name=PM-Assist_bot"
    else:
        meet_url += "?name=PM-Assist_bot"

    logger.info(f"Запуск браузера для URL: {meet_url}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--autoplay-policy=no-user-gesture-required",
                "--alsa-output-device=virtual_sink",
                "--disable-background-timer-throttling",
            ]
        )
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(meet_url)
        await page.wait_for_load_state("networkidle")

        # Закрыть модальное окно, если есть
        try:
            close_btn = await page.wait_for_selector("button[aria-label='Закрыть']", timeout=5000)
            if close_btn and await close_btn.is_visible():
                await close_btn.click()
                logger.info("Модальное окно закрыто")
        except:
            pass

        # Нажать кнопку подключения
        try:
            button = await page.wait_for_selector('[data-testid="enter-conference-button"]', timeout=30000)
            await button.click(force=True)
            logger.info("Кнопка подключения нажата")
        except Exception as e:
            logger.error(f"Не удалось нажать кнопку: {e}")
            await browser.close()
            return False

        await asyncio.sleep(10)  # ждём подключения
        success = await capture_audio_with_ffmpeg(duration_seconds, output_wav_path)
        await browser.close()
        return success