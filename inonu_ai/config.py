#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İnönü AI — Merkezi Konfigürasyon
Tüm ortam değişkenlerini tek noktadan yönetir.
"""

import os
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings
from pydantic import Field


# Proje kök dizini
BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    """Tüm uygulama ayarları. .env dosyasından otomatik okunur."""

    # ── JWT ─────────────────────────────────────────────────
    jwt_secret_key: str = Field(
        default="default-secret-key-degistirin",
        description="JWT token imzalama anahtarı"
    )
    jwt_algorithm: str = Field(default="HS256")
    jwt_access_token_expire_minutes: int = Field(default=60)

    # ── Admin ───────────────────────────────────────────────
    admin_username: str = Field(default="admin")
    admin_password: str = Field(default="inonu_ai_2025")

    # ── SGLang / LLM ───────────────────────────────────────
    sglang_base_url: str = Field(default="http://localhost:30000/v1")
    sglang_model: str = Field(default="/home/yapayzeka/models/Qwen3-8B")

    # ── Qdrant ──────────────────────────────────────────────
    qdrant_host: str = Field(default="localhost")
    qdrant_port: int = Field(default=6333)
    qdrant_collection: str = Field(default="inonu_docs")

    # ── Redis ───────────────────────────────────────────────
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)

    # ── Model Yolları ───────────────────────────────────────
    reranker_model_path: str = Field(
        default="/home/yapayzeka/models/bge-reranker-v2-m3"
    )
    embedding_model: str = Field(default="BAAI/bge-m3")

    # ── Uygulama ────────────────────────────────────────────
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)
    log_level: str = Field(default="INFO")

    model_config = {
        "env_file": str(BASE_DIR / ".env"),
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    """Singleton Settings nesnesi döndürür."""
    return Settings()
