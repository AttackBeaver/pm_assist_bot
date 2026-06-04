import asyncio
import logging
from datetime import datetime, timezone, timedelta
from aiogram import Bot
from web.database import get_tasks_with_upcoming_deadline, get_user, get_tasks_by_user

logger = logging.getLogger(__name__)

async def reminder_worker(bot: Bot, check_interval_seconds=300, remind_hours_before=2):
    """Фоновый поток: каждые 5 минут проверяет дедлайны и отправляет напоминания."""
    while True:
        try:
            tasks = get_tasks_with_upcoming_deadline(hours_before=remind_hours_before)
            for task in tasks:
                user = get_user(task['responsible_telegram_id'])
                if not user:
                    continue
                # Личное сообщение
                try:
                    deadline_dt = datetime.fromtimestamp(task['deadline_timestamp'] / 1000)
                    await bot.send_message(
                        user['telegram_id'],
                        f"⏰ Напоминание: задача **{task['title']}** должна быть выполнена в течение {remind_hours_before} часов!\n"
                        f"Дедлайн: {deadline_dt.strftime('%d.%m.%Y %H:%M')}"
                    )
                except Exception as e:
                    logger.error(f"Ошибка отправки напоминания пользователю {user['telegram_id']}: {e}")
                # В чат, если указан
                if task.get('chat_id'):
                    try:
                        await bot.send_message(
                            task['chat_id'],
                            f"⏰ Напоминание: задача **{task['title']}** (ответственный: @{user.get('username', user['telegram_id'])}) через {remind_hours_before} часа"
                        )
                    except Exception as e:
                        logger.error(f"Ошибка отправки напоминания в чат {task['chat_id']}: {e}")
        except Exception as e:
            logger.error(f"Ошибка в планировщике напоминаний: {e}")
        await asyncio.sleep(check_interval_seconds)

async def evening_digest_worker(bot: Bot, hour=19, minute=0):
    """Ежедневный дайджест в указанное время."""
    while True:
        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())

        try:
            # Получаем всех пользователей (можно упрощённо из tasks)
            from web.database import DB_PATH
            import sqlite3
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT responsible_telegram_id FROM tasks WHERE status='pending'")
            user_ids = [row['responsible_telegram_id'] for row in cursor.fetchall()]
            conn.close()

            for uid in user_ids:
                tasks = get_tasks_by_user(uid, status='pending')
                if not tasks:
                    continue
                msg = "📋 Ваш вечерний дайджест задач:\n\n"
                for t in tasks:
                    deadline_str = ""
                    if t.get('deadline'):
                        deadline_str = f" (до {t['deadline']})"
                    msg += f"• {t['title']}{deadline_str}\n"
                try:
                    await bot.send_message(uid, msg)
                except Exception as e:
                    logger.error(f"Ошибка отправки дайджеста {uid}: {e}")
        except Exception as e:
            logger.error(f"Ошибка в вечернем дайджесте: {e}")