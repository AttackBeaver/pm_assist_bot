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

        tasks_list = None

        llm_result = parse_task_with_llm(transcribed_text)
        if llm_result and isinstance(llm_result, list) and len(llm_result) > 0:
            tasks_list = llm_result
            logger.info(f"Извлечено {len(tasks_list)} задач из транскрипции через LLM")

        if not tasks_list and summary:
            llm_from_summary = parse_task_with_llm(summary)
            if llm_from_summary and isinstance(llm_from_summary, list) and len(llm_from_summary) > 0:
                tasks_list = llm_from_summary
                logger.info(f"Извлечено {len(tasks_list)} задач из саммари через LLM")

        if not tasks_list:
            regex_result = regex_parse_task(transcribed_text, known_usernames=[])
            if regex_result["confidence"] >= 70:
                tasks_list = [regex_result]
                logger.info("Задача извлечена из транскрипции через regex")
            elif summary:
                regex_from_summary = regex_parse_task(summary, known_usernames=[])
                if regex_from_summary["confidence"] >= 70:
                    tasks_list = [regex_from_summary]
                    logger.info("Задача извлечена из саммари через regex")

        if not tasks_list:
            await bot.send_message(chat_id, "🔊 Не удалось выделить задачи.")
            return

        author_id = user_id
        all_created_tasks = []

        for parse_result in tasks_list:
            assignee_usernames = parse_result.get("assignees", []) or [None]

            for assignee in assignee_usernames:
                # ИЗМЕНЕНИЕ: ответственный по умолчанию None
                responsible_id = None
                if assignee:
                    clean = assignee.lstrip('@')
                    found_id = get_telegram_id_by_username(clean)
                    if found_id:
                        responsible_id = found_id

                assignee_ids = [responsible_id] if responsible_id else []
                card_id = await create_yougile_task(
                    title=parse_result["task"],
                    description=transcribed_text,
                    deadline_str=parse_result["deadline"],
                    assignee_user_ids=assignee_ids
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
                    all_created_tasks.append((parse_result["task"], assignee, task_uuid, responsible_id))

                    # Уведомления
                    assignee_str = f"@{assignee}" if assignee else "вы"
                    if responsible_id is None:
                        keyboard = InlineKeyboardBuilder()
                        keyboard.button(text="❌ Удалить задачу", callback_data=f"cancel_task_{task_uuid}")
                        keyboard.button(text="▶️ Взять в работу", callback_data=f"move_to_do_{task_uuid}")
                        keyboard.button(text="✅ Завершить", callback_data=f"complete_task_{task_uuid}")
                        keyboard.adjust(1)
                        await bot.send_message(
                            author_id,
                            f"📌 Вы создали задачу (без исполнителя) из встречи:\n\n"
                            f"📋 {parse_result['task']}\n"
                            f"⏰ Дедлайн: {parse_result['deadline'] or 'не указан'}\n\n"
                            f"Вы можете взять задачу в работу или назначить исполнителя в YouGile.",
                            reply_markup=keyboard.as_markup()
                        )
                    elif responsible_id == author_id:
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
                            f"🔔 Вам назначена задача из встречи:\n\n"
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

        if not all_created_tasks:
            await bot.send_message(chat_id, "❌ Не удалось создать задачи в YouGile.")
            return

        unique_assignees = set()
        for _, assignee, _, _ in all_created_tasks:
            if assignee:
                unique_assignees.add(f"@{assignee}")
        assignees_display = ', '.join(sorted(unique_assignees)) if unique_assignees else 'не назначены'

        reply = f"🎤 **Встреча обработана!**\n\n"
        reply += f"📝 **Задачи:**\n"
        for i, (task_title, assignee, _, responsible_id) in enumerate(all_created_tasks, 1):
            assignee_str = f"@{assignee}" if assignee else "не назначен"
            reply += f"{i}. {task_title} (ответственный: {assignee_str})\n"
        reply += f"\n👥 **Общие ответственные:** {assignees_display}\n"
        reply += f"✅ **Создано карточек в YouGile:** {len(all_created_tasks)}"
        await bot.send_message(chat_id, reply, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Ошибка в process_meeting: {e}")
        await bot.send_message(chat_id, f"⚠️ Ошибка: {str(e)}")
    finally:
        if os.path.exists(temp_wav):
            os.remove(temp_wav)