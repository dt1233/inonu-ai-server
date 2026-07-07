import sys
import os
from loguru import logger
from unittest.mock import patch, MagicMock

# Mock qdrant_client before importing indexer
mock_qdrant = MagicMock()
sys.modules['qdrant_client'] = mock_qdrant
sys.modules['qdrant_client.models'] = MagicMock()

from inonu_ai.data_pipeline.indexer import Indexer, ensure_collection
from inonu_ai.data_pipeline.chunker import Chunk

QdrantClient = mock_qdrant.QdrantClient

def main():
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    
    logger.info("SMOKE TEST: Indexer Başlıyor...")

    # Mock chunks
    mock_chunks = [
        Chunk(
            text="Bu bir duyurudur.",
            source_url="http://example.com/1",
            source_key="announcement:muhendislik",
            doc_id="1",
            chunk_index=0,
            metadata={
                "unit": "muhendislik",
                "doc_type": "announcement",
                "content_hash": "hash_123"
            }
        ),
        Chunk(
            text="Bu bir pdf sayfasıdır.",
            source_url="http://example.com/2",
            source_key="pdf_page:muhendislik:1:1",
            doc_id="2",
            chunk_index=0,
            metadata={
                "unit": "muhendislik",
                "doc_type": "pdf_page",
                "content_hash": "hash_456"
            }
        ),
        Chunk(
            text="Bu aynı pdf sayfası ama farklı chunklanmış (Duplicate Hash Test).",
            source_url="http://example.com/2",
            source_key="pdf_page:muhendislik:1:1",
            doc_id="2_dup",
            chunk_index=1,
            metadata={
                "unit": "muhendislik",
                "doc_type": "pdf_page",
                "content_hash": "hash_456" # DUPLICATE
            }
        ),
        Chunk(
            text="Bu chunk'ta content hash hesaplanmamış.",
            source_url="http://example.com/3",
            source_key="announcement:tip",
            doc_id="3",
            chunk_index=0,
            metadata={
                "unit": "tip",
                "doc_type": "announcement",
                "content_hash": "" # EMPTY HASH
            }
        ),
    ]

    print("\n--- TEST: ensure_collection & Payload Indexes ---")
    
    # 1. Collection Yok (Missing Collection) Senaryosu
    print("\nSenaryo 1: Collection yok.")
    client_missing = MagicMock()
    mock_existing_colls_missing = MagicMock()
    mock_existing_colls_missing.collections = [] # collection yok
    client_missing.get_collections.return_value = mock_existing_colls_missing
    
    ensure_collection(client_missing, reset=False)
    
    print(f"create_collection çağrıldı mı?: {client_missing.create_collection.called}")
    calls_missing = client_missing.create_payload_index.call_args_list
    indexes_created_missing = [call.kwargs.get("field_name") for call in calls_missing]
    print(f"Payload Indexler kuruldu mu?: {len(indexes_created_missing) > 0} ({indexes_created_missing})")

    # 2. Collection Var (Existing Collection) Senaryosu
    print("\nSenaryo 2: Collection zaten var.")
    client_existing = MagicMock()
    mock_coll = MagicMock()
    mock_coll.name = "inonu_docs"
    mock_existing_colls_existing = MagicMock()
    mock_existing_colls_existing.collections = [mock_coll] # collection var
    client_existing.get_collections.return_value = mock_existing_colls_existing
    
    ensure_collection(client_existing, reset=False)
    
    print(f"create_collection çağrıldı mı?: {client_existing.create_collection.called}")
    calls_existing = client_existing.create_payload_index.call_args_list
    indexes_created_existing = [call.kwargs.get("field_name") for call in calls_existing]
    print(f"Payload Indexler yine de kuruldu mu?: {len(indexes_created_existing) > 0} ({indexes_created_existing})")


    # Test Duplicate Filter in index_chunks
    print("\n--- TEST: index_chunks (Duplicate & Empty Hash Control) ---")
    
    with patch("inonu_ai.data_pipeline.indexer.encode_batch") as mock_encode:
        # Mock embeddings for up to 4 texts
        mock_encode.return_value = {
            "dense": [[0.1]*1024 for _ in range(4)],
            "sparse": [{"1": 0.5} for _ in range(4)]
        }
        
        with patch("inonu_ai.data_pipeline.indexer.get_qdrant", return_value=client_missing):
            indexer = Indexer(reset=False)
            
            written_count = indexer.index_chunks(mock_chunks, batch_size=64)
            
            print(f"Girdi Chunk Sayısı: {len(mock_chunks)}")
            print(f"Yazılan (Filtreleme Sonrası) Chunk Sayısı: {written_count}")
            
            if written_count == 3:
                print("-> BAŞARILI: 4 inputtan 1 duplicate elendi ve tam 3 tane yazıldı.")
            else:
                print("-> HATA: Beklenen yazım sayısı 3 idi!")


if __name__ == '__main__':
    main()
