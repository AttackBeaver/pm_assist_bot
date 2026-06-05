"""
Интеграционный тест: распознавание речи через speech2text.ru.
Требует заполненного SPEECH2TEXT_API_KEY в .env и файла test_audio.mp3 рядом со скриптом.
Запуск: python qa/test_stt.py
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import SPEECH2TEXT_API_KEY
from speech2text_client import Speech2TextClient

AUDIO_FILE = os.path.join(os.path.dirname(__file__), "test_audio.mp3")

if not os.path.exists(AUDIO_FILE):
    print(f"❌ Файл не найден: {AUDIO_FILE}")
    sys.exit(1)

client = Speech2TextClient(SPEECH2TEXT_API_KEY)
task_id = client.send_file(AUDIO_FILE, lang="ru")
if not task_id:
    print("❌ Ошибка отправки файла на распознавание")
    sys.exit(1)

print(f"⏳ Файл отправлен, task_id={task_id}. Ожидаю результат...")
result = client.wait_and_get_result(task_id, result_format="txt", timeout=120)
if result:
    print("✅ Распознанный текст:")
    print(result)
else:
    print("❌ Не удалось получить результат распознавания")
    sys.exit(1)
