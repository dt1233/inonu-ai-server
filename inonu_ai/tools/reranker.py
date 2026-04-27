#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İnönü AI — Re-Ranker
BAAI/bge-reranker-v2-m3 ile top-20 → top-3 seçimi
"""

from FlagEmbedding import FlagReranker
from loguru import logger

MODEL_PATH = "/home/yapayzeka/models/bge-reranker-v2-m3"
TOP_N      = 3

_reranker = None

def get_reranker() -> FlagReranker:
    global _reranker
    if _reranker is None:
        logger.info("Re-ranker yükleniyor [CUDA, FP16]...")
        _reranker = FlagReranker(MODEL_PATH, use_fp16=True, device="cuda")
        logger.info("Re-ranker yüklendi ✓")
    return _reranker


def rerank(query: str, points: list, top_n: int = TOP_N) -> list:
    """
    Qdrant'tan gelen chunk listesini re-rank et.
    points: Qdrant ScoredPoint listesi
    Döndürür: En alakalı top_n chunk
    """
    if not points:
        return []
    if len(points) <= top_n:
        return points

    reranker = get_reranker()
    texts  = [p.payload.get("text", "") for p in points]
    pairs  = [[query, t] for t in texts]

    try:
        scores = reranker.compute_score(pairs, normalize=True)
    except Exception as e:
        logger.warning(f"Re-rank hatası: {e} — orijinal sıra korunuyor")
        return points[:top_n]

    scored = sorted(zip(scores, points), key=lambda x: x[0], reverse=True)
    top    = [p for _, p in scored[:top_n]]
    logger.debug(f"Re-rank: {len(points)} → {len(top)} chunk")
    return top