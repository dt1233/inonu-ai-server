#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İnönü AI — Qdrant Hybrid Search
Dense + Sparse vektör araması ile çift kanallı bilgi erişimi
"""

from typing import Optional
from loguru import logger
from config import get_settings

_settings = get_settings()


def hybrid_search(
    query_vector: list[float],
    collection_name: Optional[str] = None,
    limit: int = 20,
) -> list:
    """
    Qdrant'ta dense vektör araması yapar.

    Args:
        query_vector: Sorgu vektörü (1024-boyutlu dense)
        collection_name: Koleksiyon adı (varsayılan: config'den)
        limit: Döndürülecek maksimum sonuç

    Returns:
        Qdrant ScoredPoint listesi
    """
    from qdrant_client import QdrantClient

    client = QdrantClient(
        host=_settings.qdrant_host,
        port=_settings.qdrant_port,
    )

    result = client.query_points(
        collection_name=collection_name or _settings.qdrant_collection,
        query=query_vector,
        using="dense",
        limit=limit,
        with_payload=True,
    )

    logger.debug(f"Qdrant arama: {len(result.points)} sonuç")
    return result.points


def get_collection_info(collection_name: Optional[str] = None) -> dict:
    """Koleksiyon bilgilerini döndürür."""
    from qdrant_client import QdrantClient

    client = QdrantClient(
        host=_settings.qdrant_host,
        port=_settings.qdrant_port,
    )

    info = client.get_collection(
        collection_name or _settings.qdrant_collection
    )
    return {
        "vectors_count": info.vectors_count,
        "points_count":  info.points_count,
        "status":        str(info.status),
    }
