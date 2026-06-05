import logging
import uuid
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.utils.audio_utils import download_telegram_audio, transcribe_audio, cleanup_temp_file
from bot.utils.parser import parse_task
from bot.utils.date_utils import deadline_to_timestamp
from bot.utils.yougile_utils import create_yougile_task
from web.database import add_user, add_task, get_telegram_id_by_username

logger = logging.getLogger(__name__)
router = Router()
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
            await status_msg.edit_text("❌ Не удалось распознать речь.")
            return

        parse_result = parse_task(transcribed_text, known_usernames=[])
        if parse_result["confidence"] < _CONFIDENCE_THRESHOLD:
            await status_msg.edit_text(
                f"🔊 Я услышал:\n{transcribed_text}\n\nНе уверен, что это задача."
            )
            return

        # Определяем ответственного
        responsible_id = message.from_user.id
        assignee_username = parse_result.get("assignee")
        if assignee_username:
            clean_username = assignee_username.lstrip('@')
            found_id = get_telegram_id_by_username(clean_username)
            if found_id:
                responsible_id = found_id

        # Создаём задачу в YouGile
        card_id = await create_yougile_task(
            title=parse_result["task"],
            description=transcribed_text,
            deadline_str=parse_result["deadline"],
        )
        if not card_id:
            await status_msg.edit_text("❌ Не удалось создать задачу в YouGile.")
            return

        # Сохраняем в БД
        task_uuid = str(uuid.uuid4())
        add_task(
            task_id=task_uuid,
            title=parse_result["task"],
            description=transcribed_text,
            responsible_telegram_id=responsible_id,
            deadline=parse_result["deadline"],
            deadline_timestamp=deadline_to_timestamp(parse_result["deadline"]) if parse_result["deadline"] else None,
            yougile_card_id=card_id,
            chat_id=message.chat.id,
        )

        # Уведомление ответственному
        if responsible_id != message.from_user.id:
            try:
                await bot.send_message(
                    responsible_id,
                    f"🔔 Вам назначена задача в группе {message.chat.title} (голосовое сообщение):\n\n"
                    f"📋 {parse_result['task']}\n"
                    f"⏰ Дедлайн: {parse_result['deadline'] or 'не указан'}\n"
                    f"🌐 Посмотреть: /tasks"
                )
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление пользователю {responsible_id}: {e}")

        # Кнопка отмены
        builder = InlineKeyboardBuilder()
        builder.button(text="❌ Отменить задачу", callback_data=f"cancel_task_{task_uuid}")
        builder.adjust(1)

        reply_text = (
            f"✅ Задача автоматически создана в YouGile!\n\n"
            f"📋 {parse_result['task']}\n"
            f"⏰ Дедлайн: {parse_result['deadline'] or 'не указан'}\n"
            f"👤 Ответственный: @{assignee_username or 'не назначен'}\n\n"
            f"Нажмите «Отменить», если задача создана ошибочно."
        )
        await status_msg.edit_text(reply_text, reply_markup=builder.as_markup())
    except Exception as e:
        logger.error(f"Ошибка в voice_handler: {e}")
        await status_msg.edit_text("⚠️ Произошла ошибка при обработке аудио.")
    finally:
        if file_path:
            cleanup_temp_file(file_path)