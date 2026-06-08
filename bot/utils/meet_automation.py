import asyncio
import os
import logging
import base64
from typing import Optional
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

async def join_and_record_meet(meet_url: str, duration_seconds: int, output_wav_path: str) -> bool:
    env = os.environ.copy()
    env['DISPLAY'] = ':99'

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            env=env,
            args=[
                "--use-fake-ui-for-media-stream",
                "--disable-web-security",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--autoplay-policy=no-user-gesture-required",
                "--disable-background-timer-throttling",
            ]
        )
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})
        page = await context.new_page()
        logger.info(f"Переход по URL: {meet_url}")
        await page.goto(meet_url)
        await page.wait_for_load_state("networkidle")

        # Закрыть модальное окно
        try:
            close_btn = await page.wait_for_selector("button[aria-label='Закрыть']", timeout=5000)
            if close_btn:
                await close_btn.click()
        except:
            pass

        # Подключиться к встрече
        try:
            join_button = await page.wait_for_selector('[data-testid="enter-conference-button"]', timeout=30000)
            await join_button.click(force=True)
            logger.info("Кнопка подключения нажата")
        except Exception as e:
            logger.error(f"Не удалось нажать кнопку подключения: {e}")
            await browser.close()
            return False

        # Ожидаем появления аудиоэлемента (WebRTC подключение)
        try:
            await page.wait_for_selector('audio', timeout=15000)
            logger.info("Аудиоэлемент найден")
        except:
            logger.warning("Аудиоэлемент не найден, возможно, WebRTC ещё не готов")
            await asyncio.sleep(5)

        # JavaScript для захвата аудио через MediaRecorder
        capture_js = """
        async (durationSec) => {
            const audioElement = document.querySelector('audio');
            if (!audioElement) throw new Error('Аудиоэлемент не найден');
            // Убеждаемся, что звук не отключён
            audioElement.muted = false;
            audioElement.volume = 1;
            const stream = audioElement.captureStream();
            const audioTracks = stream.getAudioTracks();
            if (audioTracks.length === 0) throw new Error('Нет аудиодорожек');
            const mediaRecorder = new MediaRecorder(stream);
            const chunks = [];
            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) chunks.push(e.data);
            };
            mediaRecorder.onstop = () => {
                const blob = new Blob(chunks, { type: 'audio/webm' });
                const reader = new FileReader();
                reader.onloadend = () => {
                    window.__playwright_audio_result = reader.result;
                };
                reader.readAsDataURL(blob);
            };
            mediaRecorder.start(1000);
            setTimeout(() => {
                if (mediaRecorder.state === 'recording') mediaRecorder.stop();
            }, durationSec * 1000);
            return 'started';
        }
        """
        await page.evaluate(capture_js, duration_seconds)
        logger.info(f"Запись аудио запущена на {duration_seconds} секунд")
        await asyncio.sleep(duration_seconds + 5)

        audio_data_url = await page.evaluate("window.__playwright_audio_result")
        if not audio_data_url:
            logger.error("Не удалось получить аудиоданные")
            await browser.close()
            return False

        if not audio_data_url.startswith("data:audio/webm;base64,"):
            logger.error("Неверный формат аудиоданных")
            await browser.close()
            return False

        base64_data = audio_data_url.split(",")[1]
        webm_data = base64.b64decode(base64_data)
        temp_webm = f"/tmp/meet_audio_{asyncio.current_task().get_name()}.webm"
        with open(temp_webm, "wb") as f:
            f.write(webm_data)
        logger.info(f"Аудио WebM сохранён: {temp_webm}, размер: {len(webm_data)} байт")

        # Конвертируем WebM -> WAV (16кГц, моно)
        import subprocess
        cmd = [
            "ffmpeg", "-y",
            "-i", temp_webm,
            "-vn", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1",
            output_wav_path
        ]
        try:
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            _, stderr = await proc.communicate()
            if proc.returncode == 0:
                logger.info(f"Аудио конвертировано в {output_wav_path}")
                return True
            else:
                logger.error(f"Ошибка ffmpeg: {stderr.decode()}")
                return False
        except Exception as e:
            logger.error(f"Исключение при конвертации: {e}")
            return False
        finally:
            if os.path.exists(temp_webm):
                os.remove(temp_webm)