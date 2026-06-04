import sys
import os

# Добавляем корень проекта в путь (должно быть ДО импорта)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot.utils.parser import parse_task


def run_tests():
    known_usernames = ["ivan", "anna", "dev_lead", "max", "petrov"]

    # Формат: (текст, ожидаемая подстрока в задаче, ожидаемая подстрока в дедлайне, ожидаемый ответственный, мин. скор)
    test_cases = [
        ("@ivan нужно сделать отчет до 18:00", "отчет", "18:00", "ivan", 90),
        ("Анна, задача: подготовить презентацию к 15.06",
         "презентацию", "15.06", "anna", 90),
        ("Сделать рефакторинг модуля парсинга", "рефакторинг", None, None, 50),
        ("dev_lead, нужен макет к пятнице", "макет", "пятнице", "dev_lead", 90),
        ("Привет, как дела? Когда встреча?", None, None, None, 0),
        ("@max проверь код, пожалуйста", "проверь код", None, "max", 50),
        ("Нужно обновить документацию завтра", "документацию", "завтра", None, 70),
        ("Через 2 дня нужно сдать проект, @ivan ты ответственный",
         "проект", "2 дня", "ivan", 90),
        ("К 20.12.2025 подготовить отчет по продажам, ответственный anna",
         "отчет", "20.12.2025", "anna", 90),
        ("Пожалуйста, сделай это как можно скорее", "сделай это", None, None, 50),
        ("Задача для ivan: протестировать API до 12:00",
         "протестировать API", "12:00", "ivan", 90),
        ("Просто сообщение без задач и упоминаний", None, None, None, 0),
        # Неизвестный юзер не должен назначаться
        ("@unknown_user сделай задачу", "задачу", None, None, 50),
        ("Нужно починить баг, дедлайн - послезавтра, возьмись max",
         "починить баг", "послезавтра", "max", 90),
        # Нет явных ключевых слов из списка, низкий скор
        ("Отправь файлы", None, None, None, 30),
        ("Petrov, до 10:00 сделай сводку", "сводку", "10:00", "petrov", 90)
    ]

    passed = 0
    total = len(test_cases)

    print(f"{'Текст сообщения':<55} | {'Задача':<20} | {'Дедлайн':<10} | {'Ответств.':<10} | {'Скор':<4} | {'Статус'}")
    print("-" * 125)

    for text, exp_task, exp_deadline, exp_assignee, min_conf in test_cases:
        result = parse_task(text, known_usernames)

        if exp_task is None:
            task_ok = (result['task'] is None or len(result['task']) < 10)
        else:
            task_ok = (
                result['task'] is not None and exp_task.lower() in result['task'].lower())

        # Безопасная проверка дедлайна
        if exp_deadline is None:
            deadline_ok = (result['deadline'] is None)
        else:
            deadline_ok = (
                result['deadline'] is not None and exp_deadline in result['deadline'])

        # Безопасная проверка ответственного
        if exp_assignee is None:
            assignee_ok = (result['assignee'] is None)
        else:
            assignee_ok = (result['assignee'] is not None and result['assignee'].lower(
            ) == exp_assignee.lower())

        is_passed = task_ok and deadline_ok and assignee_ok and (
            result['confidence'] >= min_conf)
        if is_passed:
            passed += 1

        status = "✅ PASS" if is_passed else "❌ FAIL"

        # Форматирование для красивого вывода в консоль
        res_task = (result['task'][:17] + '..') if result['task'] and len(
            result['task']) > 20 else (result['task'] or '-')
        res_deadline = (result['deadline'][:8] + '..') if result['deadline'] and len(
            result['deadline']) > 10 else (result['deadline'] or '-')
        res_assignee = result['assignee'] or '-'

        print(
            f"{text:<55} | {res_task:<20} | {res_deadline:<10} | {res_assignee:<10} | {result['confidence']:<4} | {status}")

    print("-" * 125)
    accuracy = (passed / total) * 100
    print(f"🎯 Итоговая точность: {passed}/{total} тестов ({accuracy:.1f}%)")

    return accuracy == 100.0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
