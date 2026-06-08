import asyncio
import os
import logging
from typing import Optional
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

DOWNLOADED_FILE = None

async def handle_download(download):
    global DOWNLOADED_FILE
    try:
        download_path = await download.path()
        target_path = f"/tmp/meet_recording_{asyncio.current_task().get_name()}.webm"
        with open(download_path, 'rb') as src, open(target_path, 'wb') as dst:
            dst.write(src.read())
        DOWNLOADED_FILE = target_path
        logger.info(f"Файл записи сохранён: {target_path}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении файла: {e}")

async def join_and_record_meet(meet_url: str, duration_seconds: int, output_wav_path: str) -> bool:
    global DOWNLOADED_FILE
    DOWNLOADED_FILE = None

    env = os.environ.copy()
    env['DISPLAY'] = ':99'
    env['PULSE_SERVER'] = env.get('PULSE_SERVER', 'unix:/var/run/pulse/native')
    logger.info(f"Окружение: DISPLAY={env['DISPLAY']}, PULSE_SERVER={env['PULSE_SERVER']}")

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
        context = await browser.new_context(
            accept_downloads=True,
            viewport={'width': 1280, 'height': 720}
        )
        context.on("download", handle_download)
        page = await context.new_page()
        logger.info(f"Переход по URL: {meet_url}")
        await page.goto(meet_url)
        await page.wait_for_load_state("networkidle")

        try:
            close_btn = await page.wait_for_selector("button[aria-label='Закрыть']", timeout=5000)
            if close_btn:
                await close_btn.click()
        except:
            pass

        try:
            join_button = await page.wait_for_selector('[data-testid="enter-conference-button"]', timeout=30000)
            await join_button.click(force=True)
            logger.info("Кнопка подключения нажата")
        except Exception as e:
            logger.error(f"Не удалось нажать кнопку подключения: {e}")
            await browser.close()
            return False

        await asyncio.sleep(10)  # увеличил паузу для полной загрузки интерфейса

        # Открыть меню "Ещё"
        try:
            more_button = await page.wait_for_selector('button[aria-label="Ещё"]', timeout=15000)
            await more_button.click(force=True)
            logger.info("Меню 'Ещё' открыто")
        except Exception as e:
            logger.warning(f"Не удалось нажать кнопку 'Ещё' обычным способом: {e}")
            # Альтернативный способ через JavaScript
            try:
                await page.evaluate('''() => {
                    const btn = document.querySelector('button[aria-label="Ещё"]');
                    if (btn) btn.click();
                }''')
                logger.info("Меню 'Ещё' открыто через JavaScript")
            except Exception as e2:
                logger.error(f"Не удалось открыть меню 'Ещё' даже через JS: {e2}")
                await browser.close()
                return False

        # Выбрать пункт "Записать на компьютер"
        try:
            record_button = await page.wait_for_selector('text="Записать на компьютер"', timeout=5000)
            await record_button.click(force=True)
            logger.info("Запись на компьютер начата")
        except Exception as e:
            logger.warning(f"Не найден пункт 'Записать на компьютер': {e}")
            try:
                record_button = await page.wait_for_selector('button:has-text("Запись")', timeout=5000)
                await record_button.click(force=True)
                logger.info("Запись начата (альтернативная кнопка)")
            except Exception as e2:
                logger.error(f"Альтернативная кнопка также не найдена: {e2}")
                # Попробуем через JavaScript найти элемент с текстом
                try:
                    await page.evaluate('''() => {
                        const items = document.querySelectorAll('div[role="menuitem"]');
                        for (let item of items) {
                            if (item.innerText.includes('Записать') || item.innerText.includes('Запись')) {
                                item.click();
                                break;
                            }
                        }
                    }''')
                    logger.info("Запись начата через JavaScript")
                except Exception as e3:
                    logger.error(f"Не удалось найти пункт записи даже через JS: {e3}")
                    await browser.close()
                    return False

        logger.info(f"Запись будет длиться {duration_seconds} секунд...")
        await asyncio.sleep(duration_seconds)

        # Остановить запись (нажать ту же кнопку или появившуюся "Остановить")
        try:
            stop_button = await page.wait_for_selector('text="Остановить запись"', timeout=10000)
            await stop_button.click(force=True)
            logger.info("Запись остановлена")
        except Exception as e:
            logger.warning(f"Не удалось найти кнопку остановки: {e}")
            # Возможно, запись уже остановилась сама (если лимит времени)

        # Ждём появления файла
        timeout_download = 60  # увеличил таймаут
        start_wait = asyncio.get_event_loop().time()
        while DOWNLOADED_FILE is None and (asyncio.get_event_loop().time() - start_wait) < timeout_download:
            await asyncio.sleep(1)
            logger.info("Ожидание файла записи...")
        if DOWNLOADED_FILE is None:
            logger.error("Файл записи не был получен.")
            await browser.close()
            return False

        logger.info(f"Извлечение аудио из {DOWNLOADED_FILE}")
        import subprocess
        cmd = [
            "ffmpeg", "-y",
            "-i", DOWNLOADED_FILE,
            "-vn", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1",
            output_wav_path
        ]
        try:
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
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
            if os.path.exists(DOWNLOADED_FILE):
                os.remove(DOWNLOADED_FILE)
