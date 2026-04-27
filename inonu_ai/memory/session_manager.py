#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İnönü AI — Session Manager
Redis TTL tabanlı oturum geçmişi yönetimi
"""

import json
import uuid
import redis
from typing import Optional

REDIS_HOST    = "localhost"
REDIS_PORT    = 6379
SESSION_TTL   = 7200        # 2 saat (saniye)
MAX_HISTORY   = 10          # Oturum başına max soru-cevap çifti

_redis: Optional[redis.Redis] = None

def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT,
                             decode_responses=True)
    return _redis


def new_session() -> str:
    """Yeni oturum ID'si üret ve Redis'e boş geçmiş kaydı aç."""
    session_id = str(uuid.uuid4())
    r = get_redis()
    r.setex(f"session:{session_id}", SESSION_TTL, json.dumps([]))
    return session_id


def get_history(session_id: str) -> list[dict]:
    """Oturum geçmişini Redis'ten çek."""
    r = get_redis()
    raw = r.get(f"session:{session_id}")
    if raw is None:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []


def add_turn(session_id: str, question: str, answer: str) -> None:
    """Soru-cevap çiftini oturum geçmişine ekle."""
    r = get_redis()
    history = get_history(session_id)
    history.append({"role": "user",      "content": question})
    history.append({"role": "assistant", "content": answer})

    # Max geçmiş sınırı (son MAX_HISTORY*2 mesaj)
    if len(history) > MAX_HISTORY * 2:
        history = history[-(MAX_HISTORY * 2):]

    r.setex(f"session:{session_id}", SESSION_TTL, json.dumps(history))


def build_history_prompt(session_id: str) -> list[dict]:
    """LLM'e gönderilecek geçmiş mesaj listesini döndür."""
    return get_history(session_id)


def delete_session(session_id: str) -> None:
    """Oturumu manuel olarak sil."""
    get_redis().delete(f"session:{session_id}")