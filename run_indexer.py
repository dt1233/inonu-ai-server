#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI entrypoint for building the local Qdrant index."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

sys.path.append(str(Path(__file__).parent))

from inonu_ai.data_pipeline.indexer import Indexer
from inonu_ai.data_pipeline.io_utils import load_json


@dataclass
class IndexChunk:
    """Lightweight chunk contract for indexing prebuilt JSON chunks."""

    text: str
    source_url: str = ""
    source_key: str = ""
    doc_id: str = ""
    chunk_index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""


def _to_index_chunk(item: dict[str, Any]) -> IndexChunk:
    metadata = item.get("metadata") or {}
    return IndexChunk(
        text=item.get("text") or "",
        source_url=item.get("source_url") or "",
        source_key=item.get("source_key") or "",
        doc_id=str(item.get("doc_id") or ""),
        chunk_index=int(item.get("chunk_index") or 0),
        metadata=metadata if isinstance(metadata, dict) else {},
        created_at=item.get("created_at") or "",
    )


def _configure_logging(log_file: str | None) -> None:
    if not log_file:
        return
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_file,
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=True,
        rotation="50 MB",
    )
    logger.info(f"Indexer log file enabled: {log_file}")


def _load_chunks(path: Path, limit: int | None) -> list[IndexChunk]:
    logger.info(f"Reading chunk file: {path}")
    chunks_data = load_json(str(path), default=[])
    if not chunks_data:
        raise RuntimeError(f"Chunk file is empty or unreadable: {path}")

    if limit is not None:
        logger.warning(f"Local rehearsal limit enabled: first {limit} chunks will be indexed.")
        chunks_data = chunks_data[:limit]

    chunks = [_to_index_chunk(item) for item in chunks_data]
    logger.info(f"Loaded chunks into memory: {len(chunks)}")
    return chunks


def main() -> int:
    parser = argparse.ArgumentParser(description="Inonu AI Qdrant index builder")
    parser.add_argument("--reset", action="store_true", help="Delete and recreate the Qdrant collection.")
    parser.add_argument("--file", type=str, default="data/chunks_output.json", help="Chunk JSON file.")
    parser.add_argument("--limit", type=int, default=None, help="Index only the first N chunks for local rehearsal.")
    parser.add_argument("--batch-size", type=int, default=64, help="Embedding/upsert batch size.")
    parser.add_argument("--log-file", type=str, default=None, help="Write detailed indexer logs to this file.")
    args = parser.parse_args()

    _configure_logging(args.log_file)

    try:
        chunk_file = Path(args.file)
        if not chunk_file.exists():
            raise FileNotFoundError(f"Chunk file not found: {chunk_file}")

        chunks = _load_chunks(chunk_file, args.limit)

        logger.info("Connecting to Qdrant...")
        indexer = Indexer(reset=args.reset)

        logger.info("Starting embedding and Qdrant upsert...")
        written = indexer.index_chunks(chunks, batch_size=args.batch_size)
        point_count = indexer.get_point_count()

        logger.info("=" * 60)
        logger.info(f"INDEX COMPLETE: written={written}, qdrant_point_count={point_count}")
        logger.info("=" * 60)

        if written <= 0:
            raise RuntimeError("No vectors were written.")
        if point_count != written:
            raise RuntimeError(f"Final point_count mismatch: written={written}, point_count={point_count}")
        return 0
    except Exception as exc:
        logger.exception(f"INDEX FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
