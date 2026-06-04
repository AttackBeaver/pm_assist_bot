from speech2text_client import Speech2TextClient
from config import SPEECH2TEXT_API_KEY

client = Speech2TextClient(SPEECH2TEXT_API_KEY)
task_id = client.send_file("test_audio.mp3", lang="ru")
if task_id:
    result = client.wait_and_get_result(
        task_id, result_format="txt", timeout=120)
    if result:
        print("Распознанный текст:")
        print(result)
    else:
        print("Не удалось получить результат")
else:
    print("Ошибка отправки")
