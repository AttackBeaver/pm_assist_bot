import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot

from web.database import (
    get_tasks_with_upcoming_deadline,
    get_pending_user_ids,
    get_user,
    get_tasks_by_user,
    get_stale_tasks,
    mark_task_reminded,
    get_due_meeting_reminders,
    mark_meeting_reminder_notified,
    get_active_report_session,
    close_report_session,
    get_users_without_report,
    create_report_session,
    get_all_chat_ids,
)
from web.database import get_user as get_user_db

logger = logging.getLogger(__name__)

_STALE_REMINDER_INTERVAL = 21600
_STALE_TASK_DAYS = 3
_REMINDER_INTERVAL = 300   # 5 минут
_REMIND_HOURS_BEFORE = 2
_DIGEST_HOUR = 19
_DIGEST_MINUTE = 0

_REPORT_HOUR = 19
_REPORT_DURATION_HOURS = 1

async def stale_task_reminder_worker(bot: Bot) -> None:
    while True:
        try:
            stale_tasks = get_stale_tasks(days_old=_STALE_TASK_DAYS)
            for task in stale_tasks:
                user = get_user(task["responsible_telegram_id"])
                if not user:
                    continue
                try:
                    await bot.send_message(
                        user["telegram_id"],
                        f"⚠️ Вы не обновили статус задачи «{task['title']}».\nОна всё ещё в работе?",
                    )
                    logger.info(f"Отправлено stale-напоминание пользователю {user['telegram_id']} по задаче {task['id']}")
                except Exception as e:
                    logger.error(f"Ошибка отправки напоминания пользователю {user['telegram_id']}: {e}")
        except Exception as e:
            logger.error(f"Ошибка в планировщике напоминаний о старых задачах: {e}")
        await asyncio.sleep(_STALE_REMINDER_INTERVAL)

def _hours_label(hours: int) -> str:
    if hours == 1:
        return "1 час"
    if 2 <= hours <= 4:
        return f"{hours} часа"
    return f"{hours} часов"

async def reminder_worker(bot: Bot) -> None:
    while True:
        try:
            tasks = get_tasks_with_upcoming_deadline(hours_before=_REMIND_HOURS_BEFORE)
            if not tasks:
                await asyncio.sleep(_REMINDER_INTERVAL)
                continue

            user_tasks = {}
            for task in tasks:
                user = get_user(task["responsible_telegram_id"])
                if not user:
                    continue
                uid = user["telegram_id"]
                if uid not in user_tasks:
                    user_tasks[uid] = {"user": user, "tasks": []}
                user_tasks[uid]["tasks"].append(task)

            for uid, data in user_tasks.items():
                user = data["user"]
                tasks_for_user = data["tasks"]
                if not tasks_for_user:
                    continue

                lines = ["⏰ **Напоминание о дедлайнах:**\n"]
                for task in tasks_for_user:
                    deadline_dt = datetime.fromtimestamp(task["deadline_timestamp"] / 1000)
                    deadline_fmt = deadline_dt.strftime("%d.%m.%Y %H:%M")
                    lines.append(f"• {task['title']} — до {deadline_fmt}")
                text = "\n".join(lines)

                try:
                    await bot.send_message(uid, text, parse_mode="Markdown")
                    logger.info(f"Отправлено групповое напоминание пользователю {uid} по {len(tasks_for_user)} задачам")
                except Exception as e:
                    logger.error(f"Ошибка отправки группового напоминания пользователю {uid}: {e}")
                    continue

                for task in tasks_for_user:
                    mark_task_reminded(task["id"])

                chat_tasks = {}
                for task in tasks_for_user:
                    if task.get("chat_id"):
                        cid = task["chat_id"]
                        chat_tasks.setdefault(cid, []).append(task)

                for cid, chat_task_list in chat_tasks.items():
                    mention = f"@{user['username']}" if user.get("username") else str(uid)
                    for task in chat_task_list:
                        try:
                            await bot.send_message(
                                cid,
                                f"⏰ Напоминание: задача «{task['title']}» (ответственный: {mention}) — через {_hours_label(_REMIND_HOURS_BEFORE)}",
                            )
                            logger.info(f"Отправлено напоминание в чат {cid} по задаче {task['id']}")
                        except Exception as e:
                            logger.error(f"Ошибка отправки напоминания в чат {cid}: {e}")

        except Exception as e:
            logger.error(f"Ошибка в планировщике напоминаний: {e}")

        await asyncio.sleep(_REMINDER_INTERVAL)

async def evening_digest_worker(bot: Bot) -> None:
    while True:
        now = datetime.now()
        target = now.replace(hour=_DIGEST_HOUR, minute=_DIGEST_MINUTE, second=0, microsecond=0)
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
                    deadline_part = f" (до {t['deadline']})" if t.get("deadline") else ""
                    lines.append(f"• {t['title']}{deadline_part}")
                try:
                    await bot.send_message(uid, "\n".join(lines))
                    logger.info(f"Отправлен вечерний дайджест пользователю {uid} ({len(tasks)} задач)")
                except Exception as e:
                    logger.error(f"Ошибка отправки дайджеста пользователю {uid}: {e}")
        except Exception as e:
            logger.error(f"Ошибка в вечернем дайджесте: {e}")

# ========== НОВЫЙ ВОРКЕР: напоминания о встречах ==========
async def meeting_reminder_worker(bot: Bot) -> None:
    while True:
        try:
            reminders = get_due_meeting_reminders()
            for rem in reminders:
                try:
                    await bot.send_message(
                        rem["chat_id"],
                        f"🔔 Напоминание: через 10 минут начнётся встреча по ссылке: {rem['meet_url']}\n"
                        f"Я автоматически подключусь к ней, чтобы записать аудио."
                    )
                    mark_meeting_reminder_notified(rem["id"])
                    logger.info(f"Отправлено напоминание о встрече в чат {rem['chat_id']}")
                except Exception as e:
                    logger.error(f"Ошибка отправки напоминания о встрече: {e}")
        except Exception as e:
            logger.error(f"Ошибка в meeting_reminder_worker: {e}")
        await asyncio.sleep(60)

# ========== НОВЫЙ ВОРКЕР: вечерняя синхронизация (отчёты) ==========
async def evening_report_worker(bot: Bot) -> None:
    """В 19:00 создаёт сессию отчётов для всех чатов, через 1 час закрывает и тегает отсутствующих."""
    while True:
        now = datetime.now()
        target = now.replace(hour=_REPORT_HOUR, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())

        date_str = now.strftime("%Y-%m-%d")
        chat_ids = get_all_chat_ids()
        sessions = []
        for chat_id in chat_ids:
            session_id = create_report_session(chat_id, date_str)
            sessions.append((chat_id, session_id))
            try:
                await bot.send_message(
                    chat_id,
                    "⏰ **Вечерняя синхронизация!**\n"
                    "Напишите, что вы сделали сегодня. Можно просто перечислить выполненные задачи.\n"
                    "Если вы сегодня не работали (отпуск, больничный) – просто напишите «отдых».\n\n"
                    "У вас есть 1 час на отчёт."
                )
            except Exception as e:
                logger.error(f"Не удалось отправить запрос отчёта в чат {chat_id}: {e}")

        # Ждём 1 час
        await asyncio.sleep(_REPORT_DURATION_HOURS * 3600)

        for chat_id, session_id in sessions:
            # Получаем всех участников чата, у которых есть активные задачи
            from web.database import get_all_active_tasks
            active_tasks = get_all_active_tasks()
            members_with_tasks = set()
            for task in active_tasks:
                if task.get("chat_id") == chat_id and task.get("responsible_telegram_id"):
                    members_with_tasks.add(task["responsible_telegram_id"])

            # Исключаем тех, кто в away
            final_members = []
            for uid in members_with_tasks:
                user = get_user_db(uid)
                if user and user.get("is_away"):
                    continue
                final_members.append(uid)

            # Кто не отчитался
            missing = get_users_without_report(session_id, final_members)

            for uid in missing:
                user = get_user_db(uid)
                mention = f"@{user['username']}" if user and user.get("username") else str(uid)
                try:
                    await bot.send_message(
                        chat_id,
                        f"⏰ {mention}, вы не прислали отчёт за сегодня.\n"
                        f"Пожалуйста, напишите, что было сделано, или используйте /away, если вы недоступны."
                    )
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления об отсутствии отчёта: {e}")

            close_report_session(session_id)
            logger.info(f"Сессия отчётов {session_id} для чата {chat_id} закрыта")