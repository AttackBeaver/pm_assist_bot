import logging
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder   # <-- ДОБАВИТЬ

from config import WEB_BASE_URL
from web.database import (
    add_user, set_user_away, clear_user_away,
    get_tasks_by_user, get_user_stats, get_average_completion_time
)

logger = logging.getLogger(__name__)
router = Router()


def _main_keyboard() -> ReplyKeyboardMarkup:
    """Постоянная клавиатура с основными действиями."""
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
                KeyboardButton(text="🏆 Достижения"),
                KeyboardButton(text="📊 Статистика"),
            ],
            [
                KeyboardButton(text="⏰ Ближайшие дедлайны"),
                KeyboardButton(text="🧪 Тест сценария"),
            ],
            [
                KeyboardButton(text="❓ Помощь"),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие или напишите сообщение...",
    )


def _cabinet_inline(telegram_id: int) -> Optional[InlineKeyboardMarkup]:
    url = f"{WEB_BASE_URL}/cabinet/{telegram_id}"
    if "localhost" in WEB_BASE_URL or "127.0.0.1" in WEB_BASE_URL:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🌐 Открыть личный кабинет", url=url)
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
        "• Голосовые сообщения тоже распознаю\n"
        "• Напоминаю о дедлайнах и присылаю вечерний дайджест\n\n"
        "Команды:\n"
        "/away [причина] — задачи не будут назначаться до отмены\n"
        "/back — снова доступен для задач\n"
        "/tasks — список моих задач\n"
        "/cabinet — личный кабинет\n"
        "/stats — моя статистика (XP, уровень, эффективность)\n"
        "/achievements — полученные достижения\n"
        "/deadlines — ближайшие дедлайны",
        reply_markup=_main_keyboard(),
    )


# ---------- Задачи ----------
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
    cabinet_url = f"{WEB_BASE_URL}/cabinet/{message.from_user.id}"
    inline = _cabinet_inline(message.from_user.id)
    await message.answer(
        f"🌐 Личный кабинет — управление задачами:\n{cabinet_url}",
        reply_markup=inline,
    )


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


# ---------- Статистика, достижения, дедлайны ----------
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


# ---------- Кнопка теста ----------
@router.message(F.text == "🧪 Тест сценария")
async def cmd_test_scenario(message: Message) -> None:
    uid = message.from_user.id
    cabinet_url = f"{WEB_BASE_URL}/cabinet/{uid}"
    await message.answer(
        f"🧪 **Демо-сценарий PM-Assist Bot**\n\n"
        "1. Добавьте меня в групповой чат, если ещё не сделали.\n"
        "2. Напишите в чате: `@someone подготовить отчёт до пятницы`\n"
        "   → Я автоматически создам карточку в YouGile.\n"
        "3. Нажмите «Отменить» под созданной задачей, чтобы удалить её.\n"
        "4. Отправьте голосовое: «Сделать презентацию к завтра»\n"
        f"5. Откройте веб-кабинет: {cabinet_url}\n"
        "6. Там вы увидите XP, уровень, ачивки.\n"
        "7. Выполните задачу – карточка переместится в «Готово».\n\n"
        "🎯 **Команды**: /stats, /achievements, /deadlines, /away, /back",
        parse_mode="Markdown",
        reply_markup=_main_keyboard()
    )