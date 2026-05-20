#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İnönü AI — GPU Embedding Servisi
bge-m3 ile dense + sparse vektör üretimi
"""

from typing import Optional

import torch
from FlagEmbedding import BGEM3FlagModel
from loguru import logger
from config import get_settings

_settings = get_settings()

BATCH_SIZE  = 32
MAX_LENGTH  = 8192
DENSE_DIM   = 1024

_model: Optional[BGEM3FlagModel] = None


def get_model() -> BGEM3FlagModel:
    """bge-m3 embedding modelini yükle (singleton)."""
    global _model
    if _model is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"bge-m3 yükleniyor [{device.upper()}, FP16]…")
        _model = BGEM3FlagModel(
            _settings.embedding_model,
            use_fp16=True,
            device=device,
        )
        logger.info("bge-m3 yüklendi ✓")
    return _model


def encode_batch(texts: list[str]) -> dict:
    """
    Metin listesini dense + sparse vektörlere dönüştür.

    Args:
        texts: Encode edilecek metin listesi

    Returns:
        {"dense": [[float, ...], ...], "sparse": [{int: float}, ...]}
    """
    model = get_model()
    logger.debug(f"Encoding {len(texts)} metin…")

    outputs = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        max_length=MAX_LENGTH,
        return_dense=True,
        return_sparse=True,
        return_colbert_vecs=False,
    )

    return {
        "dense":  outputs["dense_vecs"].tolist(),
        "sparse": outputs["lexical_weights"],
    }
