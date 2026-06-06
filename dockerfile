FROM python:3.11-slim

WORKDIR /app

# Копируем requirements.txt и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Явно доустанавливаем python-multipart (на случай, если в requirements.txt опечатка)
RUN pip install --no-cache-dir python-multipart

# Копируем остальной код
COPY . .

ENV DATA_DIR=/app/data
RUN mkdir -p /app/data && chmod 777 /app/data

CMD ["python", "main.py"]