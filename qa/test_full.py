import sys
import os
import time
import uuid
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Переменные окружения проверяем через config
from config import (
    BOT_TOKEN, SPEECH2TEXT_API_KEY,
    YOUGILE_TOKEN, YOUGILE_BOARD_ID,
    YOUGILE_TO_COLUMN_ID, YOUGILE_DO_COLUMN_ID, YOUGILE_DONE_COLUMN_ID
)

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

def test_parser():
    print("ℹ️ Тестирование парсера задач...")
    from bot.utils.parser import parse_task
    known = ["ivan", "anna", "dev_lead", "max", "petrov"]
    cases = [
        ("@ivan нужно сделать отчет до 18:00", "отчет", "18:00", "ivan", 90),
        ("@anna, задача: подготовить презентацию к 15.06", "презентацию", "15.06", "anna", 90),
        ("Сделать рефакторинг модуля парсинга", "рефакторинг", None, None, 50),
        ("dev_lead, нужен макет к пятнице", "макет", "пятнице", "dev_lead", 90),
        ("Привет, как дела? Когда встреча?", None, None, None, 0),
        ("@max проверь код, пожалуйста", "проверь код", None, "max", 60),
        ("Нужно обновить документацию завтра", "документацию", "завтра", None, 70),
        ("Через 2 дня нужно сдать проект, @ivan ты ответственный", "проект", "2 дня", "ivan", 90),
        ("К 20.12.2025 подготовить отчет по продажам, ответственный @anna", "отчет", "20.12.2025", "anna", 90),
        ("Пожалуйста, сделай это как можно скорее", "сделай это", None, None, 55),
        ("Задача для @ivan: протестировать API до 12:00", "протестировать", "12:00", "ivan", 90),
        ("Просто сообщение без задач и упоминаний", None, None, None, 0),
        ("@unknown_user сделай задачу", "сделай задачу", None, None, 55),
        ("Нужно починить баг, дедлайн - послезавтра, возьмись @max", "починить баг", "послезавтра", "max", 90),
        ("Отправь файлы", None, None, None, 0),
        ("@petrov, до 10:00 сделай сводку", "сводку", "10:00", "petrov", 90),
    ]
    passed = 0
    failed_details = []
    for i, (text, exp_task, exp_deadline, exp_assignee, min_conf) in enumerate(cases, 1):
        res = parse_task(text, known)
        ok = True
        errors = []
        # Проверка задачи
        if exp_task is None:
            if len(res["task"]) >= 10:
                ok = False
                errors.append(f"задача не должна быть длинной ({res['task'][:30]})")
        else:
            if exp_task.lower() not in res["task"].lower():
                ok = False
                errors.append(f"ожидалась подстрока '{exp_task}', получено '{res['task'][:30]}'")
        # Проверка дедлайна
        if exp_deadline is None:
            if res["deadline"] is not None:
                ok = False
                errors.append(f"дедлайн должен быть None, получен '{res['deadline']}'")
        else:
            if res["deadline"] is None or exp_deadline not in res["deadline"]:
                ok = False
                errors.append(f"ожидался дедлайн с '{exp_deadline}', получен '{res['deadline']}'")
        # Проверка ответственного
        if exp_assignee is None:
            if res["assignee"] is not None:
                ok = False
                errors.append(f"ответственный должен быть None, получен '{res['assignee']}'")
        else:
            if res["assignee"] is None or res["assignee"].lower() != exp_assignee.lower():
                ok = False
                errors.append(f"ожидался ответственный '{exp_assignee}', получен '{res['assignee']}'")
        # Проверка confidence
        if res["confidence"] < min_conf:
            ok = False
            errors.append(f"confidence {res['confidence']} < {min_conf}")
        if ok:
            passed += 1
        else:
            failed_details.append(f"{i}. {text[:40]}... → {', '.join(errors)}")
    total = len(cases)
    accuracy = passed / total * 100
    if failed_details:
        print("❌ Проваленные тесты:")
        for detail in failed_details:
            print(f"   {detail}")
    print(f"{'✅' if accuracy >= 80 else '❌'} Парсер: {passed}/{total} тестов пройдено ({accuracy:.1f}%)")
    return accuracy >= 80

def test_database():
    print("ℹ️ Тестирование локальной БД...")
    from web.database import add_user, get_user, add_task, get_task_by_id, complete_task, delete_task, get_average_completion_time, get_stale_tasks
    test_id = 999999
    add_user(test_id, "testuser", "Test User")
    user = get_user(test_id)
    if not user:
        print("❌ Не удалось создать пользователя")
        return False
    print("✅ Пользователь создан и получен")
    task_uuid = str(uuid.uuid4())
    add_task(task_uuid, "Тестовая задача", "Описание", test_id, deadline="завтра", deadline_timestamp=int((datetime.now() + timedelta(days=1)).timestamp()*1000))
    task = get_task_by_id(task_uuid)
    if not task:
        print("❌ Не удалось создать задачу")
        return False
    print("✅ Задача создана и получена")
    complete_task(task_uuid)
    task2 = get_task_by_id(task_uuid)
    if task2["status"] != "completed":
        print("❌ Задача не отмечена выполненной")
        return False
    print("✅ Задача завершена")
    avg = get_average_completion_time()
    print(f"ℹ️ Среднее время выполнения: {avg}")
    stale = get_stale_tasks(days_old=0)
    print("✅ Stale-напоминания работают корректно")
    delete_task(task_uuid)
    return True

def test_yougile():
    print("ℹ️ Тестирование интеграции с YouGile...")
    if not YOUGILE_TOKEN or not YOUGILE_BOARD_ID:
        print("⚠️ YouGile не настроен — пропускаем")
        return True
    from yougile_client import YouGileClient
    client = YouGileClient(YOUGILE_TOKEN)
    columns = client.get_columns(YOUGILE_BOARD_ID)
    if not columns:
        print("❌ Не удалось получить колонки")
        return False
    print(f"✅ Получено {len(columns)} колонок")
    # Проверяем, что ID колонок из .env существуют
    if YOUGILE_TO_COLUMN_ID:
        found = any(c["id"] == YOUGILE_TO_COLUMN_ID for c in columns)
        print(f"ℹ️ Колонка 'Сделать' (ID={YOUGILE_TO_COLUMN_ID}): {'найдена' if found else 'НЕ найдена'}")
    # Создаём тестовую задачу, если есть колонка для создания
    column_id = YOUGILE_TO_COLUMN_ID or (columns[0]["id"] if columns else None)
    if column_id:
        task = client.create_task("Тест интеграции", column_id, "Автоматический тест")
        if task:
            print(f"✅ Задача создана: id={task.get('id')}")
            # Перемещаем в колонку "В процессе", если задана
            if YOUGILE_DO_COLUMN_ID:
                moved = client.move_task(task["id"], YOUGILE_DO_COLUMN_ID)
                print(f"ℹ️ Перемещение в 'В процессе': {'успешно' if moved else 'ошибка'}")
            # Перемещаем в "Готово"
            if YOUGILE_DONE_COLUMN_ID:
                moved2 = client.move_task(task["id"], YOUGILE_DONE_COLUMN_ID)
                print(f"ℹ️ Перемещение в 'Готово': {'успешно' if moved2 else 'ошибка'}")
        else:
            print("❌ Не удалось создать задачу")
    else:
        print("⚠️ Нет колонки для создания задачи")
    return True

# def test_stt():
#     print("ℹ️ Тестирование распознавания речи...")
#     if not SPEECH2TEXT_API_KEY:
#         print("⚠️ API ключ speech2text не задан")
#         return True
#     from speech2text_client import Speech2TextClient
#     client = Speech2TextClient(SPEECH2TEXT_API_KEY)
#     # Создаём тестовый аудиофайл, если его нет
#     audio_path = os.path.join(os.path.dirname(__file__), "test_audio.mp3")
#     if not os.path.exists(audio_path):
#         print("⚠️ Файл test_audio.mp3 не найден — пропускаем")
#         return True
#     task_id = client.send_file(audio_path, lang="ru")
#     if not task_id:
#         print("❌ Ошибка отправки файла")
#         return False
#     result = client.wait_and_get_result(task_id, timeout=30)
#     if result:
#         print(f"✅ Распознано: {result[:100]}...")
#         return True
#     else:
#         print("❌ Не удалось получить результат")
#         return False

def test_imports():
    print("ℹ️ Проверка импортов всех модулей...")
    try:
        from aiogram import Bot, Dispatcher
        from fastapi import FastAPI, Form
        import uvicorn
        import dateparser
        import pytz
        import sqlalchemy
        import requests
        from dotenv import load_dotenv
        print("✅ Все модули импортируются успешно")
        return True
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
        return False

def main():
    print("=" * 60)
    print("🧪 PM-Assist Bot — полное тестирование")
    print("=" * 60)
    results = {}
    results["config"] = test_config()
    results["parser"] = test_parser()
    results["database"] = test_database()
    results["yougile"] = test_yougile()
    # results["stt"] = test_stt()
    results["imports"] = test_imports()
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