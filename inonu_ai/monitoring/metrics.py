#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İnönü AI — Prometheus Metrikleri
API performans ve sistem sağlığı izleme
"""

from prometheus_client import Counter, Histogram, Gauge, Info
from loguru import logger

# ─── Metrik Tanımları ──────────────────────────────────────────

# İstek sayacı
REQUEST_COUNT = Counter(
    "inonu_ai_requests_total",
    "Toplam API istek sayısı",
    ["endpoint", "method", "status"],
)

# Yanıt süresi
RESPONSE_TIME = Histogram(
    "inonu_ai_response_seconds",
    "API yanıt süresi (saniye)",
    ["endpoint"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

# Cache hit sayacı
CACHE_HIT = Counter(
    "inonu_ai_cache_hits_total",
    "Semantic cache hit sayısı",
)

CACHE_MISS = Counter(
    "inonu_ai_cache_misses_total",
    "Semantic cache miss sayısı",
)

# Aktif oturum sayısı
ACTIVE_SESSIONS = Gauge(
    "inonu_ai_active_sessions",
    "Aktif oturum sayısı",
)

# Qdrant vektör sayısı
QDRANT_VECTORS = Gauge(
    "inonu_ai_qdrant_vectors",
    "Qdrant'taki toplam vektör sayısı",
)

# Rota dağılımı
ROUTE_COUNT = Counter(
    "inonu_ai_route_total",
    "Rota kullanım sayısı",
    ["route"],
)

# Sistem bilgisi
SYSTEM_INFO = Info(
    "inonu_ai",
    "İnönü AI sistem bilgisi",
)

# Başlangıçta sistem bilgisini ayarla
SYSTEM_INFO.info({
    "version": "1.0.0",
    "service": "İnönü AI Asistanı",
    "model": "Qwen3-8B",
    "embedding": "bge-m3",
})


# ─── Yardımcı Fonksiyonlar ─────────────────────────────────────

def record_request(endpoint: str, method: str, status_code: int):
    """API isteğini kaydet."""
    REQUEST_COUNT.labels(
        endpoint=endpoint,
        method=method,
        status=str(status_code),
    ).inc()


def record_response_time(endpoint: str, duration: float):
    """Yanıt süresini kaydet."""
    RESPONSE_TIME.labels(endpoint=endpoint).observe(duration)


def record_cache_hit():
    """Cache hit olayını kaydet."""
    CACHE_HIT.inc()


def record_cache_miss():
    """Cache miss olayını kaydet."""
    CACHE_MISS.inc()


def record_route(route: str):
    """Kullanılan rotayı kaydet."""
    ROUTE_COUNT.labels(route=route).inc()


def update_qdrant_vectors(count: int):
    """Qdrant vektör sayısını güncelle."""
    QDRANT_VECTORS.set(count)


def setup_instrumentator(app):
    """FastAPI uygulamasına Prometheus instrumentator bağla."""
    try:
        from prometheus_fastapi_instrumentator import Instrumentator

        instrumentator = Instrumentator(
            should_group_status_codes=True,
            should_ignore_untemplated=True,
            should_respect_env_var=False,
            excluded_handlers=["/docs", "/redoc", "/openapi.json"],
            env_var_name="ENABLE_METRICS",
        )
        instrumentator.instrument(app).expose(app, endpoint="/metrics")
        logger.info("Prometheus metrikleri aktif → /metrics")
    except Exception as e:
        logger.warning(f"Prometheus instrumentator yüklenemedi: {e}")
