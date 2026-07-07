#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vector database indexer for Inonu AI RAG chunks."""

from __future__ import annotations

import os
import traceback
import uuid
from typing import Any

from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    SparseIndexParams,
    SparseVectorParams,
    VectorParams,
)

from inonu_ai.engine.embedding import encode_batch

COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "inonu_docs")
QDRANT_PATH = os.getenv("QDRANT_PATH", "qdrant_storage")
DENSE_DIM = int(os.getenv("DENSE_DIM", "1024"))


def get_qdrant() -> QdrantClient:
    db_path = os.path.join(os.getcwd(), QDRANT_PATH)
    os.makedirs(db_path, exist_ok=True)
    return QdrantClient(path=db_path)


def _ensure_payload_indexes(client: QdrantClient) -> None:
    payload_fields = [
        "unit",
        "fakulte",
        "source_fakulte",
        "detected_fakulte",
        "scope",
        "kategori",
        "doc_type",
        "ann_id",
        "content_hash",
        "source_key",
        "doc_id",
    ]
    for field in payload_fields:
        try:
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )
        except Exception as exc:
            logger.debug(f"Payload index already exists or cannot be created ({field}): {exc}")


def ensure_collection(client: QdrantClient, reset: bool = False) -> None:
    existing = [c.name for c in client.get_collections().collections]

    if reset and COLLECTION_NAME in existing:
        logger.warning(f"Reset requested; deleting collection: {COLLECTION_NAME}")
        client.delete_collection(COLLECTION_NAME)
        existing.remove(COLLECTION_NAME)

    if COLLECTION_NAME in existing:
        logger.info(f"Collection exists: {COLLECTION_NAME}")
    else:
        logger.info(f"Creating collection: {COLLECTION_NAME}")
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config={
                "dense": VectorParams(size=DENSE_DIM, distance=Distance.COSINE),
            },
            sparse_vectors_config={
                "sparse": SparseVectorParams(index=SparseIndexParams(on_disk=True)),
            },
        )
        logger.info(f"Collection ready: {COLLECTION_NAME}")

    _ensure_payload_indexes(client)


def _chunk_uid(chunk: Any) -> str:
    return f"{chunk.source_key}:{chunk.doc_id}:{chunk.chunk_index}"


def _chunk_debug(chunk: Any) -> dict:
    metadata = chunk.metadata or {}
    return {
        "source_key": chunk.source_key,
        "doc_id": str(chunk.doc_id),
        "chunk_index": chunk.chunk_index,
        "doc_type": metadata.get("doc_type"),
        "title": metadata.get("title"),
        "source_url": chunk.source_url,
        "pdf_url": metadata.get("pdf_url"),
        "page_no": metadata.get("page_no"),
    }


def _sparse_to_qdrant(sparse_weights: dict) -> dict:
    return {
        "indices": [int(k) for k in sparse_weights.keys()],
        "values": [float(v) for v in sparse_weights.values()],
    }


class Indexer:
    def __init__(self, reset: bool = False):
        self.client = get_qdrant()
        ensure_collection(self.client, reset=reset)

    def _dedupe_chunks(self, chunks: list[Any]) -> list[Any]:
        unique_chunks: list[Any] = []
        seen_uids: set[str] = set()
        duplicate_count = 0

        for chunk in chunks:
            uid = _chunk_uid(chunk)
            if uid in seen_uids:
                duplicate_count += 1
                continue
            seen_uids.add(uid)
            unique_chunks.append(chunk)

        if duplicate_count:
            logger.info(f"Filtered duplicate chunks by UID: {duplicate_count}")
        return unique_chunks

    def index_chunks(self, chunks: list[Any], batch_size: int = 64) -> int:
        if not chunks:
            logger.info("No chunks to index.")
            return 0

        chunks_to_index = self._dedupe_chunks(chunks)
        total = len(chunks_to_index)
        if total == 0:
            logger.warning("No chunks left after deduplication.")
            return 0

        written = 0
        logger.info(f"Indexing starts: {total} chunks | batch_size={batch_size}")

        for batch_start in range(0, total, batch_size):
            batch_chunks = chunks_to_index[batch_start: batch_start + batch_size]
            batch_end = batch_start + len(batch_chunks)
            batch_texts = [c.text for c in batch_chunks]

            try:
                embeddings = encode_batch(batch_texts)
            except Exception as exc:
                logger.error(
                    "Embedding failed: batch=%s-%s first_chunk=%s error=%s",
                    batch_start,
                    batch_end - 1,
                    _chunk_debug(batch_chunks[0]),
                    exc,
                )
                logger.error(traceback.format_exc())
                raise

            dense_vectors = embeddings.get("dense", [])
            sparse_vectors = embeddings.get("sparse", [])
            if len(dense_vectors) != len(batch_chunks) or len(sparse_vectors) != len(batch_chunks):
                logger.error(
                    "Embedding count mismatch: batch=%s-%s chunks=%s dense=%s sparse=%s",
                    batch_start,
                    batch_end - 1,
                    len(batch_chunks),
                    len(dense_vectors),
                    len(sparse_vectors),
                )
                raise RuntimeError("Embedding count mismatch")

            points: list[PointStruct] = []
            for i, chunk in enumerate(batch_chunks):
                dense = dense_vectors[i]
                if len(dense) != DENSE_DIM:
                    logger.error(
                        "Dense vector dimension mismatch: expected=%s actual=%s chunk=%s",
                        DENSE_DIM,
                        len(dense),
                        _chunk_debug(chunk),
                    )
                    raise RuntimeError("Dense vector dimension mismatch")

                point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, _chunk_uid(chunk)))
                points.append(
                    PointStruct(
                        id=point_id,
                        vector={
                            "dense": dense,
                            "sparse": _sparse_to_qdrant(sparse_vectors[i]),
                        },
                        payload={
                            "text": chunk.text,
                            "source_url": chunk.source_url,
                            "source_key": chunk.source_key,
                            "doc_id": str(chunk.doc_id),
                            "chunk_index": chunk.chunk_index,
                            "created_at": chunk.created_at,
                            **(chunk.metadata or {}),
                        },
                    )
                )

            try:
                self.client.upsert(
                    collection_name=COLLECTION_NAME,
                    points=points,
                    wait=True,
                )
            except Exception as exc:
                logger.error(
                    "Qdrant upsert failed: batch=%s-%s point_count=%s first_chunk=%s error=%s",
                    batch_start,
                    batch_end - 1,
                    len(points),
                    _chunk_debug(batch_chunks[0]),
                    exc,
                )
                logger.error(traceback.format_exc())
                raise

            written += len(points)
            logger.info(f"Indexed batch: {written}/{total} chunks")

        point_count = self.get_point_count()
        logger.info(f"Indexing finished: written={written}, qdrant_point_count={point_count}")
        if point_count != written:
            raise RuntimeError(f"Qdrant point_count mismatch: written={written}, point_count={point_count}")
        return written

    def get_point_count(self) -> int:
        info = self.client.get_collection(COLLECTION_NAME)
        return int(info.points_count or 0)

    def delete_by_source_key(self, source_key: str) -> int:
        result = self.client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="source_key",
                        match=MatchValue(value=source_key),
                    )
                ]
            ),
            wait=True,
        )
        count = result.result if hasattr(result, "result") else 0
        logger.info(f"Deleted source_key={source_key}: {count} chunks")
        return count

    def collection_info(self) -> dict:
        info = self.client.get_collection(COLLECTION_NAME)
        return {
            "vectors_count": info.vectors_count,
            "points_count": info.points_count,
            "indexed_vectors_count": getattr(info, "indexed_vectors_count", None),
            "status": str(info.status),
            "collection": COLLECTION_NAME,
        }
