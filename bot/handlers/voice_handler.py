import re
import os
import tempfile
import logging
import uuid
import requests  # добавлен для HEAD-запроса
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.utils.audio_utils import download_telegram_media, transcribe_media, cleanup_temp_file
from bot.utils.link_utils import extract_yadisk_direct_link, download_file_from_url
from bot.utils.parser import parse_task as regex_parse_task
from bot.utils.llm_parser import parse_task_with_llm
from bot.utils.date_utils import deadline_to_timestamp
from bot.utils.yougile_utils import create_yougile_task
from web.database import add_user, add_task, get_telegram_id_by_username, add_task_history

logger = logging.getLogger(__name__)
router = Router()
_CONFIDENCE_THRESHOLD = 70
_MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 МБ для Telegram-файлов
_MAX_DOWNLOAD_SIZE = 200 * 1024 * 1024  # 200 МБ для ссылок Яндекс.Диск


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


# ---------- Обработчик ссылок на Яндекс.Диск (только личные сообщения) ----------
@router.message(F.text, F.chat.type == "private")
async def handle_yadisk_link(message: Message, bot: Bot) -> None:
    text = message.text
    match = re.search(r'(https?://disk\.yandex\.(?:ru|com)/[^\s]+)', text)
    if not match:
        return

    url = match.group(1)
    await message.answer("🔗 Обнаружена ссылка на Яндекс.Диск. Получаю прямую ссылку для скачивания...")

    direct_link = extract_yadisk_direct_link(url)
    if not direct_link:
        await message.answer("❌ Не удалось получить прямую ссылку на файл. Убедитесь, что ссылка публичная и ведёт на файл.")
        return

    # Проверка размера файла перед скачиванием
    try:
        head_resp = requests.head(direct_link, timeout=10)
        if head_resp.status_code == 200:
            file_size = int(head_resp.headers.get('content-length', 0))
            if file_size > _MAX_DOWNLOAD_SIZE:
                await message.answer(f"❌ Файл слишком большой ({file_size // (1024*1024)} МБ). Максимальный размер для обработки: 200 МБ.")
                return
    except Exception as e:
        logger.warning(f"Не удалось проверить размер файла: {e}")

    temp_dir = tempfile.gettempdir()
    temp_filename = f"yadisk_{uuid.uuid4().hex}.tmp"
    temp_path = os.path.join(temp_dir, temp_filename)

    await message.answer("📥 Скачиваю файл (это может занять некоторое время)...")
    if not download_file_from_url(direct_link, temp_path):
        await message.answer("❌ Не удалось скачать файл. Проверьте ссылку и попробуйте снова.")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return

    file_size = os.path.getsize(temp_path)
    if file_size > 100 * 1024 * 1024:
        await message.answer(f"⚠️ Файл большой ({file_size // (1024*1024)} МБ). Обработка может занять несколько минут.")

    status_msg = await message.answer("🎙 Обрабатываю файл...")
    try:
        transcribed_text = transcribe_media(temp_path)
        if not transcribed_text:
            await status_msg.edit_text("❌ Не удалось распознать речь в файле.")
            return

        llm_result = parse_task_with_llm(transcribed_text)
        if llm_result and llm_result.get("confidence", 0) >= _CONFIDENCE_THRESHOLD:
            parse_result = llm_result
            logger.info(f"✅ Распознано через LLM: confidence={parse_result['confidence']}")
        else:
            parse_result = regex_parse_task(transcribed_text, known_usernames=[])
            logger.info(f"🔄 Fallback на regex: confidence={parse_result['confidence']}")

        if parse_result["confidence"] < _CONFIDENCE_THRESHOLD:
            await status_msg.edit_text(f"🔊 Я услышал:\n{transcribed_text}\n\nНе уверен, что это задача.")
            return

        assignee_usernames = parse_result.get("assignees", [])
        if not assignee_usernames:
            assignee_usernames = [None]

        author_id = message.from_user.id
        created_tasks = []  # для сбора информации о созданных задачах

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
            # Добавляем историю
            add_task_history(task_uuid, 'pending', comment='Задача создана из ссылки на Яндекс.Диск')

            # Отправка уведомлений (но не автору внутри цикла)
            if responsible_id != author_id:
                # Уведомление ответственному
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
            created_tasks.append((parse_result["task"], assignee_username, task_uuid))

        # Отправляем автору одно сводное сообщение
        if created_tasks:
            assignees_str = ', '.join([f"@{a}" if a else "вы" for _, a, _ in created_tasks])
            # Используем task_uuid первой задачи для кнопок (если только одна задача – нормально, если несколько – автору будет несколько сообщений, но лучше так)
            first_uuid = created_tasks[0][2]
            keyboard = InlineKeyboardBuilder()
            keyboard.button(text="❌ Удалить задачу", callback_data=f"cancel_task_{first_uuid}")
            keyboard.button(text="▶️ Взять в работу", callback_data=f"move_to_do_{first_uuid}")
            keyboard.button(text="✅ Завершить", callback_data=f"complete_task_{first_uuid}")
            keyboard.adjust(1)
            await bot.send_message(
                author_id,
                f"📌 Вы создали задачу из файла по ссылке:\n\n"
                f"📋 {parse_result['task']}\n"
                f"⏰ Дедлайн: {parse_result['deadline'] or 'не указан'}\n"
                f"👥 Ответственные: {assignees_str}\n\n"
                f"Управляйте задачей:",
                reply_markup=keyboard.as_markup()
            )

        reply_text = (
            f"✅ Задача автоматически создана в YouGile!\n\n"
            f"📋 {parse_result['task']}\n"
            f"⏰ Дедлайн: {parse_result['deadline'] or 'не указан'}\n"
            f"👥 Ответственные: {', '.join(assignee_usernames) if assignee_usernames and assignee_usernames[0] else 'не назначены'}"
        )
        await status_msg.edit_text(reply_text)
    except Exception as e:
        logger.error(f"Ошибка обработки ссылки: {e}")
        await status_msg.edit_text("⚠️ Произошла ошибка при обработке файла.")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# ---------- Обработчик медиафайлов из Telegram ----------
@router.message(F.voice | F.audio | F.video | F.video_note | F.document)
async def handle_media_message(message: Message, bot: Bot) -> None:
    add_user(message.from_user.id, message.from_user.username, message.from_user.full_name)

    file_size = 0
    if message.document:
        file_size = message.document.file_size
    elif message.video:
        file_size = message.video.file_size
    elif message.audio:
        file_size = message.audio.file_size
    elif message.voice:
        file_size = message.voice.file_size
    elif message.video_note:
        file_size = message.video_note.file_size

    if file_size > _MAX_FILE_SIZE:
        await message.answer(
            f"⚠️ Файл слишком большой ({file_size // (1024*1024)} МБ). "
            "Telegram ограничивает размер обрабатываемых файлов до 20 МБ.\n\n"
            "Для больших файлов загрузите их на Яндекс.Диск и отправьте мне публичную ссылку."
        )
        return

    if message.document:
        ext = message.document.file_name.split('.')[-1].lower()
        if ext not in ['webm', 'mp4', 'ogg', 'mp3', 'wav', 'aac', 'wma', 'avi', 'mov', 'mkv']:
            await message.answer("❌ Неподдерживаемый формат файла.")
            return

    status_msg = await message.answer("🎙 Обрабатываю медиафайл...")
    file_path = None
    try:
        file_path = await download_telegram_media(message, bot)
        transcribed_text = transcribe_media(file_path)
        if not transcribed_text:
            await status_msg.edit_text("❌ Не удалось распознать речь.")
            return

        llm_result = parse_task_with_llm(transcribed_text)
        if llm_result and llm_result.get("confidence", 0) >= _CONFIDENCE_THRESHOLD:
            parse_result = llm_result
        else:
            parse_result = regex_parse_task(transcribed_text, known_usernames=[])

        if parse_result["confidence"] < _CONFIDENCE_THRESHOLD:
            await status_msg.edit_text(f"🔊 Я услышал:\n{transcribed_text}\n\nНе уверен, что это задача.")
            return

        assignee_usernames = parse_result.get("assignees", []) or [None]
        author_id = message.from_user.id
        created_tasks = []

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
            add_task_history(task_uuid, 'pending', comment='Задача создана из медиафайла')

            if responsible_id != author_id:
                keyboard_worker = InlineKeyboardBuilder()
                keyboard_worker.button(text="▶️ Взять в работу", callback_data=f"move_to_do_{task_uuid}")
                keyboard_worker.button(text="✅ Завершить", callback_data=f"complete_task_{task_uuid}")
                keyboard_worker.adjust(1)
                await bot.send_message(
                    responsible_id,
                    f"🔔 Вам назначена задача из файла:\n\n"
                    f"📋 {parse_result['task']}\n"
                    f"⏰ Дедлайн: {parse_result['deadline'] or 'не указан'}\n\n"
                    f"Управляйте задачей:",
                    reply_markup=keyboard_worker.as_markup()
                )
            created_tasks.append((parse_result["task"], assignee_username, task_uuid))

        if created_tasks:
            assignees_str = ', '.join([f"@{a}" if a else "вы" for _, a, _ in created_tasks])
            first_uuid = created_tasks[0][2]
            keyboard = InlineKeyboardBuilder()
            keyboard.button(text="❌ Удалить задачу", callback_data=f"cancel_task_{first_uuid}")
            keyboard.button(text="▶️ Взять в работу", callback_data=f"move_to_do_{first_uuid}")
            keyboard.button(text="✅ Завершить", callback_data=f"complete_task_{first_uuid}")
            keyboard.adjust(1)
            await bot.send_message(
                author_id,
                f"📌 Вы создали задачу из файла:\n\n"
                f"📋 {parse_result['task']}\n"
                f"⏰ Дедлайн: {parse_result['deadline'] or 'не указан'}\n"
                f"👥 Ответственные: {assignees_str}\n\n"
                f"Управляйте задачей:",
                reply_markup=keyboard.as_markup()
            )

        reply_text = f"✅ Задача автоматически создана в YouGile!\n\n📋 {parse_result['task']}\n⏰ Дедлайн: {parse_result['deadline'] or 'не указан'}\n👥 Ответственные: {', '.join(assignee_usernames) if assignee_usernames[0] else 'не назначены'}"
        await status_msg.edit_text(reply_text)
    except Exception as e:
        logger.error(f"Ошибка в handle_media_message: {e}")
        await status_msg.edit_text("⚠️ Произошла ошибка.")
    finally:
        if file_path:
            cleanup_temp_file(file_path)