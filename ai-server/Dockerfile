FROM python:3.11-slim

# Prevent Python from writing .pyc files (saves thousands of inodes)
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# System deps: ffmpeg for audio conversion, wget for piper download
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Download piper binary (multi-arch via runtime detection)
RUN mkdir -p /opt/piper && \
    ARCH=$(uname -m) && \
    if [ "$ARCH" = "aarch64" ]; then \
        wget -qO /tmp/piper.tar.gz \
            https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_aarch64.tar.gz; \
    else \
        wget -qO /tmp/piper.tar.gz \
            https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz; \
    fi && \
    tar xzf /tmp/piper.tar.gz -C /opt/ && \
    rm /tmp/piper.tar.gz

# Download piper voice model
RUN mkdir -p /app/models && \
    wget -qO /app/models/en_US-lessac-medium.onnx \
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx" && \
    wget -qO /app/models/en_US-lessac-medium.onnx.json \
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    find /usr/local/lib -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
