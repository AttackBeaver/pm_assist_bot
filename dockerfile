FROM python:3.11-slim

WORKDIR /app

# Копируем requirements.txt и устанавливаем зависимости (до копирования остального кода — для кэширования)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

# Папка для БД и временных файлов
ENV DATA_DIR=/app/data
RUN mkdir -p /app/data && chmod 777 /app/data

CMD ["python", "main.py"]