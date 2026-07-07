#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İnönü AI — GPU Embedding Servisi
bge-m3 ile dense + sparse vektör üretimi
"""

import os



from typing import Optional

from fastembed import TextEmbedding, SparseTextEmbedding
from loguru import logger
from inonu_ai.config import get_settings

_settings = get_settings()

BATCH_SIZE  = 32
MAX_LENGTH  = 8192
DENSE_DIM   = 1024

_dense_model: Optional[TextEmbedding] = None
_sparse_model: Optional[SparseTextEmbedding] = None


def get_model() -> tuple[TextEmbedding, SparseTextEmbedding]:
    """bge-m3 ve bm25 embedding modellerini yükle (singleton)."""
    global _dense_model, _sparse_model
    if _dense_model is None or _sparse_model is None:
        logger.info("Modeller yükleniyor (fastembed)...")
        _dense_model = TextEmbedding(model_name="intfloat/multilingual-e5-large")
        _sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")
        logger.info("Modeller yüklendi ✓")
    return _dense_model, _sparse_model


def encode_batch(texts: list[str]) -> dict:
    """
    Metin listesini dense + sparse vektörlere dönüştür.

    Args:
        texts: Encode edilecek metin listesi

    Returns:
        {"dense": [[float, ...], ...], "sparse": [{int: float}, ...]}
    """
    dense_m, sparse_m = get_model()
    logger.debug(f"Encoding {len(texts)} metin…")

    # generator döndürüyor, list'e çeviriyoruz
    dense_vecs = list(dense_m.embed(texts, batch_size=BATCH_SIZE))
    sparse_vecs = list(sparse_m.embed(texts, batch_size=BATCH_SIZE))

    formatted_sparse = []
    for sp in sparse_vecs:
        # sp is SparseEmbedding(indices=[...], values=[...])
        indices = sp.indices.tolist() if hasattr(sp.indices, 'tolist') else list(sp.indices)
        values = sp.values.tolist() if hasattr(sp.values, 'tolist') else list(sp.values)
        d = {str(k): float(v) for k, v in zip(indices, values)}
        formatted_sparse.append(d)

    return {
        "dense": [vec.tolist() if hasattr(vec, 'tolist') else list(vec) for vec in dense_vecs],
        "sparse": formatted_sparse
    }
