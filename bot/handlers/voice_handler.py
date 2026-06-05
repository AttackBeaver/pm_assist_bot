import logging
from typing import Dict, Any

from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.utils.audio_utils import download_telegram_audio, transcribe_audio, cleanup_temp_file
from bot.utils.parser import parse_task
from web.database import add_user

logger = logging.getLogger(__name__)
router = Router()

# Временное хранилище неподтверждённых голосовых задач (сбрасывается при перезапуске бота)
pending_tasks: Dict[str, Dict[str, Any]] = {}

_CONFIDENCE_THRESHOLD = 50


@router.message(F.voice | F.audio)
async def handle_voice_message(message: Message, bot: Bot) -> None:
    add_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    status_msg = await message.answer("🎙 Обрабатываю голосовое сообщение...")

    file_path = None
    try:
        file_path = await download_telegram_audio(message, bot)
        transcribed_text = transcribe_audio(file_path)

        if not transcribed_text:
            await status_msg.edit_text(
                "❌ Не удалось распознать речь\\. Попробуйте написать текстом\\."
            )
            return

        parse_result = parse_task(transcribed_text, known_usernames=[])

        if parse_result["confidence"] < _CONFIDENCE_THRESHOLD:
            await status_msg.edit_text(
                f"🔊 Я услышал:\n_{transcribed_text}_\n\n"
                "Не уверен, что это задача\\. Напишите её текстом, если нужно создать карточку\\."
            )
            return

        task_title = parse_result["task"]
        deadline_str = parse_result["deadline"] or "не указан"
        assignee = parse_result["assignee"] or "не назначен"

        callback_id = f"voice_{message.message_id}"
        pending_tasks[callback_id] = {
            "title": task_title,
            "description": transcribed_text,
            "deadline_str": parse_result["deadline"],
            "assignee_username": parse_result["assignee"],
            "chat_id": message.chat.id,
            "from_user_id": message.from_user.id,
        }

        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Да, создать задачу", callback_data=f"confirm_voice_{callback_id}")
        builder.button(text="❌ Отмена", callback_data=f"cancel_voice_{callback_id}")
        builder.adjust(1)

        await status_msg.edit_text(
            f"🔊 *Распознанный текст:*\n_{transcribed_text}_\n\n"
            f"*Задача:* {task_title}\n"
            f"*Дедлайн:* {deadline_str}\n"
            f"*Ответственный:* {assignee}\n\n"
            "Создать карточку в YouGile?",
            reply_markup=builder.as_markup(),
        )

    except Exception as e:
        logger.error(f"Ошибка обработки голосового сообщения: {e}")
        await status_msg.edit_text(
            "⚠️ Произошла ошибка при обработке аудио\\. Попробуйте позже\\."
        )
    finally:
        if file_path:
            cleanup_temp_file(file_path)