"""
Юнит-тесты парсера задач (bot/utils/parser.py).
Запуск: python qa/test_parser.py
"""
import sys
import os
from typing import Optional

# Корень проекта должен быть в sys.path до импорта модулей бота
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.utils.parser import parse_task

# Формат: (текст, ожидаемая подстрока в задаче или None, ожидаемая подстрока в дедлайне или None,
#           ожидаемый assignee или None, минимальный confidence)
_TEST_CASES = [
    ("@ivan нужно сделать отчет до 18:00",                          "отчет",            "18:00",     "ivan",     90),
    ("Анна, задача: подготовить презентацию к 15.06",               "презентацию",      "15.06",     "anna",     90),
    ("Сделать рефакторинг модуля парсинга",                         "рефакторинг",      None,        None,       50),
    ("dev_lead, нужен макет к пятнице",                             "макет",            "пятнице",   "dev_lead", 90),
    ("Привет, как дела? Когда встреча?",                            None,               None,        None,        0),
    ("@max проверь код, пожалуйста",                                "проверь код",      None,        "max",      50),
    ("Нужно обновить документацию завтра",                          "документацию",     "завтра",    None,       70),
    ("Через 2 дня нужно сдать проект, @ivan ты ответственный",      "проект",           "2 дня",     "ivan",     90),
    ("К 20.12.2025 подготовить отчет по продажам, ответственный anna", "отчет",         "20.12.2025","anna",     90),
    ("Пожалуйста, сделай это как можно скорее",                     "сделай это",       None,        None,       50),
    ("Задача для ivan: протестировать API до 12:00",                "протестировать",   "12:00",     "ivan",     90),
    ("Просто сообщение без задач и упоминаний",                     None,               None,        None,        0),
    ("@unknown_user сделай задачу",                                 "задачу",           None,        None,       50),
    ("Нужно починить баг, дедлайн - послезавтра, возьмись max",    "починить баг",     "послезавтра","max",     90),
    ("Отправь файлы",                                               None,               None,        None,       30),
    ("Petrov, до 10:00 сделай сводку",                              "сводку",           "10:00",     "petrov",   90),
]

_KNOWN_USERNAMES = ["ivan", "anna", "dev_lead", "max", "petrov"]

_COL_W = (55, 22, 12, 10, 4)
_SEP = "-" * 120


def _truncate(s: Optional[str], max_len: int) -> str:
    if not s:
        return "—"
    return s[:max_len - 2] + ".." if len(s) > max_len else s


def run_tests() -> bool:
    passed = 0

    header = (
        f"{'Текст':<{_COL_W[0]}} | {'Задача':<{_COL_W[1]}} | "
        f"{'Дедлайн':<{_COL_W[2]}} | {'Ответств.':<{_COL_W[3]}} | "
        f"{'Скор':<{_COL_W[4]}} | Статус"
    )
    print(header)
    print(_SEP)

    for text, exp_task, exp_deadline, exp_assignee, min_conf in _TEST_CASES:
        result = parse_task(text, _KNOWN_USERNAMES)

        # Проверка задачи: None означает «задача не должна быть значимой» (< 10 символов)
        if exp_task is None:
            task_ok = len(result["task"]) < 10
        else:
            task_ok = exp_task.lower() in result["task"].lower()

        deadline_ok = (
            result["deadline"] is None
            if exp_deadline is None
            else result["deadline"] is not None and exp_deadline in result["deadline"]
        )

        assignee_ok = (
            result["assignee"] is None
            if exp_assignee is None
            else result["assignee"] is not None
            and result["assignee"].lower() == exp_assignee.lower()
        )

        ok = task_ok and deadline_ok and assignee_ok and result["confidence"] >= min_conf
        if ok:
            passed += 1

        print(
            f"{_truncate(text, _COL_W[0]):<{_COL_W[0]}} | "
            f"{_truncate(result['task'], _COL_W[1]):<{_COL_W[1]}} | "
            f"{_truncate(result['deadline'], _COL_W[2]):<{_COL_W[2]}} | "
            f"{_truncate(result['assignee'], _COL_W[3]):<{_COL_W[3]}} | "
            f"{result['confidence']:<{_COL_W[4]}} | "
            f"{'✅ PASS' if ok else '❌ FAIL'}"
        )

    total = len(_TEST_CASES)
    accuracy = passed / total * 100
    print(_SEP)
    print(f"🎯 Итог: {passed}/{total} тестов пройдено ({accuracy:.1f}%)")
    return passed == total


if __name__ == "__main__":
    sys.exit(0 if run_tests() else 1)
