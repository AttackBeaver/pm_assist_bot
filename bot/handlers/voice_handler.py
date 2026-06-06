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

async def ensure_user_exists(username: str, bot: Bot, chat_id: int) -> int | None:
    clean = username.lstrip('@')
    existing_id = get_telegram_id_by_username(clean)
    if existing_id:
        return existing_id
    try:
        chat = await bot.get_chat(chat_id)
        member = await chat.get_member(clean)
        if member.user.id:
            add_user(member.user.id, clean, member.user.full_name)
            return member.user.id
    except Exception:
        pass
    return None

@router.message(F.voice | F.audio)
async def handle_voice_message(message: Message, bot: Bot) -> None:
    add_user(message.from_user.id, message.from_user.username, message.from_user.full_name)

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
            await status_msg.edit_text(f"🔊 Я услышал:\n{transcribed_text}\n\nНе уверен, что это задача.")
            return

        assignee_usernames = parse_result.get("assignees", [])
        if not assignee_usernames:
            assignee_usernames = [None]

        author_id = message.from_user.id

        for assignee_username in assignee_usernames:
            responsible_id = author_id
            if assignee_username:
                found_id = await ensure_user_exists(assignee_username, bot, message.chat.id)
                if found_id:
                    responsible_id = found_id

            card_id = await create_yougile_task(
                title=parse_result["task"],
                description=transcribed_text,
                deadline_str=parse_result["deadline"],
            )
            if not card_id:
                await status_msg.edit_text("❌ Не удалось создать задачу в YouGile.")
                return

            task_uuid = str(uuid.uuid4())
            add_task(
                task_id=task_uuid,
                title=parse_result["task"],
                description=transcribed_text,
                responsible_telegram_id=responsible_id,
                author_telegram_id=author_id,
                deadline=parse_result["deadline"],
                deadline_timestamp=deadline_to_timestamp(parse_result["deadline"]) if parse_result["deadline"] else None,
                yougile_card_id=card_id,
                chat_id=message.chat.id,
            )

            if responsible_id == author_id:
                keyboard = InlineKeyboardBuilder()
                keyboard.button(text="❌ Удалить задачу", callback_data=f"cancel_task_{task_uuid}")
                keyboard.button(text="▶️ Взять в работу", callback_data=f"move_to_do_{task_uuid}")
                keyboard.button(text="✅ Завершить", callback_data=f"complete_task_{task_uuid}")
                keyboard.adjust(1)
                try:
                    await bot.send_message(
                        author_id,
                        f"📌 Вы создали задачу (голосовое):\n\n"
                        f"📋 {parse_result['task']}\n"
                        f"⏰ Дедлайн: {parse_result['deadline'] or 'не указан'}\n"
                        f"👥 Ответственные: {', '.join(assignee_usernames) if assignee_usernames[0] else 'вы'}\n\n"
                        f"Управляйте задачей:",
                        reply_markup=keyboard.as_markup()
                    )
                except Exception as e:
                    logger.error(f"Не удалось отправить уведомление автору {author_id}: {e}")
            else:
                keyboard_worker = InlineKeyboardBuilder()
                keyboard_worker.button(text="▶️ Взять в работу", callback_data=f"move_to_do_{task_uuid}")
                keyboard_worker.button(text="✅ Завершить", callback_data=f"complete_task_{task_uuid}")
                keyboard_worker.adjust(1)
                try:
                    await bot.send_message(
                        responsible_id,
                        f"🔔 Вам назначена задача в группе {message.chat.title} (голосовое):\n\n"
                        f"📋 {parse_result['task']}\n"
                        f"⏰ Дедлайн: {parse_result['deadline'] or 'не указан'}\n\n"
                        f"Управляйте задачей:",
                        reply_markup=keyboard_worker.as_markup()
                    )
                except Exception as e:
                    logger.error(f"Не удалось отправить уведомление ответственному {responsible_id}: {e}")

                keyboard_author = InlineKeyboardBuilder()
                keyboard_author.button(text="❌ Удалить задачу", callback_data=f"cancel_task_{task_uuid}")
                keyboard_author.adjust(1)
                try:
                    await bot.send_message(
                        author_id,
                        f"📌 Вы создали задачу для @{assignee_username} (голосовое):\n\n"
                        f"📋 {parse_result['task']}\n"
                        f"⏰ Дедлайн: {parse_result['deadline'] or 'не указан'}\n\n"
                        f"Вы можете удалить задачу, если она создана ошибочно:",
                        reply_markup=keyboard_author.as_markup()
                    )
                except Exception as e:
                    logger.error(f"Не удалось отправить уведомление автору {author_id}: {e}")

        # Ответ в группе без кнопок
        reply_text = (
            f"✅ Задача автоматически создана в YouGile!\n\n"
            f"📋 {parse_result['task']}\n"
            f"⏰ Дедлайн: {parse_result['deadline'] or 'не указан'}\n"
            f"👥 Ответственные: {', '.join(assignee_usernames) if assignee_usernames and assignee_usernames[0] else 'не назначены'}"
        )
        await status_msg.edit_text(reply_text)
    except Exception as e:
        logger.error(f"Ошибка в voice_handler: {e}")
        await status_msg.edit_text("⚠️ Произошла ошибка при обработке аудио.")
    finally:
        if file_path:
            cleanup_temp_file(file_path)