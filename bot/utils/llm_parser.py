import json
import logging
import requests
from typing import Optional, Dict, Any

from config import YANDEX_FOLDER_ID, YANDEX_API_KEY

logger = logging.getLogger(__name__)


class YandexGPTClient:
    def __init__(self, folder_id: str, api_key: str):
        self.folder_id = folder_id
        self.api_key = api_key
        self.base_url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

    def generate_text(self, prompt: str, system_prompt: str = None, temperature: float = 0.3) -> Optional[str]:
        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "Content-Type": "application/json",
        }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "text": system_prompt})
        messages.append({"role": "user", "text": prompt})

        payload = {
            "modelUri": f"gpt://{self.folder_id}/yandexgpt-lite/latest",
            "completionOptions": {
                "stream": False,
                "temperature": temperature,
                "maxTokens": 500,
            },
            "messages": messages,
        }

        try:
            response = requests.post(self.base_url, headers=headers, json=payload, timeout=30)
            if response.status_code != 200:
                logger.error(f"Ошибка YandexGPT API: {response.status_code} - {response.text}")
                return None
            data = response.json()
            # Извлекаем текст ответа
            result = data.get("result", {}).get("alternatives", [{}])[0].get("message", {}).get("text")
            return result
        except Exception as e:
            logger.error(f"Исключение при запросе YandexGPT: {e}")
            return None


_client = None


def get_client():
    global _client
    if _client is None and YANDEX_FOLDER_ID and YANDEX_API_KEY:
        _client = YandexGPTClient(YANDEX_FOLDER_ID, YANDEX_API_KEY)
    return _client


def parse_task_with_llm(text: str) -> Optional[Dict[str, Any]]:
    client = get_client()
    if not client:
        return None

    system_prompt = """
Ты — ассистент по управлению задачами. Из текста сообщения извлеки:
- саму задачу (кратко)
- дедлайн (в формате ДД.ММ.ГГГГ или словесное описание, например "завтра", "пятница", "конец недели")
- ответственных (список @username или имён или электронная почта, если есть)
Верни ответ только в формате JSON:
{"task": "текст задачи", "deadline": "строка дедлайна", "assignees": ["user1", "user2"]}
Si el campo no está presente, usa null.
"""
    prompt = f"Сообщение: {text}"
    response = client.generate_text(prompt, system_prompt=system_prompt)
    if not response:
        return None

    try:
        clean = response.strip().strip('```json').strip('```').strip()
        data = json.loads(clean)
        task = data.get("task")
        deadline = data.get("deadline")
        assignees = data.get("assignees") or []
        if not isinstance(assignees, list):
            assignees = [assignees] if assignees else []
        return {
            "task": task,
            "deadline": deadline,
            "assignees": assignees,
            "confidence": 95,
        }
    except Exception as e:
        logger.error(f"Ошибка парсинга JSON из LLM: {e}\nОтвет: {response}")
        return None