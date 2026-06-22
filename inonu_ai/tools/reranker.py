#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İnönü AI — Re-Ranker
BAAI/bge-reranker-v2-m3 ile top-20 → top-3 seçimi
(Transformers native implementasyon - Tokenizer hatasını çözer)
"""

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from loguru import logger
from config import get_settings

_settings = get_settings()

MODEL_PATH = _settings.reranker_model_path
TOP_N      = 3

_tokenizer = None
_model = None

def get_reranker():
    global _tokenizer, _model
    if _model is None:
        logger.info("Re-ranker yükleniyor [CUDA, FP16, Native]...")
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
        _model = AutoModelForSequenceClassification.from_pretrained(
            MODEL_PATH, 
            torch_dtype=torch.float16
        ).cuda()
        _model.eval()
        logger.info("Re-ranker yüklendi ✓")
    return _tokenizer, _model


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

    tokenizer, model = get_reranker()
    texts  = [p.payload.get("text", "") for p in points]
    pairs  = [[query, t] for t in texts]

    try:
        with torch.no_grad():
            inputs = tokenizer(
                pairs, 
                padding=True, 
                truncation=True, 
                max_length=512, 
                return_tensors='pt'
            ).to('cuda')
            
            # bge-reranker outputs logits of shape (batch_size, 1)
            scores = model(**inputs, return_dict=True).logits.view(-1,).float()
            scores_list = scores.cpu().tolist()
            
    except Exception as e:
        logger.warning(f"Re-rank hatası: {e} — orijinal sıra korunuyor")
        return points[:top_n]

    scored = sorted(zip(scores_list, points), key=lambda x: x[0], reverse=True)
    top    = [p for _, p in scored[:top_n]]
    logger.debug(f"Re-rank: {len(points)} → {len(top)} chunk")
    return top