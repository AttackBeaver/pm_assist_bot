import os
import tempfile
import logging
import re
from aiogram import Bot
from aiogram.types import Message

from speech2text_client import Speech2TextClient
from config import SPEECH2TEXT_API_KEY

logger = logging.getLogger(__name__)

async def download_telegram_audio(message: Message, bot: Bot) -> str:
    """
    Скачивает голосовое/аудио из Telegram, сохраняет во временный файл, возвращает путь.
    В случае ошибки выбрасывает исключение.
    """
    try:
        file_obj = message.voice or message.audio
        if not file_obj:
            raise ValueError("В сообщении нет голосового или аудио файла")

        file_info = await bot.get_file(file_obj.file_id)
        
        # Определяем расширение
        if message.voice:
            ext = "ogg"
        else:
            # Для аудио пытаемся взять расширение из имени файла
            original_name = getattr(file_obj, 'file_name', None)
            if original_name and '.' in original_name:
                ext = original_name.split('.')[-1]
            else:
                ext = "mp3"
        
        temp_dir = tempfile.gettempdir()
        temp_file_path = os.path.join(temp_dir, f"tg_audio_{message.message_id}.{ext}")
        
        # Скачиваем и сохраняем
        file_bytes_io = await bot.download_file(file_info.file_path)
        with open(temp_file_path, 'wb') as f:
            f.write(file_bytes_io.getvalue())
        
        logger.info(f"Аудио сохранено: {temp_file_path}")
        return temp_file_path  # гарантированно возвращаем строку
        
    except Exception as e:
        logger.error(f"Ошибка скачивания аудио: {e}")
        raise  # пробрасываем дальше, чтобы в voice_handler обработали

def clean_transcription(raw_text: str) -> str:
    """Удаляет метки спикеров и временные метки из транскрипции."""
    if not raw_text:
        return ""
    # Удаляем "Спикер X: " и "Спикер X:"
    text = re.sub(r'Спикер\s+\d+:\s*', '', raw_text)
    # Удаляем временные метки вида "0:00:00 - " или "0:00:00-"
    text = re.sub(r'\d{1,2}:\d{2}:\d{2}\s*-\s*', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def transcribe_audio(file_path: str) -> str:
    """
    Синхронная транскрибация аудио через Speech2TextClient.
    Принимает путь к файлу (str), возвращает очищенный текст или пустую строку.
    """
    if not file_path or not isinstance(file_path, str):
        logger.error(f"transcribe_audio: передан некорректный путь: {file_path}")
        return ""
    
    try:
        client = Speech2TextClient(SPEECH2TEXT_API_KEY)
        task_id = client.send_file(file_path, lang="ru")
        if not task_id:
            logger.error("Не удалось отправить файл на распознавание")
            return ""
        result = client.wait_and_get_result(task_id, result_format="txt", timeout=120)
        if result:
            cleaned = clean_transcription(result)
            logger.info(f"Аудио распознано, длина текста: {len(cleaned)} симв.")
            return cleaned
        else:
            logger.error("Не удалось получить результат распознавания")
            return ""
    except Exception as e:
        logger.error(f"Ошибка транскрибации: {e}")
        return ""

def cleanup_temp_file(file_path: str) -> None:
    """Удаляет временный файл."""
    if not file_path:
        return
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Временный файл удалён: {file_path}")
    except Exception as e:
        logger.error(f"Ошибка удаления {file_path}: {e}")