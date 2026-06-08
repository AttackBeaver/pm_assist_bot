import asyncio
import os
import tempfile
import logging
import uuid
from aiogram.types import Message, BufferedInputFile
from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.utils.meet_automation import join_and_record_meet
from bot.utils.audio_utils import transcribe_media
from bot.utils.llm_parser import parse_task_with_llm, summarize_text
from bot.utils.parser import parse_task as regex_parse_task
from bot.utils.date_utils import deadline_to_timestamp
from bot.utils.yougile_utils import create_yougile_task
from web.database import add_task, get_telegram_id_by_username, add_task_history

logger = logging.getLogger(__name__)

async def process_meeting(meet_url: str, duration: int, original_message: Message, bot: Bot):
    chat_id = original_message.chat.id
    user_id = original_message.from_user.id
    temp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name

    try:
        await original_message.answer("🎧 Подключаюсь и начинаю запись...")
        success = await join_and_record_meet(meet_url, duration, temp_wav)

        if not success:
            await bot.send_message(chat_id, "❌ Не удалось записать звук.")
            return

        with open(temp_wav, 'rb') as f:
            audio_data = f.read()
        await bot.send_audio(
            chat_id=chat_id,
            audio=BufferedInputFile(audio_data, filename="meeting_recording.wav"),
            caption="🎤 Запись встречи (для проверки качества)"
        )

        await original_message.answer("🔊 Распознаю речь...")
        transcribed_text = transcribe_media(temp_wav)
        if not transcribed_text:
            await bot.send_message(chat_id, "❌ Не удалось распознать речь.")
            return

        summary = summarize_text(transcribed_text)
        if summary:
            await bot.send_message(chat_id, f"📝 **Краткое саммари встречи:**\n{summary}")

        # Извлечение задач
        parse_result = parse_task_with_llm(transcribed_text)
        if not parse_result or parse_result.get("confidence", 0) < 70:
            parse_result = regex_parse_task(transcribed_text, known_usernames=[])
        if not parse_result or parse_result.get("confidence", 0) < 70:
            await bot.send_message(chat_id, "🔊 Не удалось выделить задачи.")
            return

        assignee_usernames = parse_result.get("assignees", []) or [None]
        author_id = user_id
        created_tasks = []

        for assignee in assignee_usernames:
            responsible_id = author_id
            if assignee:
                clean = assignee.lstrip('@')
                found_id = get_telegram_id_by_username(clean)
                if found_id:
                    responsible_id = found_id

            card_id = await create_yougile_task(
                title=parse_result["task"],
                description=transcribed_text,
                deadline_str=parse_result["deadline"],
            )
            if card_id:
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
                    chat_id=chat_id,
                )
                add_task_history(task_uuid, 'pending', comment='Задача из встречи')
                created_tasks.append((parse_result["task"], assignee))

                # Отправка уведомлений
                assignee_str = f"@{assignee}" if assignee else "не назначен"
                if responsible_id == author_id:
                    keyboard = InlineKeyboardBuilder()
                    keyboard.button(text="❌ Удалить задачу", callback_data=f"cancel_task_{task_uuid}")
                    keyboard.button(text="▶️ Взять в работу", callback_data=f"move_to_do_{task_uuid}")
                    keyboard.button(text="✅ Завершить", callback_data=f"complete_task_{task_uuid}")
                    keyboard.adjust(1)
                    await bot.send_message(
                        author_id,
                        f"📌 Вы создали задачу из встречи:\n\n"
                        f"📋 {parse_result['task']}\n"
                        f"⏰ Дедлайн: {parse_result['deadline'] or 'не указан'}\n"
                        f"👥 Ответственные: {assignee_str}\n\n"
                        f"Управляйте задачей:",
                        reply_markup=keyboard.as_markup()
                    )
                else:
                    keyboard_worker = InlineKeyboardBuilder()
                    keyboard_worker.button(text="▶️ Взять в работу", callback_data=f"move_to_do_{task_uuid}")
                    keyboard_worker.button(text="✅ Завершить", callback_data=f"complete_task_{task_uuid}")
                    keyboard_worker.adjust(1)
                    await bot.send_message(
                        responsible_id,
                        f"🔔 Вам назначена задача из встречи (из расшифровки):\n\n"
                        f"📋 {parse_result['task']}\n"
                        f"⏰ Дедлайн: {parse_result['deadline'] or 'не указан'}\n\n"
                        f"Управляйте задачей:",
                        reply_markup=keyboard_worker.as_markup()
                    )
                    keyboard_author = InlineKeyboardBuilder()
                    keyboard_author.button(text="❌ Удалить задачу", callback_data=f"cancel_task_{task_uuid}")
                    keyboard_author.adjust(1)
                    await bot.send_message(
                        author_id,
                        f"📌 Вы создали задачу для @{assignee} из встречи:\n\n"
                        f"📋 {parse_result['task']}\n"
                        f"⏰ Дедлайн: {parse_result['deadline'] or 'не указан'}\n\n"
                        f"Вы можете удалить задачу, если она создана ошибочно:",
                        reply_markup=keyboard_author.as_markup()
                    )

        reply = (
            f"🎤 **Встреча обработана!**\n\n"
            f"📝 **Задача:** {parse_result['task']}\n"
            f"⏰ **Дедлайн:** {parse_result['deadline'] or 'не указан'}\n"
            f"👥 **Ответственные:** {', '.join(assignee_usernames) if assignee_usernames else 'не назначены'}\n\n"
            f"✅ **Создано карточек в YouGile:** {len(created_tasks)}"
        )
        await bot.send_message(chat_id, reply, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Ошибка в process_meeting: {e}")
        await bot.send_message(chat_id, f"⚠️ Ошибка: {str(e)}")
    finally:
        if os.path.exists(temp_wav):
            os.remove(temp_wav)