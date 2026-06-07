import asyncio
import logging
from datetime import datetime, timedelta
import os
import re
from typing import Optional

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from config import WEB_BASE_URL, YOUGILE_DO_COLUMN_ID, YOUGILE_DONE_COLUMN_ID, YOUGILE_TOKEN
from web.database import (
    add_user, complete_task, get_task_by_id, set_user_away, clear_user_away,
    get_tasks_by_user, get_user_stats, get_average_completion_time,
    add_task_history
)
from yougile_client import YouGileClient

from bot.utils.audio_utils import transcribe_media
from bot.utils.llm_parser import parse_task_with_llm
from bot.utils.date_utils import deadline_to_timestamp
from bot.utils.yougile_utils import create_yougile_task
from web.database import add_task, get_telegram_id_by_username
import uuid
import tempfile
from bot.utils.parser import parse_task as regex_parse_task
from bot.utils.mymeet_client import MyMeetClient

logger = logging.getLogger(__name__)
router = Router()

try:
    from bot.utils.meet_automation import join_and_record_meet
    MEET_AUTOMATION_AVAILABLE = True
except ImportError:
    MEET_AUTOMATION_AVAILABLE = False
    logger.warning("Playwright не установлен. Автоматическое подключение через Playwright недоступно.")
    join_and_record_meet = None


def _main_keyboard() -> ReplyKeyboardMarkup:
    """Главная клавиатура с обновлёнными кнопками."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📋 Мои задачи"),
                KeyboardButton(text="🌐 Личный кабинет"),
            ],
            [
                KeyboardButton(text="🚫 Недоступен"),
                KeyboardButton(text="✅ Доступен"),
            ],
            [
                KeyboardButton(text="👨‍💼 Тест менеджера"),
                KeyboardButton(text="👷 Тест исполнителя"),
            ],
            [
                KeyboardButton(text="📞 Встреча"),
                KeyboardButton(text="❓ Помощь"),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие или напишите сообщение...",
    )


def _cabinet_url_text(telegram_id: int) -> str:
    return f"{WEB_BASE_URL}/cabinet/{telegram_id}"


def _cabinet_inline(telegram_id: int) -> Optional[InlineKeyboardMarkup]:
    url = _cabinet_url_text(telegram_id)
    if "localhost" in WEB_BASE_URL or "127.0.0.1" in WEB_BASE_URL:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🌐 Открыть веб-кабинет", url=url)
    ]])


# ---------- Основные команды ----------
@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    add_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    await message.answer(
        "Привет! Я PM‑Assist Bot 👋\n\n"
        "Помогаю превращать сообщения в задачи.\n"
        "Добавь меня в групповой чат — я буду автоматически распознавать задачи, "
        "дедлайны и ответственных, а также обрабатывать голосовые сообщения.\n\n"
        "Используй кнопки ниже для управления 👇",
        reply_markup=_main_keyboard(),
    )


@router.message(Command("help"))
@router.message(F.text == "❓ Помощь")
async def cmd_help(message: Message) -> None:
    await message.answer(
        "📌 Как я работаю:\n"
        "• В групповом чате читаю сообщения и ищу задачи\n"
        "• Если нахожу — автоматически создаю карточку в YouGile\n"
        "• Голосовые сообщения и видео тоже распознаю\n"
        "• Напоминаю о дедлайнах и присылаю вечерний дайджест\n\n"

        "📋 Управление задачами:\n"
        "/tasks — список ваших активных задач с номерами\n"
        "/move [номер] [колонка] — переместить задачу\n"
        "/complete [номер] — завершить задачу\n"
        "/cabinet — личный кабинет (статистика, достижения)\n\n"

        "📊 Статистика и мотивация:\n"
        "/stats — ваша статистика\n"
        "/achievements — достижения\n"
        "/deadlines — ближайшие дедлайны\n"
        "/recommendations — рекомендации по развитию\n\n"

        "🎙 Встречи и расшифровка:\n"
        "Нажмите кнопку «📞 Встреча» для выбора способа обработки записи встречи.\n\n"

        "🛠 Настройки:\n"
        "/away [причина] — временно отключить назначение задач\n"
        "/back — снова доступен для задач",
        reply_markup=_main_keyboard()
    )


@router.message(Command("tasks"))
@router.message(F.text == "📋 Мои задачи")
async def cmd_tasks(message: Message) -> None:
    tasks = get_tasks_by_user(message.from_user.id, status="pending")
    if not tasks:
        await message.answer("✨ У вас нет активных задач.")
        return

    builder = InlineKeyboardBuilder()
    for task in tasks:
        title = task['title'][:40] + "..." if len(task['title']) > 40 else task['title']
        deadline = f" (до {task['deadline']})" if task.get('deadline') else ""
        builder.button(text=f"{title}{deadline}", callback_data=f"manage_task_{task['id']}")
    builder.adjust(1)

    await message.answer(
        "📋 **Ваши активные задачи**\n\nВыберите задачу для управления:",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )


@router.message(Command("cabinet"))
@router.message(F.text == "🌐 Личный кабинет")
async def cmd_cabinet(message: Message) -> None:
    uid = message.from_user.id
    stats = get_user_stats(uid)
    avg_time = get_average_completion_time(uid)
    tasks_total = len(get_tasks_by_user(uid))
    tasks_completed = len([t for t in get_tasks_by_user(uid) if t["status"] == "completed"])
    tasks_pending = tasks_total - tasks_completed

    text = (
        f"👤 **Ваш профиль**\n\n"
        f"✨ **Опыт (XP):** {stats['xp']}\n"
        f"🧙 **Уровень:** {stats['level']}\n"
        f"📋 **Всего задач:** {tasks_total}\n"
        f"🟢 **В работе:** {tasks_pending}\n"
        f"✅ **Выполнено:** {tasks_completed}\n"
        f"⏱ **Среднее время выполнения:** {avg_time:.1f} ч" if avg_time else "⏱ **Среднее время выполнения:** —"
    )

    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Детальная статистика", callback_data="cabinet_stats"),
            InlineKeyboardButton(text="🏆 Достижения", callback_data="cabinet_achievements"),
        ],
        [
            InlineKeyboardButton(text="📚 Рекомендации", callback_data="cabinet_recommendations"),
            InlineKeyboardButton(text="⏰ Ближайшие дедлайны", callback_data="cabinet_deadlines"),
        ],
    ])
    web_inline = _cabinet_inline(uid)
    if web_inline:
        inline_kb.inline_keyboard.append(web_inline.inline_keyboard[0])

    await message.answer(text, parse_mode="Markdown", reply_markup=inline_kb)


# Обработчики инлайн-кнопок из личного кабинета
@router.callback_query(lambda c: c.data == "cabinet_stats")
async def cabinet_stats_callback(callback: CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    stats = get_user_stats(uid)
    avg_time = get_average_completion_time(uid)
    tasks_total = len(get_tasks_by_user(uid))
    tasks_completed = len([t for t in get_tasks_by_user(uid) if t["status"] == "completed"])
    tasks_pending = tasks_total - tasks_completed

    text = (
        f"📊 **Детальная статистика**\n\n"
        f"✨ XP: {stats['xp']}\n"
        f"🧙 Уровень: {stats['level']}\n"
        f"📋 Всего задач: {tasks_total}\n"
        f"🟢 В работе: {tasks_pending}\n"
        f"✅ Выполнено: {tasks_completed}\n"
        f"⏱ Среднее время выполнения: {avg_time:.1f} ч" if avg_time else "⏱ Среднее время выполнения: —"
    )
    await callback.message.answer(text, parse_mode="Markdown")


@router.callback_query(lambda c: c.data == "cabinet_achievements")
async def cabinet_achievements_callback(callback: CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    stats = get_user_stats(uid)
    achievements = stats.get("achievements", [])
    if not achievements:
        text = "🏆 У вас пока нет достижений.\n\nВыполняйте задачи, чтобы получать ачивки:\n• 🎯 Первая задача\n• ⚡ Спринтер (3 задачи)\n• 🧙‍♂️ Мастер (2 уровень)"
    else:
        lines = ["🏆 **Ваши достижения**:\n"]
        for ach in achievements:
            icon = "🏆"
            if "Первая" in ach:
                icon = "🎯"
            elif "Спринтер" in ach:
                icon = "⚡"
            elif "Мастер" in ach:
                icon = "🧙"
            lines.append(f"{icon} {ach}")
        text = "\n".join(lines)
    await callback.message.answer(text, parse_mode="Markdown")


@router.callback_query(lambda c: c.data == "cabinet_recommendations")
async def cabinet_recommendations_callback(callback: CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    tasks = get_tasks_by_user(uid, status="completed")
    if not tasks:
        text = "📚 У вас пока нет выполненных задач. Сначала выполните несколько задач, чтобы получить рекомендации."
    else:
        all_text = " ".join([t["title"].lower() for t in tasks])
        recommendations = []
        if re.search(r'аналитик|анализ|отчет|отчёт|дашборд', all_text):
            recommendations.append("📊 Аналитика данных – курс 'Основы SQL и визуализация'")
        if re.search(r'python|код|программирование|скрипт', all_text):
            recommendations.append("🐍 Python – курс 'Автоматизация рутинных задач'")
        if re.search(r'управление|проект|менеджмент|agile|scrum', all_text):
            recommendations.append("📈 Управление проектами – курс 'Agile и Scrum для PM'")
        if re.search(r'коммуникация|презентация|выступление', all_text):
            recommendations.append("🗣️ Коммуникации – курс 'Эффективные презентации'")
        if re.search(r'баг|bug|дефект', all_text):
            recommendations.append("🐞 Тестирование – курс 'Основы QA и баг-трекинг'")
        if re.search(r'сервер|деплой|инфраструктура', all_text):
            recommendations.append("☁️ DevOps – курс 'Введение в CI/CD и контейнеризацию'")
        if not recommendations:
            recommendations = ["🧠 Тайм-менеджмент – курс 'Как успевать больше'", "🎯 Постановка целей – курс 'SMART и OKR'"]
        text = "📚 **Рекомендации по развитию:**\n\n" + "\n".join(recommendations)
    await callback.message.answer(text, parse_mode="Markdown")


@router.callback_query(lambda c: c.data == "cabinet_deadlines")
async def cabinet_deadlines_callback(callback: CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    tasks = get_tasks_by_user(uid, status="pending")
    upcoming = [t for t in tasks if t.get("deadline") and t["deadline"] != "Не указан"]
    if not upcoming:
        text = "⏰ У вас нет запланированных дедлайнов.\nСоздайте задачу с указанием срока."
    else:
        try:
            upcoming.sort(key=lambda x: datetime.strptime(x["deadline"], "%Y-%m-%d") if x["deadline"] else datetime.max)
        except:
            pass
        lines = ["⏰ **Ближайшие дедлайны** (первые 5):\n"]
        for i, t in enumerate(upcoming[:5], 1):
            lines.append(f"{i}. **{t['title']}** — до {t['deadline']}")
        text = "\n".join(lines)
    await callback.message.answer(text, parse_mode="Markdown")


# ---------- Остальные команды ----------
@router.message(Command("away"))
@router.message(F.text == "🚫 Недоступен")
async def cmd_away(message: Message) -> None:
    if message.text.startswith("/away"):
        args = message.text.split(maxsplit=1)
        reason = args[1] if len(args) > 1 else "Не указана"
    else:
        reason = "Не указана"

    until = datetime.now() + timedelta(days=7)
    set_user_away(message.from_user.id, reason, until)
    await message.answer(
        f"🚫 Вы отмечены как недоступный.\n"
        f"Причина: {reason}\n"
        f"До: {until.strftime('%d.%m.%Y %H:%M')}\n\n"
        "Задачи не будут назначаться на вас. Нажмите ✅ Доступен для возврата.",
        reply_markup=_main_keyboard(),
    )


@router.message(Command("back"))
@router.message(F.text == "✅ Доступен")
async def cmd_back(message: Message) -> None:
    clear_user_away(message.from_user.id)
    await message.answer(
        "✅ Вы снова доступны для задач.",
        reply_markup=_main_keyboard(),
    )


@router.message(Command("stats"))
@router.message(F.text == "📊 Статистика")
async def cmd_stats(message: Message) -> None:
    uid = message.from_user.id
    stats = get_user_stats(uid)
    avg_time = get_average_completion_time(uid)
    tasks_total = len(get_tasks_by_user(uid))
    tasks_completed = len([t for t in get_tasks_by_user(uid) if t["status"] == "completed"])
    tasks_pending = tasks_total - tasks_completed

    msg = (
        f"📊 **Ваша статистика**\n\n"
        f"✨ Опыт (XP): **{stats['xp']}**\n"
        f"🧙‍♂️ Уровень: **{stats['level']}**\n"
        f"📋 Всего задач: **{tasks_total}**\n"
        f"🟢 В работе: **{tasks_pending}**\n"
        f"✅ Выполнено: **{tasks_completed}**\n"
        f"⏱ Среднее время выполнения: **{avg_time:.1f} ч**" if avg_time else "⏱ Среднее время выполнения: **—**"
    )
    await message.answer(msg, parse_mode="Markdown", reply_markup=_main_keyboard())


@router.message(Command("achievements"))
@router.message(F.text == "🏆 Достижения")
async def cmd_achievements(message: Message) -> None:
    uid = message.from_user.id
    stats = get_user_stats(uid)
    achievements = stats.get("achievements", [])
    if not achievements:
        await message.answer(
            "🏆 У вас пока нет достижений.\n\n"
            "Выполняйте задачи, чтобы получать ачивки:\n"
            "• 🎯 Первая задача — создать первую задачу\n"
            "• ⚡ Спринтер — выполнить 3 задачи\n"
            "• 🧙‍♂️ Мастер — достичь 2 уровня (200 XP)",
            reply_markup=_main_keyboard()
        )
        return
    lines = ["🏆 **Ваши достижения**:\n"]
    for ach in achievements:
        icon = "🏆"
        if "Первая" in ach:
            icon = "🎯"
        elif "Спринтер" in ach:
            icon = "⚡"
        elif "Мастер" in ach:
            icon = "🧙"
        lines.append(f"{icon} {ach}")
    await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=_main_keyboard())


@router.message(Command("deadlines"))
@router.message(F.text == "⏰ Ближайшие дедлайны")
async def cmd_deadlines(message: Message) -> None:
    uid = message.from_user.id
    tasks = get_tasks_by_user(uid, status="pending")
    upcoming = [t for t in tasks if t.get("deadline") and t["deadline"] != "Не указан"]
    if not upcoming:
        await message.answer(
            "⏰ У вас нет запланированных дедлайнов.\n"
            "Создайте задачу с указанием срока (например, «сделать отчёт до пятницы»).",
            reply_markup=_main_keyboard()
        )
        return
    try:
        upcoming.sort(key=lambda x: datetime.strptime(x["deadline"], "%Y-%m-%d") if x["deadline"] else datetime.max)
    except:
        pass
    lines = ["⏰ **Ближайшие дедлайны** (первые 5):\n"]
    for i, t in enumerate(upcoming[:5], 1):
        lines.append(f"{i}. **{t['title']}** — до {t['deadline']}")
    await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=_main_keyboard())


@router.message(Command("recommendations"))
@router.message(F.text == "📚 Рекомендации")
async def cmd_recommendations(message: Message):
    uid = message.from_user.id
    tasks = get_tasks_by_user(uid, status="completed")
    if not tasks:
        await message.answer(
            "📚 У вас пока нет выполненных задач. Сначала выполните несколько задач, чтобы получить персонализированные рекомендации.",
            reply_markup=_main_keyboard()
        )
        return

    all_text = " ".join([t["title"].lower() for t in tasks])
    recommendations = []

    if re.search(r'аналитик|анализ|отчет|отчёт|дашборд', all_text):
        recommendations.append("📊 Аналитика данных – курс 'Основы SQL и визуализация'")
    if re.search(r'python|код|программирование|скрипт', all_text):
        recommendations.append("🐍 Python – курс 'Автоматизация рутинных задач'")
    if re.search(r'управление|проект|менеджмент|agile|scrum', all_text):
        recommendations.append("📈 Управление проектами – курс 'Agile и Scrum для PM'")
    if re.search(r'коммуникация|презентация|выступление', all_text):
        recommendations.append("🗣️ Коммуникации – курс 'Эффективные презентации'")
    if re.search(r'баг|bug|дефект', all_text):
        recommendations.append("🐞 Тестирование – курс 'Основы QA и баг-трекинг'")
    if re.search(r'сервер|деплой|инфраструктура', all_text):
        recommendations.append("☁️ DevOps – курс 'Введение в CI/CD и контейнеризацию'")

    if not recommendations:
        recommendations = [
            "🧠 Тайм-менеджмент – курс 'Как успевать больше'",
            "🎯 Постановка целей – курс 'SMART и OKR'"
        ]

    answer = "📚 **Рекомендации по развитию:**\n\n" + "\n".join(recommendations)
    await message.answer(answer, parse_mode="Markdown", reply_markup=_main_keyboard())


# ---------- Команды move, complete ----------
@router.message(Command("move"))
async def cmd_move(message: Message):
    args = message.text.split()
    if len(args) < 3:
        await message.answer(
            "ℹ️ Используйте: `/move <номер задачи> <колонка>`\n"
            "Номер задачи можно посмотреть командой `/tasks`.\n"
            "Доступные колонки: `В процессе`, `Готово`\n"
            "Пример: `/move 2 В процессе`",
            parse_mode="Markdown"
        )
        return

    try:
        idx = int(args[1]) - 1
        column_name = ' '.join(args[2:]).lower()

        tasks = get_tasks_by_user(message.from_user.id, status="pending")
        if not tasks:
            await message.answer("✨ У вас нет активных задач.")
            return
        if idx < 0 or idx >= len(tasks):
            await message.answer(f"❌ Задача с номером {idx+1} не найдена. Команда `/tasks` покажет актуальный список.", parse_mode="Markdown")
            return

        task = tasks[idx]
        yougile_card_id = task.get("yougile_card_id")
        if not yougile_card_id:
            await message.answer("❌ У этой задачи нет карточки в YouGile.")
            return

        if "процесс" in column_name or "do" in column_name:
            column_id = YOUGILE_DO_COLUMN_ID
        elif "готово" in column_name or "done" in column_name:
            column_id = YOUGILE_DONE_COLUMN_ID
        else:
            await message.answer("❌ Неизвестная колонка. Доступные: `В процессе`, `Готово`", parse_mode="Markdown")
            return

        client = YouGileClient(YOUGILE_TOKEN)
        success = client.move_task(yougile_card_id, column_id)
        if success:
            if column_id == YOUGILE_DONE_COLUMN_ID:
                add_task_history(task["id"], 'completed', status_from=task["status"], comment='Завершено через /move')
                complete_task(task["id"])
                await message.answer(f"✅ Задача «{task['title']}» завершена и перемещена в «Готово».")
            else:
                add_task_history(task["id"], 'in_progress', status_from=task["status"], comment='Перемещено в работу через /move')
                await message.answer(f"✅ Задача «{task['title']}» перемещена в «{column_name.capitalize()}».")
        else:
            await message.answer("❌ Не удалось переместить задачу. Проверьте настройки YouGile.")
    except ValueError:
        await message.answer("❌ Неверный формат номера. Пример: `/move 2 В процессе`", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка в /move: {e}")
        await message.answer("⚠️ Произошла ошибка при перемещении задачи.")


@router.message(Command("complete"))
async def cmd_complete(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "ℹ️ Используйте: `/complete <номер задачи>`\n"
            "Номер задачи можно посмотреть командой `/tasks`.\n"
            "Пример: `/complete 2`",
            parse_mode="Markdown"
        )
        return

    try:
        idx = int(args[1]) - 1
        tasks = get_tasks_by_user(message.from_user.id, status="pending")
        if not tasks:
            await message.answer("✨ У вас нет активных задач.")
            return
        if idx < 0 or idx >= len(tasks):
            await message.answer(f"❌ Задача с номером {idx+1} не найдена.")
            return

        task = tasks[idx]
        yougile_card_id = task.get("yougile_card_id")
        if not yougile_card_id:
            await message.answer("❌ У этой задачи нет карточки в YouGile.")
            return

        client = YouGileClient(YOUGILE_TOKEN)
        success = client.move_task(yougile_card_id, YOUGILE_DONE_COLUMN_ID)
        
        if success:
            add_task_history(task["id"], 'completed', status_from=task["status"], comment='Завершено через /complete')
            complete_task(task["id"])
            await message.answer(f"✅ Задача «{task['title']}» завершена и перемещена в «Готово».")
        else:
            await message.answer("❌ Не удалось завершить задачу.")
    except ValueError:
        await message.answer("❌ Неверный формат номера. Пример: `/complete 2`")
    except Exception as e:
        logger.error(f"Ошибка в /complete: {e}")
        await message.answer("⚠️ Произошла ошибка при завершении задачи.")


# ---------- Обработка встреч (меню выбора) ----------
@router.message(Command("join_meet"))
@router.message(F.text == "📞 Встреча")
async def cmd_join_meet(message: Message, bot: Bot) -> None:
    """Показывает меню выбора способа обработки встречи."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎙 Загрузить аудио/видео файл", callback_data="meet_upload_file")],
        [InlineKeyboardButton(text="🔗 Ссылка на Яндекс.Диск", callback_data="meet_yadisk")],
        [InlineKeyboardButton(text="🤖 Автоподключение через mymeet.ai", callback_data="meet_mymeet")],
        [InlineKeyboardButton(text="🎧 Автоподключение (Playwright)", callback_data="meet_playwright")],
    ])
    await message.answer(
        "Выберите способ обработки встречи:\n\n"
        "• **Загрузить файл** – отправьте аудио/видео запись (работает всегда)\n"
        "• **Ссылка на Яндекс.Диск** – укажите публичную ссылку на файл\n"
        "• **mymeet.ai** – автоматическое подключение (требует API-ключ)\n"
        "• **Playwright** – автономное подключение (требует выделенный сервер с PulseAudio)",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


@router.callback_query(lambda c: c.data == "meet_upload_file")
async def meet_upload_file_callback(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "🎙 **Отправьте мне аудио или видео файл**\n\n"
        "Поддерживаются форматы: MP3, WAV, OGG, MP4, WEBM, AVI, MOV, MKV и др.\n\n"
        "Я распознаю речь, выделю задачи, дедлайны и ответственных, "
        "создам карточки в YouGile и отправлю уведомления.\n\n"
        "Просто отправьте файл в этот чат."
    )


@router.callback_query(lambda c: c.data == "meet_yadisk")
async def meet_yadisk_callback(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "🔗 **Отправьте публичную ссылку на Яндекс.Диск**\n\n"
        "Ссылка должна вести на аудио или видео файл.\n"
        "Пример: `https://disk.yandex.ru/i/xxxxx`\n\n"
        "Я скачаю файл, распознаю речь, выделю задачи и создам карточки в YouGile."
    )


@router.callback_query(lambda c: c.data == "meet_mymeet")
async def meet_mymeet_callback(callback: CallbackQuery):
    await callback.answer()
    mymeet = MyMeetClient()
    if not mymeet.is_available():
        await callback.message.edit_text(
            "⚠️ **Автоматическое подключение через mymeet.ai требует настройки**\n\n"
            "Для использования этой функции необходимо:\n"
            "1. Заключить корпоративный договор с сервисом [mymeet.ai](https://mymeet.ai)\n"
            "2. Получить API‑ключ и указать его в переменной окружения `MYMEET_API_KEY`\n\n"
            "После этого бот сможет автоматически подключаться к встречам на "
            "Яндекс Телемост, Zoom, Google Meet, Microsoft Teams и др.\n\n"
            "**Альтернатива (уже работает):** загрузите запись встречи файлом или ссылкой.",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
        return
    # Если ключ есть – запускаем интеграцию
    await callback.message.edit_text(
        "🤖 **Автоматическое подключение через mymeet.ai**\n\n"
        "Отправьте ссылку на встречу в формате:\n"
        "`/join_meet https://telemost.yandex.ru/... 300`\n\n"
        "Где `300` – длительность записи в секундах (по умолчанию 300).\n\n"
        "Поддерживаются: Яндекс Телемост, Zoom, Google Meet, Microsoft Teams, TrueConf, Jitsi."
    )


@router.callback_query(lambda c: c.data == "meet_playwright")
async def meet_playwright_callback(callback: CallbackQuery):
    await callback.answer()
    if not MEET_AUTOMATION_AVAILABLE:
        await callback.message.edit_text(
            "⚠️ **Автоматическое подключение через Playwright недоступно**\n\n"
            "Этот модуль требует выделенного сервера с установленным PulseAudio "
            "и доступом к звуковому устройству (loopback).\n\n"
            "На текущем хостинге функция отключена.\n\n"
            "**Альтернатива:** загрузите запись встречи файлом или ссылкой на Яндекс.Диск."
        )
        return
    await callback.message.edit_text(
        "🎧 **Автоматическое подключение через Playwright + ffmpeg**\n\n"
        "Отправьте ссылку на встречу в формате:\n"
        "`/join_meet_auto https://telemost.yandex.ru/... 120`\n\n"
        "Бот откроет браузер, подключится к встрече, запишет звук, распознает речь и создаст задачи.\n\n"
        "⚠️ Требуется сервер с PulseAudio и X11 (или XVFB)."
    )


# ---------- Старый обработчик для Playwright (сохранён) ----------
@router.message(Command("join_meet_auto"))
async def cmd_join_meet_auto(message: Message, bot: Bot):
    """Альтернативная команда для прямого вызова Playwright (только для продвинутых)."""
    if not MEET_AUTOMATION_AVAILABLE:
        await message.answer("❌ Playwright автоматизация недоступна на этом сервере.")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Используйте: `/join_meet_auto <ссылка> [длительность]`")
        return
    meet_url = args[1]
    duration = 120
    if len(args) > 2 and args[2].isdigit():
        duration = int(args[2])
    await message.answer(f"🎧 Подключаюсь к встрече `{meet_url}` на {duration} сек...")
    asyncio.create_task(process_auto_meet(meet_url, duration, message, bot))


async def process_auto_meet(meet_url: str, duration: int, original_message: Message, bot: Bot):
    chat_id = original_message.chat.id
    user_id = original_message.from_user.id
    temp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    if 'PULSE_SERVER' not in os.environ:
        os.environ['PULSE_SERVER'] = 'unix:/var/run/pulse/native'
    logger.info(f"PULSE_SERVER = {os.environ.get('PULSE_SERVER', 'не задан')}")
    try:
        await original_message.answer("🎧 Подключаюсь и начинаю запись...")
        success = await join_and_record_meet(meet_url, duration, temp_wav)
        if not success:
            await bot.send_message(chat_id, "❌ Не удалось захватить звук. Возможно, модуль loopback PulseAudio не загружен или нет прав.")
            return
        await original_message.answer("🔊 Распознаю речь...")
        transcribed_text = transcribe_media(temp_wav)
        if not transcribed_text:
            await bot.send_message(chat_id, "❌ Не удалось распознать речь в записи.")
            return
        parse_result = parse_task_with_llm(transcribed_text)
        if not parse_result or parse_result.get("confidence", 0) < 50:
            parse_result = regex_parse_task(transcribed_text, known_usernames=[])
        if not parse_result or parse_result.get("confidence", 0) < 50:
            await bot.send_message(chat_id, "🔊 Не удалось выделить задачи. Возможно, встреча не содержала задач.")
            return
        assignee_usernames = parse_result.get("assignees", [])
        if not assignee_usernames:
            assignee_usernames = [None]
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
                add_task_history(task_uuid, 'pending', comment='Задача создана из встречи (Playwright)')
                created_tasks.append((parse_result["task"], assignee))
        reply = (
            f"🎤 **Встреча обработана!**\n\n"
            f"📝 **Задача:** {parse_result['task']}\n"
            f"⏰ **Дедлайн:** {parse_result['deadline'] or 'не указан'}\n"
            f"👥 **Ответственные:** {', '.join(assignee_usernames) if assignee_usernames else 'не назначены'}\n\n"
            f"✅ **Создано карточек в YouGile:** {len(created_tasks)}"
        )
        await bot.send_message(chat_id, reply, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка в process_auto_meet: {e}")
        await bot.send_message(chat_id, f"⚠️ Произошла ошибка: {str(e)}")
    finally:
        if os.path.exists(temp_wav):
            os.remove(temp_wav)


# ---------- Тестовые сценарии ----------
class ManagerTest(StatesGroup):
    step_1_created = State()
    step_2_moved = State()
    step_3_completed = State()

class ExecutorTest(StatesGroup):
    step_1_created = State()
    step_2_taken = State()
    step_3_completed = State()


@router.message(F.text == "👨‍💼 Тест менеджера")
async def start_manager_test(message: Message, state: FSMContext):
    uid = message.from_user.id
    add_user(uid, message.from_user.username, message.from_user.full_name)
    
    task_title = "Подготовить отчёт по итогам спринта"
    task_desc = "Собрать метрики, сделать выводы, презентацию. Дедлайн: пятница 18:00"
    deadline_str = "пятница 18:00"
    deadline_ts = deadline_to_timestamp(deadline_str)
    
    card_id = await create_yougile_task(task_title, task_desc, deadline_str)
    task_uuid = str(uuid.uuid4())
    add_task(
        task_id=task_uuid,
        title=task_title,
        description=task_desc,
        responsible_telegram_id=uid,
        author_telegram_id=uid,
        deadline=deadline_str,
        deadline_timestamp=deadline_ts,
        yougile_card_id=card_id,
        chat_id=message.chat.id,
    )
    add_task_history(task_uuid, 'pending', comment='Создано в тесте менеджера')
    
    await message.answer(
        f"✅ **Шаг 1/3**\n\n"
        f"Создана задача:\n"
        f"📋 {task_title}\n"
        f"⏰ {deadline_str}\n"
        f"👤 Вы – ответственный.\n\n"
        f"Нажмите «Далее», чтобы взять задачу в работу.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➡️ Далее", callback_data="manager_test_next_1")]
        ])
    )
    await state.set_state(ManagerTest.step_1_created)
    await state.update_data(task_id=task_uuid, title=task_title)


@router.callback_query(ManagerTest.step_1_created, lambda c: c.data == "manager_test_next_1")
async def manager_test_step2(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    task_id = data["task_id"]
    task_title = data["title"]
    
    task = get_task_by_id(task_id)
    if task and task.get("yougile_card_id") and YOUGILE_TOKEN and YOUGILE_DO_COLUMN_ID:
        client = YouGileClient(YOUGILE_TOKEN)
        client.move_task(task["yougile_card_id"], YOUGILE_DO_COLUMN_ID)
    add_task_history(task_id, 'in_progress', status_from='pending', comment='Взято в работу')
    
    await callback.message.edit_text(
        f"✅ **Шаг 2/3**\n\n"
        f"Задача «{task_title}» перемещена в колонку «В процессе».\n"
        f"Теперь завершите её (нажмите «Далее»).",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➡️ Далее", callback_data="manager_test_next_2")]
        ])
    )
    await state.set_state(ManagerTest.step_2_moved)
    await callback.answer()


@router.callback_query(ManagerTest.step_2_moved, lambda c: c.data == "manager_test_next_2")
async def manager_test_step3(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    task_id = data["task_id"]
    task_title = data["title"]
    
    task = get_task_by_id(task_id)
    if task and task.get("yougile_card_id") and YOUGILE_TOKEN and YOUGILE_DONE_COLUMN_ID:
        client = YouGileClient(YOUGILE_TOKEN)
        client.move_task(task["yougile_card_id"], YOUGILE_DONE_COLUMN_ID)
    complete_task(task_id)
    
    stats = get_user_stats(callback.from_user.id)
    xp = stats["xp"]
    level = stats["level"]
    achievements = stats.get("achievements", [])
    ach_text = "\n".join([f"🏆 {a}" for a in achievements]) if achievements else "Пока нет"
    
    await callback.message.edit_text(
        f"✅ **Шаг 3/3 – Тест завершён!**\n\n"
        f"Задача «{task_title}» выполнена.\n"
        f"✨ Ваш опыт: {xp} XP, уровень {level}\n\n"
        f"🏅 Достижения:\n{ach_text}\n\n"
        f"Вы можете проверить задачи командой /tasks или зайти в личный кабинет.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Мои задачи", callback_data="user_tasks")]
        ])
    )
    await state.clear()
    await callback.answer()


@router.message(F.text == "👷 Тест исполнителя")
async def start_executor_test(message: Message, state: FSMContext):
    executor_id = message.from_user.id
    add_user(executor_id, message.from_user.username, message.from_user.full_name)
    
    manager_id = 999999
    add_user(manager_id, "test_manager", "Тестовый Менеджер")
    
    task_title = "Проверить код после рефакторинга"
    task_desc = "Запустить тесты, проверить стиль, оставить комментарии. Срок – завтра до обеда."
    deadline_str = "завтра 12:00"
    deadline_ts = deadline_to_timestamp(deadline_str)
    
    card_id = await create_yougile_task(task_title, task_desc, deadline_str)
    task_uuid = str(uuid.uuid4())
    add_task(
        task_id=task_uuid,
        title=task_title,
        description=task_desc,
        responsible_telegram_id=executor_id,
        author_telegram_id=manager_id,
        deadline=deadline_str,
        deadline_timestamp=deadline_ts,
        yougile_card_id=card_id,
        chat_id=message.chat.id,
    )
    add_task_history(task_uuid, 'pending', comment='Задача от менеджера в тесте исполнителя')
    
    await message.answer(
        f"📨 **Шаг 1/3**\n\n"
        f"Менеджер назначил вам задачу:\n"
        f"📋 {task_title}\n"
        f"⏰ {deadline_str}\n\n"
        f"Нажмите «Далее», чтобы взять её в работу.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➡️ Далее", callback_data="executor_test_next_1")]
        ])
    )
    await state.set_state(ExecutorTest.step_1_created)
    await state.update_data(task_id=task_uuid, title=task_title)


@router.callback_query(ExecutorTest.step_1_created, lambda c: c.data == "executor_test_next_1")
async def executor_test_step2(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    task_id = data["task_id"]
    task_title = data["title"]
    
    task = get_task_by_id(task_id)
    if task and task.get("yougile_card_id") and YOUGILE_TOKEN and YOUGILE_DO_COLUMN_ID:
        client = YouGileClient(YOUGILE_TOKEN)
        client.move_task(task["yougile_card_id"], YOUGILE_DO_COLUMN_ID)
    add_task_history(task_id, 'in_progress', status_from='pending', comment='Взято в работу')
    
    await callback.message.edit_text(
        f"✅ **Шаг 2/3**\n\n"
        f"Задача «{task_title}» взята в работу.\n"
        f"Теперь выполните её (нажмите «Далее»).",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➡️ Далее", callback_data="executor_test_next_2")]
        ])
    )
    await state.set_state(ExecutorTest.step_2_taken)
    await callback.answer()


@router.callback_query(ExecutorTest.step_2_taken, lambda c: c.data == "executor_test_next_2")
async def executor_test_step3(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    task_id = data["task_id"]
    task_title = data["title"]
    
    task = get_task_by_id(task_id)
    if task and task.get("yougile_card_id") and YOUGILE_TOKEN and YOUGILE_DONE_COLUMN_ID:
        client = YouGileClient(YOUGILE_TOKEN)
        client.move_task(task["yougile_card_id"], YOUGILE_DONE_COLUMN_ID)
    complete_task(task_id)
    
    stats = get_user_stats(callback.from_user.id)
    xp = stats["xp"]
    level = stats["level"]
    achievements = stats.get("achievements", [])
    ach_text = "\n".join([f"🏆 {a}" for a in achievements]) if achievements else "Пока нет"
    
    await callback.message.edit_text(
        f"✅ **Шаг 3/3 – Тест исполнителя завершён!**\n\n"
        f"Выполнена задача «{task_title}».\n"
        f"✨ Ваш опыт: {xp} XP, уровень {level}\n\n"
        f"🏅 Достижения:\n{ach_text}\n\n"
        f"Теперь вы можете проверить свои задачи и ачивки.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data="user_stats")]
        ])
    )
    await state.clear()
    await callback.answer()


@router.callback_query(lambda c: c.data == "user_tasks")
async def show_tasks_callback(callback: CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    tasks = get_tasks_by_user(uid, status="pending")
    if not tasks:
        await callback.message.answer("✨ У вас нет активных задач.")
    else:
        text = "📋 Ваши задачи:\n" + "\n".join([f"- {t['title']}" for t in tasks])
        await callback.message.answer(text)


@router.callback_query(lambda c: c.data == "user_stats")
async def show_stats_callback(callback: CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    stats = get_user_stats(uid)
    await callback.message.answer(
        f"📊 Ваша статистика:\n✨ XP: {stats['xp']}\n🧙 Уровень: {stats['level']}\n🏆 Достижения: {', '.join(stats.get('achievements', [])) or 'нет'}"
    )