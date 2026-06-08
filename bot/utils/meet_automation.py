import asyncio
import os
import logging
from typing import Optional
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

# Глобальная переменная для хранения пути к скачанному файлу
DOWNLOADED_FILE = None


async def handle_download(download):
    """Обработчик события загрузки файла."""
    global DOWNLOADED_FILE
    try:
        # Сохраняем файл во временную директорию
        download_path = await download.path()
        # Копируем файл в нужное место (download.path() может быть временным)
        target_path = f"/tmp/meet_recording_{asyncio.current_task().get_name()}.webm"
        with open(download_path, 'rb') as src, open(target_path, 'wb') as dst:
            dst.write(src.read())
        DOWNLOADED_FILE = target_path
        logger.info(f"Файл записи сохранён: {target_path}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении файла: {e}")


async def join_and_record_meet(meet_url: str, duration_seconds: int, output_wav_path: str) -> bool:
    """
    Подключается к встрече, начинает запись через UI, ждёт duration_seconds,
    затем останавливает запись, перехватывает файл и извлекает аудио.
    """
    global DOWNLOADED_FILE
    DOWNLOADED_FILE = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # используем Xvfb для скрытия
            args=[
                "--use-fake-ui-for-media-stream",
                "--disable-web-security",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--autoplay-policy=no-user-gesture-required",
                "--disable-background-timer-throttling",
            ]
        )
        context = await browser.new_context(
            accept_downloads=True,  # важно: разрешить загрузки
            viewport={'width': 1280, 'height': 720}
        )
        # Настраиваем обработчик загрузки
        context.on("download", handle_download)

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
            join_button = await page.wait_for_selector('[data-testid="enter-conference-button"]', timeout=30000)
            await join_button.click(force=True)
            logger.info("Кнопка подключения нажата")
        except Exception as e:
            logger.error(f"Не удалось нажать кнопку подключения: {e}")
            await browser.close()
            return False

        # Ждём загрузки комнаты
        await asyncio.sleep(5)

        # Найти кнопку "Ещё" (три точки) и открыть меню
        try:
            more_button = await page.wait_selector('button[aria-label="Ещё"]', timeout=10000)
            await more_button.click()
            logger.info("Меню 'Ещё' открыто")
        except Exception as e:
            logger.error(f"Не найдена кнопка 'Ещё': {e}")
            await browser.close()
            return False

        # Нажать пункт "Записать на компьютер"
        try:
            record_button = await page.wait_for_selector('text="Записать на компьютер"', timeout=5000)
            await record_button.click()
            logger.info("Запись на компьютер начата")
        except Exception as e:
            logger.error(f"Не найден пункт 'Записать на компьютер': {e}")
            # Возможный альтернативный селектор
            try:
                record_button = await page.wait_for_selector('button:has-text("Запись")', timeout=5000)
                await record_button.click()
                logger.info("Запись начата (альтернативная кнопка)")
            except Exception as e2:
                logger.error(f"Альтернативная кнопка также не найдена: {e2}")
                await browser.close()
                return False

        # Ждём записи в течение duration_seconds
        logger.info(f"Запись будет длиться {duration_seconds} секунд...")
        await asyncio.sleep(duration_seconds)

        # Остановить запись (нажать ту же кнопку или появившуюся "Остановить")
        try:
            stop_button = await page.wait_for_selector('text="Остановить запись"', timeout=10000)
            await stop_button.click()
            logger.info("Запись остановлена")
        except Exception as e:
            logger.warning(f"Не удалось найти кнопку остановки: {e}, возможно, запись уже завершилась автоматически")

        # Ждём завершения скачивания (DOWNLOADED_FILE должен установиться)
        timeout_download = 30
        start_wait = asyncio.get_event_loop().time()
        while DOWNLOADED_FILE is None and (asyncio.get_event_loop().time() - start_wait) < timeout_download:
            await asyncio.sleep(1)
            logger.info("Ожидание файла записи...")
        if DOWNLOADED_FILE is None:
            logger.error("Файл записи не был получен.")
            await browser.close()
            return False

        # Извлекаем аудио из видеофайла
        logger.info(f"Извлечение аудио из {DOWNLOADED_FILE}")
        import subprocess
        cmd = [
            "ffmpeg", "-y",
            "-i", DOWNLOADED_FILE,
            "-vn",  # без видео
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            output_wav_path
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await proc.communicate()
            if proc.returncode == 0:
                logger.info(f"Аудио извлечено в {output_wav_path}")
                return True
            else:
                logger.error(f"Ошибка ffmpeg: {stderr.decode()}")
                return False
        except Exception as e:
            logger.error(f"Исключение при извлечении аудио: {e}")
            return False
        finally:
            # Очистка временного видеофайла
            if os.path.exists(DOWNLOADED_FILE):
                os.remove(DOWNLOADED_FILE)
                logger.info(f"Временный файл {DOWNLOADED_FILE} удалён")
