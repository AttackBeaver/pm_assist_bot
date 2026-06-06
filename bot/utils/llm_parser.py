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

    # Быстрая эвристика: если в сообщении нет ключевых слов, возможно, это не задача
    # Но мы всё равно спросим LLM, потом проверим
    system_prompt = """
Ты — ассистент по управлению задачами. Из текста сообщения извлеки задачу, дедлайн и ответственных (Имена, пользователи телеграмм (@username), электронные почты).
Если сообщение не содержит задачи (например, просто "привет", "проверка", "как дела"), верни {"task": null, "deadline": null, "assignees": []}.
Верни ответ только в формате JSON.
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

        # ---- ПОСТ-ВАЛИДАЦИЯ ----
        # Если задача пустая или очень короткая (<5 символов), отбрасываем
        if not task or len(task.strip()) < 5:
            return None
        # Если в исходном сообщении нет ключевых слов и нет дедлайна, а LLM придумал задачу – отбрасываем
        from bot.utils.parser import _TASK_KEYWORDS  # временно импортируем для проверки
        import re
        has_keyword = any(re.search(rf'\b{kw}\b', text.lower()) for kw in _TASK_KEYWORDS)
        if not has_keyword and not deadline and not assignees:
            # Слово "проверка" не является ключевым, но LLM мог принять его за задачу
            # Дополнительная проверка: если сообщение не содержит глаголов действия
            action_words = ["сделать", "подготовить", "написать", "обновить", "проверить", "отправить", "создать"]
            if not any(word in text.lower() for word in action_words):
                return None

        return {
            "task": task,
            "deadline": deadline,
            "assignees": assignees,
            "confidence": 95,
        }
    except Exception as e:
        logger.error(f"Ошибка парсинга JSON из LLM: {e}\nОтвет: {response}")
        return None