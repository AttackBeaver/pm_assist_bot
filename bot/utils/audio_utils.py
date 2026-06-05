import os
import re
import tempfile
import logging

from aiogram import Bot
from aiogram.types import Message

from speech2text_client import Speech2TextClient
from config import SPEECH2TEXT_API_KEY

logger = logging.getLogger(__name__)

_STT_TIMEOUT = 120  # секунд


async def download_telegram_audio(message: Message, bot: Bot) -> str:
    """
    Скачивает голосовое/аудио сообщение из Telegram во временный файл.
    Возвращает путь к файлу. При ошибке выбрасывает исключение.
    """
    file_obj = message.voice or message.audio
    if not file_obj:
        raise ValueError("В сообщении нет голосового или аудио файла")

    file_info = await bot.get_file(file_obj.file_id)

    if message.voice:
        ext = "ogg"
    else:
        original_name: str = getattr(file_obj, "file_name", "") or ""
        ext = original_name.rsplit(".", 1)[-1] if "." in original_name else "mp3"

    temp_path = os.path.join(
        tempfile.gettempdir(), f"tg_audio_{message.message_id}.{ext}"
    )

    file_bytes_io = await bot.download_file(file_info.file_path)
    with open(temp_path, "wb") as f:
        f.write(file_bytes_io.getvalue())

    logger.info(f"Аудио сохранено: {temp_path}")
    return temp_path


def clean_transcription(raw_text: str) -> str:
    """Удаляет метки спикеров и временны́е метки из транскрипции speech2text.ru."""
    if not raw_text:
        return ""
    text = re.sub(r'Спикер\s+\d+:\s*', '', raw_text)
    text = re.sub(r'\d{1,2}:\d{2}:\d{2}\s*-\s*', '', text)
    return re.sub(r'\s+', ' ', text).strip()


def transcribe_audio(file_path: str) -> str:
    """
    Синхронная транскрибация аудиофайла через Speech2TextClient.
    Возвращает очищенный текст или пустую строку при ошибке.
    """
    if not file_path:
        logger.error("transcribe_audio: передан пустой путь к файлу")
        return ""

    try:
        client = Speech2TextClient(SPEECH2TEXT_API_KEY)
        task_id = client.send_file(file_path, lang="ru")
        if not task_id:
            logger.error("Не удалось отправить файл на распознавание")
            return ""

        result = client.wait_and_get_result(task_id, result_format="txt", timeout=_STT_TIMEOUT)
        if not result:
            logger.error("Не удалось получить результат распознавания")
            return ""

        cleaned = clean_transcription(result)
        logger.info(f"Аудио распознано: {len(cleaned)} символов")
        return cleaned

    except Exception as e:
        logger.error(f"Ошибка транскрибации: {e}")
        return ""


def cleanup_temp_file(file_path: str) -> None:
    """Удаляет временный файл, если он существует."""
    if not file_path:
        return
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Временный файл удалён: {file_path}")
    except OSError as e:
        logger.error(f"Не удалось удалить временный файл {file_path}: {e}")