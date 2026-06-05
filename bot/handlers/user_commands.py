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

from config import WEB_BASE_URL
from web.database import add_user, set_user_away, clear_user_away, get_tasks_by_user
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
                KeyboardButton(text="❓ Помощь"),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие или напишите сообщение...",
    )


def _cabinet_inline(telegram_id: int) -> Optional[InlineKeyboardMarkup]:
    """Inline-кнопка перехода в личный кабинет.
    Возвращает None если URL локальный (Telegram не принимает localhost в кнопках)."""
    url = f"{WEB_BASE_URL}/cabinet/{telegram_id}"
    if "localhost" in WEB_BASE_URL or "127.0.0.1" in WEB_BASE_URL:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🌐 Открыть личный кабинет", url=url)
    ]])

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
        "• Если нахожу — предлагаю создать карточку в YouGile\n"
        "• Голосовые сообщения тоже распознаю\n"
        "• Напоминаю о дедлайнах и присылаю вечерний дайджест\n\n"
        "Команды:\n"
        "/away [причина] — задачи не будут назначаться до отмены\n"
        "/back — снова доступен для задач\n"
        "/tasks — список моих задач\n"
        "/cabinet — личный кабинет",
        reply_markup=_main_keyboard(),
    )

def _cabinet_url_text(telegram_id: int) -> str:
    """Возвращает строку с URL кабинета для вставки в текст сообщения."""
    return f"{WEB_BASE_URL}/cabinet/{telegram_id}"


@router.message(Command("tasks"))
@router.message(F.text == "📋 Мои задачи")
async def cmd_tasks(message: Message) -> None:
    tasks = get_tasks_by_user(message.from_user.id, status="pending")
    cabinet_url = _cabinet_url_text(message.from_user.id)
    inline = _cabinet_inline(message.from_user.id)

    if not tasks:
        await message.answer(
            f"✨ У вас нет активных задач.\n\n"
            f"🌐 Кабинет: {cabinet_url}",
            reply_markup=inline,
        )
        return

    lines = ["📋 Ваши активные задачи:\n"]
    for i, t in enumerate(tasks, 1):
        deadline_part = f" (до {t['deadline']})" if t.get("deadline") else ""
        lines.append(f"{i}. {t['title']}{deadline_part}")
    lines.append(f"\n🌐 Кабинет: {cabinet_url}")
    await message.answer(
        "\n".join(lines),
        reply_markup=inline,
    )


@router.message(Command("cabinet"))
@router.message(F.text == "🌐 Личный кабинет")
async def cmd_cabinet(message: Message) -> None:
    cabinet_url = _cabinet_url_text(message.from_user.id)
    inline = _cabinet_inline(message.from_user.id)
    await message.answer(
        f"🌐 Личный кабинет — управление задачами:\n{cabinet_url}",
        reply_markup=inline,
    )
@router.message(Command("away"))
@router.message(F.text == "🚫 Недоступен")
async def cmd_away(message: Message) -> None:
    # Для кнопки причина не указывается; для команды — берём аргумент
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