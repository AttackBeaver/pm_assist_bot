# bot/handlers/voice_handler.py
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.utils.audio_utils import download_telegram_audio, transcribe_audio, cleanup_temp_file
from bot.utils.parser import parse_task
from web.database import add_user

logger = logging.getLogger(__name__)
router = Router()

# Словарь для временного хранения данных задачи перед подтверждением
# Ключ: callback_data_id, значение: dict с task, deadline, assignee
pending_tasks = {}

@router.message(F.voice | F.audio)
async def handle_voice_message(message: Message, bot: Bot):
    # Регистрируем пользователя в БД (если ещё нет)
    add_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name
    )

    status_msg = await message.answer("🎙 Обрабатываю голосовое сообщение...")

    file_path = None
    try:
        file_path = await download_telegram_audio(message, bot)
        transcribed_text = transcribe_audio(file_path)

        if not transcribed_text:
            await status_msg.edit_text("❌ Не удалось распознать речь. Попробуйте написать текстом.")
            return

        # Парсим задачу из распознанного текста
        parse_result = parse_task(transcribed_text, known_usernames=[])

        # Если уверенность низкая (<50), просто показываем текст
        if parse_result["confidence"] < 50:
            await status_msg.edit_text(
                f"🔊 Я услышал:\n_{transcribed_text}_\n\n"
                f"Не уверен, что это задача. Вы можете создать её вручную командой /newtask",
                parse_mode="Markdown"
            )
            return

        # Формируем данные для подтверждения
        task_title = parse_result["task"]
        deadline_str = parse_result["deadline"] or "не указан"
        assignee = parse_result["assignee"] or "не назначен"

        # Сохраняем данные для callback (префикс voice_)
        callback_id = f"voice_{message.message_id}"
        pending_tasks[callback_id] = {
            "title": task_title,
            "description": transcribed_text,
            "deadline_str": parse_result["deadline"],
            "assignee_username": parse_result["assignee"],
            "chat_id": message.chat.id,
            "from_user_id": message.from_user.id
        }

        # Кнопки подтверждения (префиксы confirm_voice_ / cancel_voice_)
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Да, создать задачу", callback_data=f"confirm_voice_{callback_id}")
        builder.button(text="❌ Отмена", callback_data=f"cancel_voice_{callback_id}")
        builder.adjust(1)

        await status_msg.edit_text(
            f"📝 Распознанный текст:\n_{transcribed_text}_\n\n"
            f"**Задача:** {task_title}\n"
            f"**Дедлайн:** {deadline_str}\n"
            f"**Ответственный:** {assignee}\n\n"
            f"Создать карточку в YouGile?",
            parse_mode="Markdown",
            reply_markup=builder.as_markup()
        )

    except Exception as e:
        logger.error(f"Ошибка в voice_handler: {e}")
        await status_msg.edit_text("⚠️ Произошла ошибка при обработке аудио. Попробуйте позже.")
    finally:
        if file_path:
            cleanup_temp_file(file_path)