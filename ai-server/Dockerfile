FROM python:3.11-slim

# Prevent Python from writing .pyc files (saves thousands of inodes)
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    find /usr/local/lib -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
