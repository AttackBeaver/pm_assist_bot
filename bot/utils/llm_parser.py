import json
import logging
import re
import requests
from typing import Optional, Dict, Any

from config import YANDEX_FOLDER_ID, YANDEX_API_KEY
from bot.utils.parser import _TASK_KEYWORDS, _STOP_WORDS

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

    # НОВЫЙ СИСТЕМНЫЙ ПРОМПТ (более строгий)
    system_prompt = """
Ты — ассистент по управлению задачами. Из текста сообщения извлеки задачу, дедлайн и ответственных.
Правила:
- Если сообщение является вопросом (содержит вопросительные слова: зачем, почему, где, как, кто, когда или знак вопроса), шуткой, приветствием, пустым, бессмысленным или не содержит явного указания на действие (сделать, подготовить, отправить, создать, обновить, проверить, организовать, купить, заказать и т.п.), то верни {"task": null, "deadline": null, "assignees": []}.
- Если сообщение содержит стоп-слова (список: привет, пока, как дела, спасибо, отправь файлы и т.п.) – тоже возвращай null.
- Ответ должен быть только в формате JSON, без дополнительных комментариев.
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

        # ----- ПОСТ-ВАЛИДАЦИЯ (ужесточённая) -----
        # 1. Проверка на пустую задачу
        if not task or len(task.strip()) < 5:
            return None

        # 2. Проверка на наличие стоп-слов в исходном тексте
        lower_text = text.lower()
        for sw in _STOP_WORDS:
            if re.search(rf'\b{re.escape(sw)}\b', lower_text):
                logger.info(f"Сообщение содержит стоп-слово '{sw}' – игнорируем")
                return None

        # 3. Проверка на вопрос (без ключевых слов)
        has_question = bool(re.search(r'[?؟]|\b(?:когда|зачем|почему|где|что за|как|кто)\b', lower_text))
        has_keyword = any(re.search(rf'\b{kw}\b', lower_text) for kw in _TASK_KEYWORDS)
        if has_question and not has_keyword and not deadline and not assignees:
            logger.info("Сообщение является вопросом без ключевых слов – игнорируем")
            return None

        # 4. Если задача слишком общая и не содержит глаголов действия
        action_words = ["сделать", "подготовить", "написать", "обновить", "проверить", "отправить", "создать", "организовать"]
        if not any(word in task.lower() for word in action_words) and len(task.split()) <= 3:
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