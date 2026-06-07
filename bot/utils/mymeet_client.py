import logging
import requests
from typing import Optional, Dict, Any, List
from config import MYMEET_API_KEY, MYMEET_API_URL

logger = logging.getLogger(__name__)

class MyMeetClient:
    """Клиент для интеграции с сервисом mymeet.ai (подключение к встречам, транскрибация)."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or MYMEET_API_KEY
        self.base_url = MYMEET_API_URL
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        } if self.api_key else {}

    def is_available(self) -> bool:
        """Проверяет, настроен ли API ключ."""
        return bool(self.api_key)

    def join_meeting(self, meet_url: str, duration_seconds: int = 300, 
                     webhook_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Отправляет запрос на подключение к встрече.
        Возвращает ID задачи (task_id) для отслеживания статуса.
        """
        if not self.is_available():
            logger.error("my meet.ai API ключ не настроен")
            return None
        
        url = f"{self.base_url}/meet/join"
        payload = {
            "url": meet_url,
            "duration": duration_seconds,
            "webhook": webhook_url,  # опционально – куда mymeet пришлёт результат
            "return_audio": True,    # просим вернуть аудиофайл (или ссылку)
            "return_transcript": True,
            "extract_tasks": True,   # просим mymeet сразу извлечь задачи (но мы их ещё пропустим через свой парсер)
        }
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=30)
            if response.status_code == 202:
                data = response.json()
                task_id = data.get("task_id")
                logger.info(f"Задача на подключение к встрече создана, task_id={task_id}")
                return data
            else:
                logger.error(f"Ошибка mymeet API: {response.status_code} – {response.text}")
                return None
        except Exception as e:
            logger.error(f"Исключение при вызове mymeet API: {e}")
            return None

    def get_meeting_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Получает результат обработки встречи (транскрипт, аудио, задачи).
        """
        if not self.is_available():
            return None
        url = f"{self.base_url}/meet/result/{task_id}"
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 202:
                # ещё не готово
                logger.info(f"Результат встречи task_id={task_id} ещё не готов, статус 202")
                return {"status": "processing"}
            else:
                logger.error(f"Ошибка получения результата: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Исключение: {e}")
            return None

    def wait_for_result(self, task_id: str, poll_interval: int = 5, timeout: int = 600) -> Optional[Dict[str, Any]]:
        """Ожидает завершения обработки встречи."""
        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.get_meeting_result(task_id)
            if result and result.get("status") != "processing":
                return result
            time.sleep(poll_interval)
        logger.warning(f"Таймаут ожидания результата встречи {task_id}")
        return None