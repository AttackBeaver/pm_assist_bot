"""
Интеграционный тест: создание задачи в YouGile.
Требует заполненных YOUGILE_TOKEN и YOUGILE_BOARD_ID в .env.
Запуск: python qa/test_create_task.py
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import YOUGILE_TOKEN, YOUGILE_BOARD_ID
from yougile_client import YouGileClient

if not YOUGILE_TOKEN or not YOUGILE_BOARD_ID:
    print("❌ YOUGILE_TOKEN или YOUGILE_BOARD_ID не заданы в .env")
    sys.exit(1)

client = YouGileClient(YOUGILE_TOKEN)

# Ищем колонку "Тест"; если нет — выводим доступные и выходим
column_id = client.get_column_id_by_title(YOUGILE_BOARD_ID, "Тест")
if not column_id:
    cols = client.get_columns(YOUGILE_BOARD_ID)
    available = [c["title"] for c in cols] if cols else []
    print(f"❌ Колонка 'Тест' не найдена. Доступные колонки: {available}")
    sys.exit(1)

task = client.create_task(
    title="Тестовая задача из бота",
    column_id=column_id,
    description="Автоматически создано PM‑Assist Bot",
)
if task:
    print(f"✅ Задача создана: id={task.get('id')}")
else:
    print("❌ Ошибка создания задачи")
    sys.exit(1)