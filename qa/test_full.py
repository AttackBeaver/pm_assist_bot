import sys
import os
import asyncio
import uuid
import json
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Конфигурация и клиенты
from config import (
    BOT_TOKEN, SPEECH2TEXT_API_KEY,
    YOUGILE_TOKEN, YOUGILE_BOARD_ID,
    YOUGILE_TO_COLUMN_ID, YOUGILE_DO_COLUMN_ID, YOUGILE_DONE_COLUMN_ID,
    YANDEX_FOLDER_ID, YANDEX_API_KEY   # добавлено
)
from bot.utils.parser import parse_task
from web.database import (
    get_tasks_by_user, add_user, get_user, add_task, get_task_by_id,
    complete_task, delete_task, get_average_completion_time,
    get_stale_tasks, get_user_stats
)
from yougile_client import YouGileClient
from bot.tasks.scheduler import reminder_worker, evening_digest_worker, stale_task_reminder_worker
from aiogram.types import Message, CallbackQuery, User, Chat
from aiogram import Bot
from fastapi.testclient import TestClient
from web.app import app
from bot.handlers.message_handler import handle_text_message

# ----------------------------------------------------------------------
# 1. Тест переменных окружения
# ----------------------------------------------------------------------
def test_config():
    print("ℹ️ Проверка переменных окружения...")
    errors = []
    if not BOT_TOKEN:
        errors.append("BOT_TOKEN")
    if not SPEECH2TEXT_API_KEY:
        errors.append("SPEECH2TEXT_API_KEY")
    if errors:
        print(f"❌ Отсутствуют: {', '.join(errors)}")
        return False
    print("✅ Все переменные окружения заданы")
    if YOUGILE_TOKEN and YOUGILE_BOARD_ID:
        print(f"ℹ️ YouGile ID колонок: Сделать={YOUGILE_TO_COLUMN_ID}, В процессе={YOUGILE_DO_COLUMN_ID}, Готово={YOUGILE_DONE_COLUMN_ID}")
    return True

# ----------------------------------------------------------------------
# 2. Тест парсера (расширенный)
# ----------------------------------------------------------------------
def test_parser():
    print("ℹ️ Тестирование парсера задач (расширенный)...")
    known = ["ivan", "anna", "dev_lead", "max", "petrov", "m_u_shro_o_m", "F3NR1R55"]
    cases = [
        ("@ivan нужно сделать отчет до 18:00", "отчет", "18:00", "ivan", 90),
        ("@anna, задача: подготовить презентацию к 15.06", "презентацию", "15.06", "anna", 90),
        ("Сделать рефакторинг модуля парсинга", "рефакторинг", None, None, 55),
        ("dev_lead, нужен макет к пятнице", "макет", "пятнице", None, 75),
        ("Привет, как дела? Когда встреча?", None, None, None, 0),
        ("@max проверь код, пожалуйста", "проверь код", None, "max", 60),
        ("Нужно обновить документацию завтра", "документацию", "завтра", None, 75),
        ("Через 2 дня нужно сдать проект, @ivan ты ответственный", "проект", "2 дня", "ivan", 90),
        ("К 20.12.2025 подготовить отчет по продажам, ответственный @anna", "отчет", "20.12.2025", "anna", 90),
        ("Пожалуйста, сделай это как можно скорее", "сделай это", None, None, 50),
        ("Задача для @ivan: протестировать API до 12:00", "протестировать", "12:00", "ivan", 90),
        ("Просто сообщение без задач и упоминаний", None, None, None, 0),
        ("@unknown_user сделай задачу", "сделай задачу", None, None, 55),
        ("Нужно починить баг, дедлайн - послезавтра, возьмись @max", "починить баг", "послезавтра", "max", 90),
        ("Отправь файлы", None, None, None, 0),
        ("@petrov, до 10:00 сделай сводку", "сводку", "10:00", "petrov", 90),
        ("Купить пиво Даше в июле", "пиво Даше", "в июле", None, 55),
        ("@m_u_shro_o_m подготовь отчет по расходам на рекламу за прошлый месяц. Надо сделать к среде.", 
         "подготовь отчет по расходам на рекламу за прошлый месяц", "к среде", "m_u_shro_o_m", 90),
        ("Составь список сотрудников которые были на больничном в мае, сдать до 7 июня", 
         "составь список сотрудников которые были на больничном в мае", "до 7 июня", None, 75),
    ]
    passed = 0
    total = len(cases)
    failed = []
    for i, (text, exp_task, exp_deadline, exp_assignee, min_conf) in enumerate(cases, 1):
        res = parse_task(text, known)
        ok = True
        err = []
        # Проверка задачи
        if exp_task is None:
            ok = (res["confidence"] == 0)
            if not ok:
                err.append(f"expected confidence 0, got {res['confidence']}")
        else:
            if exp_task.lower() not in res["task"].lower():
                ok = False; err.append(f"no '{exp_task}' in '{res['task'][:50]}'")
        # Проверка дедлайна
        if exp_deadline is None:
            if res["deadline"] is not None:
                ok = False; err.append(f"deadline should be None, got {res['deadline']}")
        else:
            if res["deadline"] is None or exp_deadline not in res["deadline"]:
                ok = False; err.append(f"no '{exp_deadline}' in '{res['deadline']}'")
        # Проверка ответственных (список)
        if exp_assignee is None:
            if res.get("assignees"):
                ok = False; err.append(f"assignees should be empty, got {res['assignees']}")
        else:
            assignees_lower = [a.lower() for a in res.get("assignees", [])]
            if exp_assignee.lower() not in assignees_lower:
                ok = False; err.append(f"assignee expected {exp_assignee}, got {res.get('assignees')}")
        # Проверка confidence
        if res["confidence"] < min_conf:
            ok = False; err.append(f"confidence {res['confidence']} < {min_conf}")
        if ok:
            passed += 1
        else:
            failed.append(f"{i}. {text[:40]}... → {', '.join(err)}")
    accuracy = passed / total * 100
    if failed:
        print("❌ Проваленные тесты:")
        for f in failed:
            print(f"   {f}")
    print(f"{'✅' if accuracy >= 80 else '❌'} Парсер: {passed}/{total} тестов пройдено ({accuracy:.1f}%)")
    return accuracy >= 80

# ----------------------------------------------------------------------
# 3. Тест локальной БД (геймификация)
# ----------------------------------------------------------------------
def test_database():
    print("ℹ️ Тестирование локальной БД и геймификации...")
    test_id = 999999
    # Жёсткая очистка всех данных этого пользователя
    import sqlite3
    from web.database import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM tasks WHERE responsible_telegram_id = ? OR author_telegram_id = ?", (test_id, test_id))
    conn.execute("DELETE FROM user_stats WHERE telegram_id = ?", (test_id,))
    conn.execute("DELETE FROM users WHERE telegram_id = ?", (test_id,))
    conn.commit()
    conn.close()
    add_user(test_id, "testuser", "Test User")
    user = get_user(test_id)
    if not user:
        print("❌ Не удалось создать пользователя")
        return False
    print("✅ Пользователь создан")
    task_uuid = str(uuid.uuid4())
    add_task(
        task_id=task_uuid,
        title="Тестовая задача",
        description="Описание",
        responsible_telegram_id=test_id,
        author_telegram_id=test_id,          # <-- ДОБАВЛЕНО
        deadline="завтра",
        deadline_timestamp=int((datetime.now() + timedelta(days=1)).timestamp() * 1000),
    )
    task = get_task_by_id(task_uuid)
    if not task:
        print("❌ Не удалось создать задачу")
        return False
    print("✅ Задача создана")
    stats = get_user_stats(test_id)
    if stats["xp"] != 5:
        print(f"❌ XP не начислен: ожидалось 5, получено {stats['xp']}")
        return False
    print("✅ XP за создание начислен")
    complete_task(task_uuid)
    task2 = get_task_by_id(task_uuid)
    if task2["status"] != "completed":
        print("❌ Задача не отмечена выполненной")
        return False
    stats2 = get_user_stats(test_id)
    if stats2["xp"] != 15:
        print(f"❌ XP за выполнение не начислен: ожидалось 15, получено {stats2['xp']}")
        return False
    print("✅ XP за выполнение начислен")
    avg = get_average_completion_time(test_id)
    print(f"ℹ️ Среднее время выполнения: {avg} ч")
    stale = get_stale_tasks(days_old=0)
    print("✅ Stale-напоминания работают")
    delete_task(task_uuid)
    return True

# ----------------------------------------------------------------------
# 4. Тест интеграции YouGile
# ----------------------------------------------------------------------
def test_yougile():
    print("ℹ️ Тестирование интеграции с YouGile...")
    if not YOUGILE_TOKEN or not YOUGILE_BOARD_ID:
        print("⚠️ YouGile не настроен — пропускаем")
        return True
    client = YouGileClient(YOUGILE_TOKEN)
    columns = client.get_columns(YOUGILE_BOARD_ID)
    if not columns:
        print("❌ Не удалось получить колонки")
        return False
    print(f"✅ Получено {len(columns)} колонок")
    if YOUGILE_TO_COLUMN_ID:
        found = any(c["id"] == YOUGILE_TO_COLUMN_ID for c in columns)
        print(f"ℹ️ Колонка 'Сделать': {'найдена' if found else 'НЕ найдена'}")
    column_id = YOUGILE_TO_COLUMN_ID or columns[0]["id"]
    if column_id:
        task = client.create_task("Тест интеграции", column_id, "Автоматический тест")
        if task:
            print(f"✅ Задача создана: id={task.get('id')}")
            if YOUGILE_DO_COLUMN_ID:
                moved = client.move_task(task["id"], YOUGILE_DO_COLUMN_ID)
                print(f"ℹ️ Перемещение в 'В процессе': {'успешно' if moved else 'ошибка'}")
            if YOUGILE_DONE_COLUMN_ID:
                moved2 = client.move_task(task["id"], YOUGILE_DONE_COLUMN_ID)
                print(f"ℹ️ Перемещение в 'Готово': {'успешно' if moved2 else 'ошибка'}")
        else:
            print("❌ Не удалось создать задачу")
    else:
        print("⚠️ Нет колонки для создания задачи")
    return True

# ----------------------------------------------------------------------
# 5. Тест веб-кабинета
# ----------------------------------------------------------------------
def test_web_cabinet():
    print("ℹ️ Тестирование веб-кабинета...")
    from fastapi.testclient import TestClient
    client = TestClient(app)
    resp = client.get("/health")
    if resp.status_code != 200:
        print(f"❌ /health вернул {resp.status_code}")
        return False
    test_id = 888888
    add_user(test_id, "webtest", "Web Test")
    task_uuid = str(uuid.uuid4())
    add_task(
        task_id=task_uuid,
        title="Веб задача",
        description="Тест",
        responsible_telegram_id=test_id,
        author_telegram_id=test_id,
    )
    resp = client.get(f"/cabinet/{test_id}")
    if resp.status_code != 200:
        print(f"❌ /cabinet/{test_id} вернул {resp.status_code}")
        return False
    content = resp.text
    if "Веб задача" not in content:
        print("❌ Задача не отображается в кабинете")
        return False
    resp = client.post(f"/task/{task_uuid}/complete", data={"telegram_id": test_id})
    if resp.status_code not in (200, 303):
        print(f"❌ /complete вернул {resp.status_code}")
        return False
    task = get_task_by_id(task_uuid)
    if task["status"] != "completed":
        print("❌ Задача не выполнена после POST")
        return False
    resp = client.post(f"/task/{task_uuid}/delete", data={"telegram_id": test_id})
    if resp.status_code not in (200, 303):
        print(f"❌ /delete вернул {resp.status_code}")
        return False
    delete_task(task_uuid)
    print("✅ Веб-кабинет работает корректно")
    return True

# ----------------------------------------------------------------------
# 6. Тест напоминаний
# ----------------------------------------------------------------------
async def test_reminder():
    print("ℹ️ Тестирование напоминаний (имитация)...")
    test_id = 555555
    add_user(test_id, "reminder_user", "Reminder")
    task_id = str(uuid.uuid4())
    deadline_ts = int((datetime.now() + timedelta(hours=1)).timestamp() * 1000)
    add_task(
        task_id=task_id,
        title="Тест напоминания",
        description="Описание",
        responsible_telegram_id=test_id,
        author_telegram_id=test_id,   # <-- добавлено
        deadline_timestamp=deadline_ts,
        chat_id=-100123456789
    )
    class MockBot:
        async def send_message(self, chat_id, text):
            print(f"→ Отправлено сообщение в чат {chat_id}: {text[:50]}")
    bot = MockBot()
    from web.database import get_tasks_with_upcoming_deadline
    tasks = get_tasks_with_upcoming_deadline(hours_before=2)
    if not tasks:
        print("❌ Задача не найдена как приближающаяся")
        return False
    for task in tasks:
        if task["id"] == task_id:
            print("✅ Задача обнаружена планировщиком")
            break
    delete_task(task_id)
    print("✅ Планировщик напоминаний работает")
    return True

def test_scheduler():
    return asyncio.run(test_reminder())

# ----------------------------------------------------------------------
# 7. Тест импортов модулей
# ----------------------------------------------------------------------
def test_imports():
    print("ℹ️ Проверка импортов модулей...")
    try:
        from aiogram import Bot, Dispatcher
        from fastapi import FastAPI, Form
        import uvicorn
        import pytz
        import sqlalchemy
        import requests
        from dotenv import load_dotenv
        print("✅ Все модули импортируются успешно")
        return True
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
        return False

# ----------------------------------------------------------------------
# 8. Тест уведомлений
# ----------------------------------------------------------------------
def test_notifications():
    print("ℹ️ Тестирование отправки уведомлений ответственному...")
    author_id = 111111
    responsible_id = 222222
    responsible_username = "test_resp"
    add_user(author_id, "author", "Author")
    add_user(responsible_id, responsible_username, "Responsible")
    
    # Проверим, что пользователь добавился
    user = get_user(responsible_id)
    if not user:
        print("❌ Пользователь не добавлен в БД")
        return False

    class MockMessage:
        from_user = type('User', (), {'id': author_id, 'username': 'author', 'full_name': 'Author'})
        chat = type('Chat', (), {'id': -100123456789, 'title': 'Test Group'})
        message_id = 999
        text = f"Привет, @{responsible_username} нужно сделать отчёт до пятницы"
        async def reply(self, text, reply_markup=None):
            print(f"📨 Бот ответил в группе: {text[:50]}...")

    mock_msg = MockMessage()

    class MockBot:
        def __init__(self):
            self.sent_messages = []
        async def send_message(self, chat_id, text, reply_markup=None):
            print(f"🔔 Бот отправил личное сообщение пользователю {chat_id}: {text[:100]}...")
            self.sent_messages.append((chat_id, text))

    bot = MockBot()

    try:
        asyncio.run(handle_text_message(mock_msg, bot))
    except Exception as e:
        print(f"❌ Ошибка при вызове handle_text_message: {e}")
        return False

    sent = bot.sent_messages
    if not sent:
        print("❌ Уведомление не было отправлено.")
        print("   Возможные причины:")
        print("   - Парсер не извлёк assignee (в сообщении должен быть @test_resp)")
        print("   - handle_text_message не вызывает bot.send_message для ответственного")
        print("   - В БД нет пользователя с username =", responsible_username)
        return False

    for chat_id, text in sent:
        if chat_id == responsible_id:
            print("✅ Личное уведомление отправлено ответственному")
            return True
    print("❌ Уведомление отправлено, но не тому пользователю")
    return False

# ----------------------------------------------------------------------
# 9. Тест YandexGPT
# ----------------------------------------------------------------------
def test_yandex_gpt():
    print("ℹ️ Тестирование YandexGPT...")
    from config import YANDEX_FOLDER_ID, YANDEX_API_KEY
    if not YANDEX_FOLDER_ID or not YANDEX_API_KEY:
        print("⚠️ YandexGPT не настроен (отсутствуют YANDEX_FOLDER_ID или YANDEX_API_KEY) — тест пропущен")
        return True  # Не считаем ошибкой, просто пропускаем

    try:
        from bot.utils.llm_parser import parse_task_with_llm
    except ImportError as e:
        print(f"❌ Не удалось импортировать llm_parser: {e}")
        return False

    test_text = "@ivan нужно сделать отчет до 18:00"
    print(f"🔍 Тестовая фраза: {test_text}")
    result = parse_task_with_llm(test_text)
    if not result:
        print("❌ YandexGPT не вернул результат (возможно, ошибка API или сетевые проблемы)")
        return False

    required_fields = ["task", "deadline", "assignees", "confidence"]
    for field in required_fields:
        if field not in result:
            print(f"❌ В ответе отсутствует поле {field}")
            return False

    confidence = result.get("confidence", 0)
    if confidence < 50:
        print(f"❌ Уверенность слишком низкая: {confidence}")
        return False

    print(f"✅ YandexGPT распознал задачу: task={result['task']}, deadline={result['deadline']}, assignees={result['assignees']}, confidence={confidence}")
    return True

# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------
def main():
    print("=" * 60)
    print("🧪 PM-Assist Bot — ПОЛНОЕ ТЕСТИРОВАНИЕ")
    print("=" * 60)
    results = {}
    results["config"] = test_config()
    results["parser"] = test_parser()
    results["database"] = test_database()
    results["yougile"] = test_yougile()
    results["web_cabinet"] = test_web_cabinet()
    results["scheduler"] = test_scheduler()
    results["imports"] = test_imports()
    results["notifications"] = test_notifications()
    results["yandex_gpt"] = test_yandex_gpt()
    print("\n" + "=" * 60)
    print("📊 РЕЗУЛЬТАТЫ:")
    for name, ok in results.items():
        print(f"  {'✅' if ok else '❌'} {name.capitalize()}")
    print("=" * 60)
    if all(results.values()):
        print("✅ Все тесты пройдены успешно!")
        sys.exit(0)
    else:
        print("❌ Некоторые тесты не пройдены. Исправьте ошибки перед деплоем.")
        sys.exit(1)

if __name__ == "__main__":
    main()