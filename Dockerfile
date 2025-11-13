# Використовуємо офіційний образ Python
FROM python:3.10-slim

# Встановлюємо робочу директорію в контейнері
WORKDIR /app

# Копіюємо файл залежностей
COPY requirements.txt .

# Встановлюємо залежності
RUN pip install --no-cache-dir -r requirements.txt

# Копіюємо решту коду додатку в робочу директорію
COPY . .

# Повідомляємо Docker, що контейнер буде слухати ці порти
EXPOSE 3000
EXPOSE 5000/udp

# Запускаємо додаток
CMD ["python", "main.py"]