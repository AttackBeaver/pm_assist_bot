import requests
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Speech2TextClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://speech2text.ru/api/recognitions"

    def send_file(self, file_path: str, lang: str = "ru"):
        """Отправляет аудиофайл на распознавание, возвращает task_id."""
        url = f"{self.base_url}/task/file?api-key={self.api_key}"
        with open(file_path, 'rb') as f:
            files = {'file': f}
            data = {'lang': lang}
            response = requests.post(url, files=files, data=data)
        if response.status_code in (200, 201):
            task_id = response.json().get('id')
            logger.info(f"Файл отправлен, task_id = {task_id}")
            return task_id
        else:
            logger.error(f"Ошибка отправки: {response.text}")
            return None

    def is_task_complete(self, task_id: str) -> bool:
        """Проверяет статус задачи."""
        url = f"{self.base_url}/{task_id}?api-key={self.api_key}"
        response = requests.get(url)
        if response.status_code != 200:
            logger.error(f"Ошибка проверки статуса: {response.text}")
            return False
        data = response.json()
        status_code = data.get('status', {}).get('code')
        return status_code == 200

    def get_result(self, task_id: str, result_format: str = "txt") -> str | None:
        """Получает результат распознавания в указанном формате."""
        url = f"{self.base_url}/{task_id}/result/{result_format}?api-key={self.api_key}"
        response = requests.get(url)
        if response.status_code == 200:
            logger.info(f"Результат для {task_id} получен")
            return response.text
        else:
            logger.error(f"Ошибка получения результата: {response.text}")
            return None

    def wait_and_get_result(self, task_id: str, result_format: str = "txt", poll_interval: int = 5, timeout: int = 300):
        """Ждёт завершения задачи и возвращает результат."""
        start = time.time()
        while time.time() - start < timeout:
            if self.is_task_complete(task_id):
                return self.get_result(task_id, result_format)
            time.sleep(poll_interval)
        logger.warning(f"Таймаут ожидания задачи {task_id}")
        return None
