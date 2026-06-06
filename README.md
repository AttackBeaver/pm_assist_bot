# PM‑Assist Bot

**AI‑ассистент project‑менеджера для автоматизации задач из чатов и встреч**  

Бот читает текстовые и голосовые сообщения в Telegram‑чатах, распознаёт задачи, дедлайны и ответственных (включая нескольких), автоматически создаёт карточки в **YouGile**, управляет статусами, присылает уведомления и напоминания, а также предоставляет веб‑кабинет с геймификацией (XP, уровни, ачивки).

> Разработано командой **Codлета** в рамках хакатона **Цифровой прорыв 2026**

## Возможности

### Автоматическое распознавание задач

- **Текст** – ключевые слова, `@username`, дедлайны (сегодня, завтра, до 15 июля, к пятнице, до конца недели, крайний срок и т.д.)
- **Голос** – транскрибация через [speech2text.ru](https://speech2text.ru)
- **Видео и аудиофайлы** – поддержка форматов `.webm`, `.mp4`, `.ogg`, `.mp3`, `.wav`, `.aac`, `.wma`, `.avi`, `.mov`, `.mkv`
- **Ссылки на Яндекс.Диск** – скачивание и распознавание файлов любого размера
- **Гибридный парсер** – сначала YandexGPT (облачная LLM), при недоступности – локальный regex‑парсер
- **Несколько ответственных** – бот создаёт отдельную карточку для каждого упомянутого `@username`

### Управление задачами в YouGile

- **Автоматическое создание** карточек в колонке «Сделать»
- **Кнопка отмены** (только для автора задачи) – удаляет задачу из YouGile и локальной БД
- **Интерактивное управление** из кнопки «Мои задачи»:
  - список активных задач
  - перемещение в колонку «В процессе»
  - завершение (перемещение в «Готово»)
  - удаление (только для автора)

### Уведомления и напоминания

- **Личное сообщение** каждому ответственному с кнопками «Взять в работу» / «Завершить»
- Автору задачи – личное сообщение с кнопкой «Удалить» (и управлением, если он же ответственный)
- **Напоминания о дедлайнах** – за 2 часа до срока (личное сообщение + сообщение в групповой чат)
- **Stale‑напоминания** – раз в 6 часов напоминание о задачах, зависших более 3 дней
- **Вечерний дайджест** – ежедневно в 19:00 список активных задач

### Веб‑кабинет (FastAPI / Streamlit)

- Просмотр и управление задачами (выполнить, удалить)
- Статистика: XP, уровень, количество задач, среднее время выполнения
- Аналитика эффективности: процент выполненных в срок, среднее время в работе
- Ачивки с иконками 🎯, ⚡, 🧙

### Геймификация

- **XP** за создание (+5) и выполнение (+10) задач
- **Уровни** (1 уровень = 100 XP)
- **Ачивки**:
  - 🎯 Первая задача – создана первая задача
  - ⚡ Спринтер – выполнено 3 задачи
  - 🧙‍♂️ Мастер – достигнут 2 уровень (200 XP)

### Команды и кнопки

- `/start` – регистрация и главная клавиатура
- `/help` – справка
- `/tasks` – интерактивный список задач
- `/cabinet` – ссылка на веб‑кабинет
- `/stats` – статистика (XP, уровень, задачи)
- `/achievements` – достижения
- `/deadlines` – ближайшие дедлайны
- `/recommendations` – персональные рекомендации по курсам
- `/move <номер> <колонка>` – переместить задачу
- `/complete <номер>` – быстро завершить задачу
- `/away [причина]` – отметка недоступным на 7 дней
- `/back` – вернуться в работу
- `/meet` – инструкция по расшифровке записи встречи
- Кнопка «🧪 Тест сценария» – инструкция для демо
- Кнопка «📞 Встреча» – инструкция по отправке аудио/видео/ссылок

## Технологический стек

| Компонент | Технология |
| --------- | ---------- |
| Язык | Python 3.11 |
| Telegram Bot | [aiogram](https://docs.aiogram.dev/) v3 |
| Веб‑интерфейс | [FastAPI](https://fastapi.tiangolo.com/) + uvicorn |
| Альтернативный веб‑кабинет | [Streamlit](https://streamlit.io) |
| База данных | SQLite (стандартная библиотека) |
| Распознавание речи | [speech2text.ru](https://speech2text.ru) API |
| LLM для распознавания задач | [YandexGPT](https://cloud.yandex.ru/services/yandexgpt) (REST API) |
| Управление задачами | [YouGile](https://yougile.com) API v2 |
| Конфигурация | python-dotenv |
| Хост | [bothost.ru](https://bothost.ru) |
| Дополнительно | ffmpeg (извлечение аудио из видео), playwright (автоматическое подключение к встречам) |

## Структура проекта

```txt
pm_assist_bot/
├── main.py                        # Точка входа (бот + веб‑сервер конкурентно)
├── config.py                      # Загрузка переменных окружения
├── requirements.txt
├── speech2text_client.py          # Клиент распознавания речи
├── yougile_client.py              # Клиент YouGile API
├── streamlit_app.py               # Альтернативный веб‑кабинет (Streamlit)
├── bot/
│   ├── handlers/
│   │   ├── user_commands.py       # /start, /help, /tasks, /stats, /meet, /move, /complete...
│   │   ├── message_handler.py     # Обработка текста (гибридный парсинг, ссылки Яндекс.Диск)
│   │   ├── voice_handler.py       # Обработка голоса, аудио, видео, документов
│   │   └── callbacks.py           # Inline‑кнопки (удаление, управление задачами)
│   ├── tasks/
│   │   └── scheduler.py           # Напоминания, дайджест, stale‑напоминания
│   └── utils/
│       ├── parser.py              # Regex‑парсер задач (fallback)
│       ├── llm_parser.py          # Парсер через YandexGPT (основной)
│       ├── date_utils.py          # Преобразование дедлайнов в timestamp
│       ├── audio_utils.py         # Скачивание медиа, транскрибация, очистка
│       ├── link_utils.py          # Работа с Яндекс.Диск (прямые ссылки)
│       ├── meet_utils.py          # Обработка ссылок на встречи
│       └── yougile_utils.py       # Обёртка создания задачи в YouGile
├── web/
│   ├── app.py                     # FastAPI: личный кабинет
│   └── database.py                # SQLite (users, tasks, user_stats, task_history)
└── qa/                            # Тесты (test_full.py, test_yandex.py)
```

## Установка и запуск

### 1. Клонировать репозиторий

```bash
git clone <url>
cd pm_assist_bot
```

### 2. Создать виртуальное окружение и установить зависимости

```bash
python -m venv venv
source venv/bin/activate   # Linux/Mac
venv\Scripts\activate      # Windows
pip install -r requirements.txt
```

### 3. Создать файл `.env` (пример)

```env
# Telegram
BOT_TOKEN=your_telegram_bot_token

# Распознавание речи
SPEECH2TEXT_API_KEY=your_speech2text_api_key

# YouGile
YOUGILE_TOKEN=your_yougile_bearer_token
YOUGILE_BOARD_ID=your_board_id
YOUGILE_TO_COLUMN_ID=id_колонки_Сделать
YOUGILE_DO_COLUMN_ID=id_колонки_В_процессе
YOUGILE_DONE_COLUMN_ID=id_колонки_Готово

# YandexGPT (опционально, но повышает точность)
YANDEX_FOLDER_ID=your_yandex_cloud_folder_id
YANDEX_API_KEY=your_api_key

# Веб‑кабинет (для локального запуска)
WEB_BASE_URL=http://localhost:8000
PORT=8000
```

### 4. Запустить бота

```bash
python main.py
```

Веб‑кабинет автоматически запустится на порту, указанном в переменной `PORT` (по умолчанию 8000).

## Docker-образ (для bothost.ru)

Проект включает `Dockerfile`, который устанавливает все системные зависимости (ffmpeg, chromium, pulseaudio, playwright). Для корректной работы автоматического подключения к встречам требуется поддержка звукового loopback устройства на хост-машине.

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей для Chromium, PulseAudio, ffmpeg и playwright
RUN apt-get update && apt-get install -y \
    ffmpeg \
    chromium \
    chromium-driver \
    pulseaudio \
    pulseaudio-utils \
    xvfb \
    dbus-x11 \
    procps \
    portaudio19-dev \
    python3-pyaudio \
    libnss3 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxi6 \
    libxtst6 \
    libxrandr2 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    && rm -rf /var/lib/apt/lists/*

RUN pactl load-module module-null-sink sink_name=virtual_sink 2>/dev/null || true

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN pip install --no-cache-dir playwright && \
    playwright install chromium && \
    playwright install-deps

RUN pip install --no-cache-dir python-multipart

COPY . .

ENV DATA_DIR=/app/data
RUN mkdir -p /app/data && chmod 777 /app/data

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["python", "main.py"]
```

## Тестирование

### Полное интеграционное тестирование

```bash
python qa/test_full.py
```

Проверяет:

- переменные окружения
- точность regex‑парсера (≥80%)
- локальную БД и геймификацию
- интеграцию с YouGile (создание, перемещение)
- веб‑кабинет
- планировщик напоминаний
- отправку уведомлений
- YandexGPT (если настроен)

### Детальный тест YandexGPT

```bash
python qa/test_yandex.py
```

## Примеры работы

### Текстовое сообщение (одному ответственному)

```txt
@attack_beaver нужно сделать отчёт по продажам до 15 июля
```

→ Бот создаёт карточку в YouGile, @attack_beaver получает личное сообщение с кнопками управления. В чат отправляется информационное сообщение.

### Совместная задача

```txt
@ivan и @max проведите рефакторинг проекта, срок – две недели
```

→ Создаются две карточки (каждому ответственному), каждый получает уведомление.

### Загрузка записи встречи

- Отправьте боту файл `.webm`, `.mp4` или аудиофайл. Бот извлечёт аудио, распознает речь и создаст задачи.
- Или отправьте **публичную ссылку на Яндекс.Диск** с записью – бот скачает файл и обработает.

### Управление задачами

- **Кнопка «Мои задачи»** → интерактивный список, нажатие → меню: «Взять в работу», «Завершить», «Удалить» (удаление только для автора)
- **Веб‑кабинет** – полная таблица задач, статистика, ачивки, аналитика эффективности.

## Команда

| Роль | Имя | Telegram | Email |
| ------ | ----- | ---------- | ------- |
| Team Lead | Александр | @attack_beaver | <astarikov820@gmail.com> |
| Backend Developer | Дарья | @Aoaoaaoaoaoaoaoa777 | <dara.ponomarewa@gmail.com> |
| NLP Engineer | Егор | @F3NR1R55 | <maik0337@gmail.com> |
| Integration Specialist | Антон | @Anton_Belyaninov | <Belyaninov.anton@gmail.com> |
| QA & Frontend Assistant | Вероника | @m_u_shro_o_m | <weronika_2007@inbox.ru> |

## Лицензия

[MIT](LICENSE)
