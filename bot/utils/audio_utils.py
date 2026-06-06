import os
import re
import tempfile
import logging
import subprocess
from aiogram import Bot
from aiogram.types import Message

from speech2text_client import Speech2TextClient
from config import SPEECH2TEXT_API_KEY

logger = logging.getLogger(__name__)

_STT_TIMEOUT = 300  # секунд (можно увеличить до 600 для длинных встреч)


async def download_telegram_media(message: Message, bot: Bot) -> str:
    """
    Скачивает голосовое/аудио/видео сообщение из Telegram во временный файл.
    Возвращает путь к файлу.
    """
    file_obj = message.voice or message.audio or message.video
    if not file_obj:
        raise ValueError("В сообщении нет голосового, аудио или видео файла")

    file_info = await bot.get_file(file_obj.file_id)

    # Определяем расширение
    if message.voice:
        ext = "ogg"
    elif message.audio:
        original_name = getattr(file_obj, "file_name", "") or ""
        ext = original_name.rsplit(".", 1)[-1] if "." in original_name else "mp3"
    elif message.video:
        original_name = getattr(file_obj, "file_name", "") or ""
        ext = original_name.rsplit(".", 1)[-1] if "." in original_name else "mp4"
    else:
        ext = "bin"

    temp_path = os.path.join(tempfile.gettempdir(), f"tg_media_{message.message_id}.{ext}")
    file_bytes_io = await bot.download_file(file_info.file_path)
    with open(temp_path, "wb") as f:
        f.write(file_bytes_io.getvalue())

    logger.info(f"Медиа сохранено: {temp_path}")
    return temp_path


def extract_audio_from_video(video_path: str, output_audio_path: str) -> bool:
    """Извлекает аудио из видеофайла с помощью ffmpeg."""
    try:
        cmd = [
            "ffmpeg", "-i", video_path,
            "-vn",                     # без видео
            "-acodec", "libmp3lame",
            "-q:a", "2",               # качество
            "-y",                      # перезаписывать
            output_audio_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            logger.info(f"Аудио извлечено: {output_audio_path}")
            return True
        else:
            logger.error(f"Ошибка ffmpeg: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"Ошибка извлечения аудио: {e}")
        return False

async def download_telegram_media(message: Message, bot: Bot) -> str:
    file_obj = message.voice or message.audio or message.video or message.video_note or message.document
    if not file_obj:
        raise ValueError("В сообщении нет голосового, аудио, видео или документа")

    # Для документа используем file_obj напрямую
    file_info = await bot.get_file(file_obj.file_id)

    if message.document:
        ext = message.document.file_name.split('.')[-1]
    elif message.video_note:
        ext = "mp4"
    elif message.video:
        original_name = getattr(file_obj, "file_name", "") or ""
        ext = original_name.rsplit(".", 1)[-1] if "." in original_name else "mp4"
    elif message.audio:
        original_name = getattr(file_obj, "file_name", "") or ""
        ext = original_name.rsplit(".", 1)[-1] if "." in original_name else "mp3"
    else:
        ext = "ogg"

    temp_path = os.path.join(tempfile.gettempdir(), f"tg_media_{message.message_id}.{ext}")
    file_bytes_io = await bot.download_file(file_info.file_path)
    with open(temp_path, "wb") as f:
        f.write(file_bytes_io.getvalue())

    logger.info(f"Медиа сохранено: {temp_path}")
    return temp_path

def convert_audio_format(input_path: str, output_ext: str = "mp3") -> str:
    """Конвертирует аудио в поддерживаемый формат (mp3). Возвращает путь к новому файлу."""
    output_path = os.path.splitext(input_path)[0] + f".{output_ext}"
    try:
        cmd = ["ffmpeg", "-i", input_path, "-acodec", "libmp3lame", "-y", output_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            logger.info(f"Конвертировано в {output_path}")
            return output_path
        else:
            logger.error(f"Ошибка конвертации: {result.stderr}")
            return None
    except Exception as e:
        logger.error(f"Ошибка конвертации: {e}")
        return None


def clean_transcription(raw_text: str) -> str:
    if not raw_text:
        return ""
    text = re.sub(r'Спикер\s+\d+:\s*', '', raw_text)
    text = re.sub(r'\d{1,2}:\d{2}:\d{2}\s*-\s*', '', text)
    return re.sub(r'\s+', ' ', text).strip()


def transcribe_media(file_path: str) -> str:
    """
    Синхронная транскрибация медиафайла (аудио или видео).
    Поддерживает форматы: ogg, mp3, wav, mp4, webm, aac, wma, avi, mov, mkv.
    """
    if not file_path:
        logger.error("transcribe_media: передан пустой путь к файлу")
        return ""

    ext = os.path.splitext(file_path)[1].lower()
    audio_path = file_path

    # 1. Если видео – извлекаем аудио
    video_extensions = [".webm", ".mp4", ".avi", ".mov", ".mkv"]
    if ext in video_extensions:
        temp_audio = os.path.join(tempfile.gettempdir(), f"extracted_audio_{os.path.basename(file_path)}.mp3")
        if extract_audio_from_video(file_path, temp_audio):
            audio_path = temp_audio
        else:
            logger.error("Не удалось извлечь аудио из видео")
            return ""

    # 2. Проверяем, поддерживается ли формат напрямую API
    supported_formats = [".ogg", ".mp3", ".wav", ".mp4", ".aac", ".wma"]
    if ext not in supported_formats and audio_path == file_path:
        converted = convert_audio_format(audio_path, "mp3")
        if converted:
            audio_path = converted
        else:
            logger.error("Не удалось конвертировать аудио в поддерживаемый формат")
            return ""

    try:
        client = Speech2TextClient(SPEECH2TEXT_API_KEY)
        task_id = client.send_file(audio_path, lang="ru")
        if not task_id:
            logger.error("Не удалось отправить файл на распознавание")
            return ""

        result = client.wait_and_get_result(task_id, result_format="txt", timeout=_STT_TIMEOUT)
        if not result:
            logger.error("Не удалось получить результат распознавания")
            return ""

        cleaned = clean_transcription(result)
        logger.info(f"Медиа распознано: {len(cleaned)} символов")
        return cleaned
    except Exception as e:
        logger.error(f"Ошибка транскрибации: {e}")
        return ""
    finally:
        # Удаляем временные аудиофайлы, если они были созданы
        if audio_path != file_path and os.path.exists(audio_path):
            os.remove(audio_path)


def cleanup_temp_file(file_path: str) -> None:
    if not file_path:
        return
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Временный файл удалён: {file_path}")
    except OSError as e:
        logger.error(f"Не удалось удалить {file_path}: {e}")


# Сохраняем старые имена для обратной совместимости
download_telegram_audio = download_telegram_media
transcribe_audio = transcribe_media