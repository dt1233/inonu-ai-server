#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║  İNÖNÜ AI │ indexer.py                                           ║
║  Katman 2 → Vektör Veritabanı: bge-m3 GPU + Qdrant Hybrid       ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import uuid
from typing import Optional

import torch
from FlagEmbedding import BGEM3FlagModel
from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    HnswConfigDiff,
    MatchValue,
    PointStruct,
    SparseIndexParams,
    SparseVectorParams,
    VectorParams,
    VectorsConfig,
)

from .chunker import Chunk

COLLECTION_NAME  = os.getenv("QDRANT_COLLECTION", "inonu_docs")
QDRANT_HOST      = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT      = int(os.getenv("QDRANT_PORT", "6333"))
EMBEDDING_MODEL  = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")

DENSE_DIM    = 1024
BATCH_SIZE   = 32
MAX_LENGTH   = 8192


def _load_model() -> BGEM3FlagModel:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"bge-m3 yükleniyor [{device.upper()}, FP16]…")
    model = BGEM3FlagModel(
        EMBEDDING_MODEL,
        use_fp16=True,
        device=device,
    )
    logger.info("bge-m3 yüklendi ✓")
    return model


_MODEL: Optional[BGEM3FlagModel] = None


def get_model() -> BGEM3FlagModel:
    global _MODEL
    if _MODEL is None:
        _MODEL = _load_model()
    return _MODEL


def get_qdrant() -> QdrantClient:
    return QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


def ensure_collection(client: QdrantClient) -> None:
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME in existing:
        logger.info(f"Koleksiyon mevcut: {COLLECTION_NAME}")
        return

    logger.info(f"Koleksiyon oluşturuluyor: {COLLECTION_NAME}")
    client.create_collection(
        collection_name = COLLECTION_NAME,
        vectors_config  = {
            "dense": VectorParams(
                size     = DENSE_DIM,
                distance = Distance.COSINE,
            )
        },
        sparse_vectors_config={
            "sparse": SparseVectorParams(
                index=SparseIndexParams(on_disk=True),
            )
        },
    )
    logger.info(f"Koleksiyon hazır: {COLLECTION_NAME} ✓")


def encode_batch(texts: list[str]) -> dict:
    model = get_model()
    logger.debug(f"Encoding {len(texts)} metin…")

    outputs = model.encode(
        texts,
        batch_size          = BATCH_SIZE,
        max_length          = MAX_LENGTH,
        return_dense        = True,
        return_sparse       = True,
        return_colbert_vecs = False,
    )

    return {
        "dense":  outputs["dense_vecs"].tolist(),
        "sparse": outputs["lexical_weights"],
    }


def _sparse_to_qdrant(sparse_weights: dict) -> dict:
    indices = [int(k) for k in sparse_weights.keys()]
    values  = [float(v) for v in sparse_weights.values()]
    return {"indices": indices, "values": values}


class Indexer:

    def __init__(self):
        self.client = get_qdrant()
        ensure_collection(self.client)

    def index_chunks(self, chunks: list[Chunk], batch_size: int = 64) -> int:
        if not chunks:
            logger.info("Yazılacak chunk yok.")
            return 0

        total   = len(chunks)
        written = 0

        logger.info(f"Indexing başlıyor: {total} chunk")

        for batch_start in range(0, total, batch_size):
            batch_chunks = chunks[batch_start: batch_start + batch_size]
            batch_texts  = [c.text for c in batch_chunks]
            embeddings   = encode_batch(batch_texts)

            points: list[PointStruct] = []
            for i, chunk in enumerate(batch_chunks):
                uid = str(uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{chunk.source_key}:{chunk.doc_id}:{chunk.chunk_index}"
                ))
                points.append(PointStruct(
                    id     = uid,
                    vector = {
                        "dense":  embeddings["dense"][i],
                        "sparse": _sparse_to_qdrant(embeddings["sparse"][i]),
                    },
                    payload = {
                        "text":        chunk.text,
                        "source_url":  chunk.source_url,
                        "source_key":  chunk.source_key,
                        "doc_id":      str(chunk.doc_id),
                        "chunk_index": chunk.chunk_index,
                        "created_at":  chunk.created_at,
                        **chunk.metadata,
                    },
                ))

            self.client.upsert(
                collection_name = COLLECTION_NAME,
                points          = points,
                wait            = True,
            )
            written += len(points)
            logger.info(f"  {written}/{total} chunk yazıldı")

        logger.info(f"Indexing tamamlandı: {written} chunk → Qdrant:{COLLECTION_NAME}")
        return written

    def delete_by_source_key(self, source_key: str) -> int:
        result = self.client.delete(
            collection_name = COLLECTION_NAME,
            points_selector = Filter(
                must=[FieldCondition(
                    key   = "source_key",
                    match = MatchValue(value=source_key),
                )]
            ),
            wait=True,
        )
        count = result.result if hasattr(result, "result") else 0
        logger.info(f"Silindi: source_key={source_key} → {count} chunk")
        return count

    def collection_info(self) -> dict:
        info = self.client.get_collection(COLLECTION_NAME)
        return {
            "vectors_count": info.vectors_count,
            "points_count":  info.points_count,
            "status":        str(info.status),
            "collection":    COLLECTION_NAME,
        }