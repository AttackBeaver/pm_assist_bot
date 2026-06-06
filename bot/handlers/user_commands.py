import logging
from datetime import datetime, timedelta
import re
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
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import WEB_BASE_URL, YOUGILE_DO_COLUMN_ID, YOUGILE_DONE_COLUMN_ID, YOUGILE_TOKEN
from web.database import (
    add_user, complete_task, set_user_away, clear_user_away,
    get_tasks_by_user, get_user_stats, get_average_completion_time
)
from yougile_client import YouGileClient

logger = logging.getLogger(__name__)
router = Router()


def _main_keyboard() -> ReplyKeyboardMarkup:
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
                KeyboardButton(text="📚 Рекомендации"),
            ],
            [
                KeyboardButton(text="⏰ Ближайшие дедлайны"),
                KeyboardButton(text="🧪 Тест сценария"),
                KeyboardButton(text="📞 Встреча"),
            ],
            [
                KeyboardButton(text="❓ Помощь"),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие или напишите сообщение...",
    )


def _cabinet_url_text(telegram_id: int) -> str:
    return f"{WEB_BASE_URL}?id={telegram_id}"


def _cabinet_inline(telegram_id: int) -> Optional[InlineKeyboardMarkup]:
    url = f"{WEB_BASE_URL}?id={telegram_id}"
    if "localhost" in WEB_BASE_URL or "127.0.0.1" in WEB_BASE_URL:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🌐 Открыть личный кабинет", url=url)
    ]])


# ---------- Обработчик встречи ----------
@router.message(Command("meet"))
@router.message(F.text == "📞 Встреча")
async def cmd_meet(message: Message) -> None:
    await message.answer(
        "📢 **Расшифровка встречи**\n\n"
        "Вы можете отправить мне:\n"
        "• Голосовое сообщение\n"
        "• Аудиофайл (MP3, OGG, WAV)\n"
        "• Видеофайл (WEBM, MP4, AVI, MOV)\n"
        "• **Публичную ссылку на Яндекс.Диск** с записью встречи\n\n"
        "Я распознаю речь, выделю задачи, дедлайны и ответственных, и создам карточки в YouGile.\n\n"
        "⚠️ **Важно:** Telegram не позволяет обрабатывать файлы >20 МБ. Для больших файлов используйте ссылку на Яндекс.Диск.",
        parse_mode="Markdown",
        reply_markup=_main_keyboard()
    )

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
        "📋 Управление задачами:\n"
        "/tasks — список ваших активных задач с номерами\n"
        "/move <номер> <колонка> — переместить задачу (колонки: `В процессе`, `Готово`)\n"
        "/complete <номер> — быстро завершить задачу и переместить в «Готово»\n"
        "/cabinet — открыть личный кабинет в браузере\n\n"
        "📊 Статистика и мотивация:\n"
        "/stats — ваша статистика (XP, уровень, выполненные задачи)\n"
        "/achievements — полученные достижения\n"
        "/deadlines — ближайшие дедлайны\n"
        "/recommendations — персональные рекомендации по курсам\n\n"
        "🛠 Настройки:\n"
        "/away [причина] — временно отключить назначение задач\n"
        "/back — снова доступен для задач\n"
        "/meet — инструкция по загрузке записи встречи\n",
        parse_mode="Markdown",
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
    cabinet_url = _cabinet_url_text(message.from_user.id)
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


@router.message(F.text == "🧪 Тест сценария")
async def cmd_test_scenario(message: Message) -> None:
    uid = message.from_user.id
    cabinet_url = _cabinet_url_text(uid)
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
                complete_task(task["id"])
                await message.answer(f"✅ Задача «{task['title']}» завершена и перемещена в «Готово».")
            else:
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
            complete_task(task["id"])
            await message.answer(f"✅ Задача «{task['title']}» завершена и перемещена в «Готово».")
        else:
            await message.answer("❌ Не удалось завершить задачу.")
    except ValueError:
        await message.answer("❌ Неверный формат номера. Пример: `/complete 2`")
    except Exception as e:
        logger.error(f"Ошибка в /complete: {e}")
        await message.answer("⚠️ Произошла ошибка при завершении задачи.")