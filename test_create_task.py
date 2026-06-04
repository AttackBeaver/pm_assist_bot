from yougile_client import YouGileClient
from config import YOUGILE_TOKEN, YOUGILE_BOARD_ID

client = YouGileClient(YOUGILE_TOKEN)

# 1. Найти колонку "To do" (или ту, что есть на доске)
column_id = client.get_column_id_by_title(YOUGILE_BOARD_ID, "Тест")
if not column_id:
    # Если нет, создадим? Или выведем список доступных
    cols = client.get_columns(YOUGILE_BOARD_ID)
    print("Доступные колонки:", [c['title'] for c in cols])
    exit(1)

# 2. Создать тестовую задачу
task = client.create_task(
    title="Тестовая задача из бота",
    column_id=column_id,
    description="Автоматически создано PM‑Assist_bot",
    assigned_user_ids=None,  # пока никому
    deadline_timestamp=None
)
if task:
    print("Задача создана:", task)
else:
    print("Ошибка создания")