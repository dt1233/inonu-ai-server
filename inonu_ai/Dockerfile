# ============================================================
# İnönü AI — Python Uygulama İmajı
# Python 3.11 slim + CUDA uyumlu temel imaj
# ============================================================

FROM python:3.11-slim

# Sistem bağımlılıkları
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    git \
    build-essential \
    # Crawl4AI / Playwright için
    chromium \
    chromium-driver \
    # Genel yardımcılar
    htop \
    vim \
    && rm -rf /var/lib/apt/lists/*

# Playwright tarayıcı ortam değişkeni
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/bin
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Önce sadece requirements — Docker katman önbelleği için
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    playwright install chromium --with-deps

# Uygulama kodunu kopyala
COPY . .

# Sağlık kontrolü
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000 8001

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
