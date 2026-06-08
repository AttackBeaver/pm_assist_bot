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
    """Захватывает аудио с PulseAudio устройства meet_sink.monitor."""
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
        "-i", "meet_sink.monitor",   # используем монитор нашего sink-а
        "-t", str(duration_seconds),
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
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
            size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
            logger.info(f"Аудио сохранено: {output_path}, размер: {size} байт")
            if size < 50000:
                logger.warning("Размер аудиофайла очень мал — вероятно, записана тишина")
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

    # Устанавливаем DISPLAY для Xvfb
    os.environ['DISPLAY'] = ':99'
    # Убедимся, что PulseAudio использует правильный сокет
    os.environ['PULSE_SERVER'] = os.environ.get('PULSE_SERVER', 'unix:/var/run/pulse/native')

    async with async_playwright() as p:
        # Запускаем браузер НЕ в headless, а через Xvfb (headed, но окно не видно)
        browser = await p.chromium.launch(
            headless=False,   # важно: False, т.к. используем Xvfb
            args=[
                "--use-fake-ui-for-media-stream",   # автоматически разрешаем доступ к микрофону/камере
                # "--use-fake-device-for-media-stream",  # Убираем – нам нужны реальные устройства!
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--autoplay-policy=no-user-gesture-required",
                "--alsa-output-device=meet_sink",   # направляем звук в наш sink
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
            ]
        )
        context = await browser.new_context()
        # Разрешаем доступ к микрофону (на всякий случай)
        await context.grant_permissions(["microphone", "camera"])
        page = await context.new_page()

        logger.info(f"Переход по URL: {meet_url}")
        await page.goto(meet_url)
        await page.wait_for_load_state("networkidle")

        # Закрыть возможное модальное окно
        try:
            close_btn = await page.wait_for_selector("button[aria-label='Закрыть']", timeout=5000)
            if close_btn:
                await close_btn.click()
                logger.info("Модальное окно закрыто")
        except Exception:
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

        # Ждём, пока звуковой поток станет активным
        await asyncio.sleep(10)

        # Запись аудио
        success = await capture_audio_with_ffmpeg(duration_seconds, output_wav_path)

        await browser.close()
        return success
