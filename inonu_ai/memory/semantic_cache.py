#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İnönü AI — Semantic Cache
Redis + bge-m3 vektör benzerlik önbelleği
Benzer sorularda LLM devreye girmez.
"""

import json
import time
import hashlib
import numpy as np
import redis
from typing import Optional

REDIS_HOST      = "localhost"
REDIS_PORT      = 6379
CACHE_PREFIX    = "scache:"
SIMILARITY_THR = 0.95  # 0.92'den 0.95'e yükseltildi (daha sıkı benzerlik)
TTL_DYNAMIC     = 1800      # 30 dakika (duyuru, yemek gibi)
TTL_STATIC      = 86400     # 24 saat (personel, yönetmelik gibi)

_redis: Optional[redis.Redis] = None

def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT,
                             decode_responses=True)
    return _redis


def _cosine(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


def _cache_key(question: str) -> str:
    h = hashlib.md5(question.strip().lower().encode()).hexdigest()
    return f"{CACHE_PREFIX}{h}"


def get_cached(question: str, question_vec: list[float],
               ttl: int = TTL_STATIC) -> Optional[str]:
    """
    Semantik olarak benzer bir soru cache'de varsa yanıtı döndür.
    Yoksa None döndür.
    """
    r = get_redis()
    # Tüm cache key'lerini tara (küçük ölçekte yeterli)
    keys = r.keys(f"{CACHE_PREFIX}*")
    best_sim, best_answer = 0.0, None

    for key in keys:
        raw = r.get(key)
        if raw is None:
            continue
        try:
            entry = json.loads(raw)
            sim = _cosine(question_vec, entry["vec"])
            if sim > best_sim:
                best_sim = sim
                best_answer = entry["answer"]
        except Exception:
            continue

    if best_sim >= SIMILARITY_THR and best_answer:
        return best_answer
    return None


def set_cache(question: str, question_vec: list[float],
              answer: str, ttl: int = TTL_STATIC) -> None:
    """Soru vektörünü ve yanıtı cache'e yaz."""
    r = get_redis()
    key = _cache_key(question)
    entry = {
        "question": question,
        "vec":      question_vec,
        "answer":   answer,
        "ts":       time.time(),
    }
    r.setex(key, ttl, json.dumps(entry))


def cache_stats() -> dict:
    """Cache istatistikleri."""
    r = get_redis()
    keys = r.keys(f"{CACHE_PREFIX}*")
    return {"total_entries": len(keys)}