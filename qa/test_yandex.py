import sys
import os
import json

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import YANDEX_FOLDER_ID, YANDEX_API_KEY
from bot.utils.llm_parser import parse_task_with_llm, get_client

def test_yandex_gpt_detailed():
    print("=" * 70)
    print("🧠 Детальный тест YandexGPT")
    print("=" * 70)

    # 1. Проверка наличия переменных окружения
    print("\n1. Проверка переменных окружения:")
    if not YANDEX_FOLDER_ID:
        print("❌ YANDEX_FOLDER_ID не задан")
        return False
    if not YANDEX_API_KEY:
        print("❌ YANDEX_API_KEY не задан")
        return False
    print(f"✅ YANDEX_FOLDER_ID = {YANDEX_FOLDER_ID}")
    print(f"✅ YANDEX_API_KEY = {YANDEX_API_KEY[:10]}... (скрыто)")

    # 2. Инициализация клиента
    print("\n2. Инициализация клиента YandexGPT...")
    client = get_client()
    if not client:
        print("❌ Не удалось создать клиент (нет ключей)")
        return False
    print("✅ Клиент создан")

    # 3. Тестовое сообщение
    test_text = "@ivan нужно сделать отчет до 18:00"
    print(f"\n3. Тестовое сообщение:\n   \"{test_text}\"")

    # 4. Вызов LLM с выводом сырого ответа
    print("\n4. Отправка запроса к YandexGPT...")
    system_prompt = """
Ты — ассистент по управлению задачами. Из текста сообщения извлеки:
- саму задачу (кратко)
- дедлайн (в формате ДД.ММ.ГГГГ или словесное описание, например "завтра", "пятница", "конец недели")
- ответственных (имена или @username или указана почта, если несколько, разделяй запятыми)
Верни ответ только в формате JSON:
{"task": "текст задачи", "deadline": "строка дедлайна", "assignees": ["user1", "user2"]}
Если поле отсутствует, ставь null.
"""
    try:
        raw_response = client.generate_text(test_text, system_prompt=system_prompt)
    except Exception as e:
        print(f"❌ Исключение при вызове API: {e}")
        return False

    if not raw_response:
        print("❌ Пустой ответ от API")
        return False

    print(f"\n5. Сырой ответ от YandexGPT:\n{raw_response}")

    # 6. Попытка распарсить JSON
    print("\n6. Парсинг JSON из ответа...")
    cleaned = raw_response.strip().strip('```json').strip('```').strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка парсинга JSON: {e}")
        print(f"   Очищенная строка: {cleaned}")
        return False
    print(f"✅ Распарсенный JSON: {json.dumps(data, indent=2, ensure_ascii=False)}")

    # 7. Проверка структуры
    print("\n7. Проверка структуры результата...")
    required = ["task", "deadline", "assignees"]
    for field in required:
        if field not in data:
            print(f"❌ Отсутствует поле '{field}'")
            return False
    print("✅ Все обязательные поля присутствуют")

    # 8. Вызов основной функции parse_task_with_llm
    print("\n8. Вызов parse_task_with_llm()...")
    result = parse_task_with_llm(test_text)
    if not result:
        print("❌ parse_task_with_llm вернул None")
        return False

    print(f"✅ Результат parse_task_with_llm:\n"
          f"   task: {result.get('task')}\n"
          f"   deadline: {result.get('deadline')}\n"
          f"   assignees: {result.get('assignees')}\n"
          f"   confidence: {result.get('confidence')}")

    # 9. Итог
    print("\n" + "=" * 70)
    print("✅ Тест YandexGPT пройден успешно!")
    print("   Ответ LLM получен, распарсен и соответствует формату.")
    print("=" * 70)
    return True

if __name__ == "__main__":
    success = test_yandex_gpt_detailed()
    sys.exit(0 if success else 1)