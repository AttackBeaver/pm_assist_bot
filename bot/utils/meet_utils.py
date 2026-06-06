import re
import os
import tempfile
import uuid
import logging
from aiogram import Bot
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.utils.link_utils import extract_yadisk_direct_link, download_file_from_url
from bot.utils.audio_utils import transcribe_media
from bot.utils.parser import parse_task as regex_parse_task
from bot.utils.llm_parser import parse_task_with_llm
from bot.utils.date_utils import deadline_to_timestamp
from bot.utils.yougile_utils import create_yougile_task
from web.database import add_task, get_telegram_id_by_username, add_user

logger = logging.getLogger(__name__)
_CONFIDENCE_THRESHOLD = 50


async def process_meet_link(url: str, message: Message, bot: Bot) -> bool:
    """
    Обрабатывает ссылку на Яндекс.Диск: получает прямую ссылку, скачивает,
    транскрибирует, парсит задачи и создаёт карточки в YouGile.
    Возвращает True, если обработка успешна, иначе False.
    """
    await message.answer("🔗 Обнаружена ссылка на Яндекс.Диск. Получаю прямую ссылку для скачивания...")
    direct_link = extract_yadisk_direct_link(url)
    if not direct_link:
        await message.answer("❌ Не удалось получить прямую ссылку на файл. Убедитесь, что ссылка публичная и ведёт на файл.")
        return False

    temp_dir = tempfile.gettempdir()
    temp_filename = f"yadisk_{uuid.uuid4().hex}.tmp"
    temp_path = os.path.join(temp_dir, temp_filename)

    await message.answer("📥 Скачиваю файл (это может занять некоторое время)...")
    if not download_file_from_url(direct_link, temp_path):
        await message.answer("❌ Не удалось скачать файл. Проверьте ссылку и попробуйте снова.")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return False

    file_size = os.path.getsize(temp_path)
    if file_size > 100 * 1024 * 1024:
        await message.answer(f"⚠️ Файл большой ({file_size // (1024*1024)} МБ). Обработка может занять несколько минут.")

    status_msg = await message.answer("🎙 Обрабатываю файл...")
    try:
        transcribed_text = transcribe_media(temp_path)
        if not transcribed_text:
            await status_msg.edit_text("❌ Не удалось распознать речь в файле.")
            return False

        # Гибридный парсинг
        llm_result = parse_task_with_llm(transcribed_text)
        if llm_result and llm_result.get("confidence", 0) >= _CONFIDENCE_THRESHOLD:
            parse_result = llm_result
            logger.info(f"✅ Распознано через LLM: confidence={parse_result['confidence']}")
        else:
            parse_result = regex_parse_task(transcribed_text, known_usernames=[])
            logger.info(f"🔄 Fallback на regex: confidence={parse_result['confidence']}")

        if parse_result["confidence"] < _CONFIDENCE_THRESHOLD:
            await status_msg.edit_text(f"🔊 Я услышал:\n{transcribed_text}\n\nНе уверен, что это задача.")
            return False

        assignee_usernames = parse_result.get("assignees", [])
        if not assignee_usernames:
            assignee_usernames = [None]

        author_id = message.from_user.id
        # Регистрируем автора
        add_user(author_id, username=message.from_user.username, full_name=message.from_user.full_name)

        for assignee_username in assignee_usernames:
            responsible_id = author_id
            if assignee_username:
                clean = assignee_username.lstrip('@')
                found_id = get_telegram_id_by_username(clean)
                if found_id:
                    responsible_id = found_id
                else:
                    # Если не найден, всё равно назначаем автору
                    pass

            card_id = await create_yougile_task(
                title=parse_result["task"],
                description=transcribed_text,
                deadline_str=parse_result["deadline"],
            )
            if not card_id:
                await status_msg.edit_text("❌ Не удалось создать задачу в YouGile.")
                return False

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

            # Отправка уведомлений
            if responsible_id == author_id:
                keyboard = InlineKeyboardBuilder()
                keyboard.button(text="❌ Удалить задачу", callback_data=f"cancel_task_{task_uuid}")
                keyboard.button(text="▶️ Взять в работу", callback_data=f"move_to_do_{task_uuid}")
                keyboard.button(text="✅ Завершить", callback_data=f"complete_task_{task_uuid}")
                keyboard.adjust(1)
                await bot.send_message(
                    author_id,
                    f"📌 Вы создали задачу из файла по ссылке:\n\n"
                    f"📋 {parse_result['task']}\n"
                    f"⏰ Дедлайн: {parse_result['deadline'] or 'не указан'}\n"
                    f"👥 Ответственные: {', '.join(assignee_usernames) if assignee_usernames[0] else 'вы'}\n\n"
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
                    f"🔔 Вам назначена задача из файла (по ссылке):\n\n"
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
                    f"📌 Вы создали задачу для @{assignee_username} из файла по ссылке:\n\n"
                    f"📋 {parse_result['task']}\n"
                    f"⏰ Дедлайн: {parse_result['deadline'] or 'не указан'}\n\n"
                    f"Вы можете удалить задачу, если она создана ошибочно:",
                    reply_markup=keyboard_author.as_markup()
                )

        reply_text = (
            f"✅ Задача автоматически создана в YouGile!\n\n"
            f"📋 {parse_result['task']}\n"
            f"⏰ Дедлайн: {parse_result['deadline'] or 'не указан'}\n"
            f"👥 Ответственные: {', '.join(assignee_usernames) if assignee_usernames and assignee_usernames[0] else 'не назначены'}"
        )
        await status_msg.edit_text(reply_text)
        return True
    except Exception as e:
        logger.error(f"Ошибка обработки ссылки: {e}")
        await status_msg.edit_text("⚠️ Произошла ошибка при обработке файла.")
        return False
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)