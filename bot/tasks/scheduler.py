import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot

from web.database import (
    get_tasks_with_upcoming_deadline,
    get_pending_user_ids,
    get_user,
    get_tasks_by_user,
)

logger = logging.getLogger(__name__)

_STALE_REMINDER_INTERVAL = 21600  # 6 часов в секундах
_STALE_TASK_DAYS = 3  # сколько дней задача считается "зависшей"
_REMINDER_INTERVAL = 300   # секунд между проверками дедлайнов
_REMIND_HOURS_BEFORE = 2   # за сколько часов до дедлайна напоминать
_DIGEST_HOUR = 19          # час отправки вечернего дайджеста
_DIGEST_MINUTE = 0


async def stale_task_reminder_worker(bot: Bot) -> None:
    """Раз в 6 часов проверяет старые задачи и напоминает о них."""
    while True:
        try:
            from web.database import get_stale_tasks
            stale_tasks = get_stale_tasks(days_old=_STALE_TASK_DAYS)

            for task in stale_tasks:
                user = get_user(task["responsible_telegram_id"])
                if not user:
                    continue

                try:
                    await bot.send_message(
                        user["telegram_id"],
                        f"⚠️ Вы не обновили статус задачи «{task['title']}».\n"
                        f"Она всё ещё в работе?",
                    )
                except Exception as e:
                    logger.error(
                        f"Ошибка отправки напоминания пользователю {user['telegram_id']}: {e}"
                    )
        except Exception as e:
            logger.error(
                f"Ошибка в планировщике напоминаний о старых задачах: {e}")

        await asyncio.sleep(_STALE_REMINDER_INTERVAL)


def _hours_label(hours: int) -> str:
    """Возвращает корректную форму слова 'час' для числа hours."""
    if hours == 1:
        return "1 час"
    if 2 <= hours <= 4:
        return f"{hours} часа"
    return f"{hours} часов"


async def reminder_worker(bot: Bot) -> None:
    """Каждые 5 минут проверяет дедлайны и отправляет напоминания ответственным."""
    while True:
        try:
            tasks = get_tasks_with_upcoming_deadline(
                hours_before=_REMIND_HOURS_BEFORE)
            for task in tasks:
                user = get_user(task["responsible_telegram_id"])
                if not user:
                    continue

                deadline_dt = datetime.fromtimestamp(
                    task["deadline_timestamp"] / 1000)
                deadline_fmt = deadline_dt.strftime("%d.%m.%Y %H:%M")
                label = _hours_label(_REMIND_HOURS_BEFORE)

                # Личное сообщение ответственному
                try:
                    await bot.send_message(
                        user["telegram_id"],
                        f"⏰ Напоминание: задача «{task['title']}» "
                        f"должна быть выполнена через {label}!\n"
                        f"Дедлайн: {deadline_fmt}",
                    )
                except Exception as e:
                    logger.error(
                        f"Ошибка отправки напоминания пользователю {user['telegram_id']}: {e}"
                    )

                # Сообщение в групповой чат, если указан
                if task.get("chat_id"):
                    mention = f"@{user['username']}" if user.get(
                        "username") else str(user["telegram_id"])
                    try:
                        await bot.send_message(
                            task["chat_id"],
                            f"⏰ Напоминание: задача «{task['title']}» "
                            f"(ответственный: {mention}) — через {label}",
                        )
                    except Exception as e:
                        logger.error(
                            f"Ошибка отправки напоминания в чат {task['chat_id']}: {e}"
                        )
        except Exception as e:
            logger.error(f"Ошибка в планировщике напоминаний: {e}")

        await asyncio.sleep(_REMINDER_INTERVAL)


async def evening_digest_worker(bot: Bot) -> None:
    """Ежедневно в _DIGEST_HOUR:_DIGEST_MINUTE отправляет дайджест задач каждому пользователю."""
    while True:
        now = datetime.now()
        target = now.replace(
            hour=_DIGEST_HOUR, minute=_DIGEST_MINUTE, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())

        try:
            user_ids = get_pending_user_ids()
            for uid in user_ids:
                tasks = get_tasks_by_user(uid, status="pending")
                if not tasks:
                    continue

                lines = ["📋 Ваш вечерний дайджест задач:\n"]
                for t in tasks:
                    deadline_part = f" (до {t['deadline']})" if t.get(
                        "deadline") else ""
                    lines.append(f"• {t['title']}{deadline_part}")
                try:
                    await bot.send_message(uid, "\n".join(lines))
                except Exception as e:
                    logger.error(
                        f"Ошибка отправки дайджеста пользователю {uid}: {e}")
        except Exception as e:
            logger.error(f"Ошибка в вечернем дайджесте: {e}")
