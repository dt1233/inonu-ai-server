#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smoke Test: Retriever Strict/Fallback Filtreleme Mantığı
Gerçek Qdrant/embedding gerektirmez.
"""
import sys
import json
from unittest.mock import MagicMock

# Mock heavy deps before import
import os
# Add inonu_ai package root to path so bare imports (engine.*, data_pipeline.*, tools.*) resolve
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "inonu_ai"))

sys.modules['qdrant_client'] = MagicMock()
sys.modules['qdrant_client.models'] = MagicMock()
sys.modules['engine.embedding'] = MagicMock()
sys.modules['tools.reranker'] = MagicMock()

from engine.retriever import (
    filter_by_fakulte,
    _is_chunk_safe_for_query,
    _get_effective_fakulte,
    _point_to_doc,
)


def mock_point(payload: dict, score: float = 0.8):
    """Qdrant ScoredPoint benzeri mock obje."""
    p = MagicMock()
    p.payload = payload
    p.score = score
    return p


def main():
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 60)
    print("RETRIEVER STRICT/FALLBACK SMOKE TEST")
    print("=" * 60)

    requested = ["Mühendislik Fakültesi"]

    # ── Mock Chunk'lar ──
    chunk_a = mock_point({
        "text": "Mühendislik sınav takvimi...",
        "source_url": "http://example.com/muh/1",
        "unit": "muhendislik",
        "unit_label": "Mühendislik Fakültesi",
        "fakulte": "Mühendislik Fakültesi",
        "source_fakulte": "Mühendislik Fakültesi",
        "detected_fakulte": "Mühendislik Fakültesi",
        "scope": "faculty",
        "doc_type": "announcement",
        "title": "Sınav Takvimi",
        "content_hash": "aaa",
    })

    chunk_b = mock_point({
        "text": "Diş Hekimliği Ortodonti tarihleri...",
        "source_url": "http://example.com/muh/1/ek.pdf",
        "unit": "muhendislik",
        "unit_label": "Mühendislik Fakültesi",
        "fakulte": "Mühendislik Fakültesi",
        "source_fakulte": "Mühendislik Fakültesi",
        "detected_fakulte": "Diş Hekimliği Fakültesi",  # MISMATCH!
        "scope": "faculty",
        "doc_type": "pdf_page",
        "page_no": 2,
        "title": "Sınav Takvimi",
        "content_hash": "bbb",
    })

    chunk_c = mock_point({
        "text": "Üniversite genel akademik takvim...",
        "source_url": "http://example.com/genel/takvim",
        "unit": "ogrencidb",
        "unit_label": "Öğrenci İşleri",
        "fakulte": "",
        "source_fakulte": "",
        "detected_fakulte": "",
        "scope": "university",
        "doc_type": "static",
        "title": "Akademik Takvim",
        "content_hash": "ccc",
    })

    chunk_d = mock_point({
        "text": "Hukuk Fakültesi büt takvimi...",
        "source_url": "http://example.com/genel/takvim2",
        "unit": "ogrencidb",
        "unit_label": "Öğrenci İşleri",
        "fakulte": "",
        "source_fakulte": "",
        "detected_fakulte": "Hukuk Fakültesi",  # University ama rakip tespit!
        "scope": "university",
        "doc_type": "static",
        "title": "Akademik Takvim 2",
        "content_hash": "ddd",
    })

    chunk_e = mock_point({
        "text": "Mühendislik genel bilgi...",
        "source_url": "http://example.com/muh/about",
        "unit": "muhendislik",
        "unit_label": "Mühendislik Fakültesi",
        "fakulte": "Mühendislik Fakültesi",
        "source_fakulte": "Mühendislik Fakültesi",
        "detected_fakulte": "",  # Tespit yapılamadı ama source Mühendislik
        "scope": "faculty",
        "doc_type": "static",
        "title": "Hakkımızda",
        "content_hash": "eee",
    })

    all_points = [chunk_a, chunk_b, chunk_c, chunk_d, chunk_e]

    # ── TEST 1: Bireysel _is_chunk_safe_for_query ──
    print("\n--- TEST 1: _is_chunk_safe_for_query ---")
    tests = [
        ("A (Müh, detected=Müh)", chunk_a.payload, True),
        ("B (Müh source, detected=Diş)", chunk_b.payload, False),
        ("C (university, detected boş)", chunk_c.payload, True),
        ("D (university, detected=Hukuk)", chunk_d.payload, False),
        ("E (Müh, detected boş)", chunk_e.payload, True),
    ]
    all_pass = True
    for label, payload, expected in tests:
        result = _is_chunk_safe_for_query(payload, requested)
        status = "✅" if result == expected else "❌"
        if result != expected:
            all_pass = False
        print(f"  {status} Chunk {label}: safe={result} (beklenen={expected})")

    # ── TEST 2: filter_by_fakulte ──
    print("\n--- TEST 2: filter_by_fakulte ---")
    result = filter_by_fakulte(all_points, requested)

    print(f"  Input Aday Sayısı: {len(all_points)}")
    print(f"  Strict Geçen Sayı: {len(result['strict'])}")
    print(f"  Owner Mismatch Elenen: {result['owner_mismatch']}")
    print(f"  Fallback Tetiklendi mi: {result['fallback_used']}")
    print(f"  Debug: {json.dumps(result['debug'], ensure_ascii=False, indent=4)}")

    # Beklenti: A, C, E geçmeli. B ve D elenmeli.
    passed_urls = [p.payload["source_url"] for p in result["strict"]]
    expected_urls = [
        "http://example.com/muh/1",
        "http://example.com/genel/takvim",
        "http://example.com/muh/about",
    ]
    urls_match = set(passed_urls) == set(expected_urls)
    print(f"  Geçen URL'ler doğru mu: {'✅' if urls_match else '❌'}")
    if not urls_match:
        print(f"    Beklenen: {expected_urls}")
        print(f"    Gelen:    {passed_urls}")
        all_pass = False

    # ── TEST 3: _point_to_doc metadata formatı ──
    print("\n--- TEST 3: _point_to_doc metadata formatı ---")
    doc = _point_to_doc(chunk_b)
    required_fields = [
        "unit", "unit_label", "fakulte", "source_fakulte", "detected_fakulte",
        "scope", "doc_type", "page_no", "ann_id", "title", "source_url",
        "pdf_url", "content_hash"
    ]
    missing = [f for f in required_fields if f not in doc["metadata"]]
    print(f"  Eksik metadata alan: {missing if missing else 'YOK ✅'}")
    print(f"  detected_fakulte korunuyor mu: {doc['metadata']['detected_fakulte']}")
    if missing:
        all_pass = False

    # ── TEST 4: Fallback senaryosu ──
    print("\n--- TEST 4: Fallback Senaryosu ---")
    # Sadece B ve D var (ikisi de elenir) → strict < 2 → fallback tetiklenmeli
    fallback_result = filter_by_fakulte([chunk_b, chunk_d, chunk_c], requested)
    print(f"  Fallback tetiklendi mi: {fallback_result['fallback_used']}")
    print(f"  Fallback sonrası sonuç: {len(fallback_result['strict'])}")
    # C university ve detected boş → fallback'te eklenmeli
    fallback_correct = fallback_result['fallback_used'] and len(fallback_result['strict']) >= 1
    print(f"  Fallback doğru çalıştı mı: {'✅' if fallback_correct else '❌'}")
    if not fallback_correct:
        all_pass = False

    # ── TEST 5: Düşük skorlu chunk artık elenmiyor ──
    print("\n--- TEST 5: Düşük Skor Chunk Hayatta Kalma ---")
    low_score_chunk = mock_point({
        "text": "Mühendislik büt tarihleri...",
        "source_url": "http://example.com/muh/but",
        "unit": "muhendislik",
        "fakulte": "Mühendislik Fakültesi",
        "detected_fakulte": "Mühendislik Fakültesi",
        "scope": "faculty",
        "doc_type": "announcement",
        "title": "Büt Tarihleri",
        "content_hash": "fff",
    }, score=0.01)  # Çok düşük RRF score

    doc_low = _point_to_doc(low_score_chunk)
    survived = doc_low["score"] == 0.01  # Filtresiz geçmeli
    print(f"  score=0.01 chunk hayatta mı: {'✅' if survived else '❌'} (score={doc_low['score']})")
    if not survived:
        all_pass = False

    # ── TEST 6: Skor kaynağı (provenance) metadata ──
    print("\n--- TEST 6: Skor Kaynağı Metadata ---")
    # rerank_score=None (henüz reranker çalışmadı)
    doc_no_rerank = _point_to_doc(low_score_chunk)
    has_retrieval = "retrieval_score" in doc_no_rerank["metadata"]
    has_rerank = "rerank_score" in doc_no_rerank["metadata"]
    retrieval_val = doc_no_rerank["metadata"].get("retrieval_score")
    rerank_val = doc_no_rerank["metadata"].get("rerank_score")
    print(f"  retrieval_score alanı var mı: {'✅' if has_retrieval else '❌'} (değer={retrieval_val})")
    print(f"  rerank_score alanı var mı:    {'✅' if has_rerank else '❌'} (değer={rerank_val})")
    print(f"  rerank_score=None (henüz yok): {'✅' if rerank_val is None else '❌'}")
    if not (has_retrieval and has_rerank and rerank_val is None):
        all_pass = False

    # rerank_score verildiğinde ana skor onu kullanmalı
    doc_with_rerank = _point_to_doc(low_score_chunk, rerank_score=7.5)
    effective_correct = doc_with_rerank["score"] == 7.5
    rerank_stored = doc_with_rerank["metadata"]["rerank_score"] == 7.5
    retrieval_kept = doc_with_rerank["metadata"]["retrieval_score"] == 0.01
    print(f"  rerank_score=7.5 verildi → ana score=7.5 mi: {'✅' if effective_correct else '❌'}")
    print(f"  metadata.rerank_score=7.5 mi: {'✅' if rerank_stored else '❌'}")
    print(f"  metadata.retrieval_score hâlâ 0.01 mi: {'✅' if retrieval_kept else '❌'}")
    if not (effective_correct and rerank_stored and retrieval_kept):
        all_pass = False

    # ── SONUÇ ──
    print("\n" + "=" * 60)
    print(f"GENEL SONUÇ: {'✅ TÜM TESTLER GEÇTİ' if all_pass else '❌ BAZI TESTLER BAŞARISIZ'}")
    print("=" * 60)


    if not all_pass:
        import sys
        sys.exit(1)

if __name__ == "__main__":
    main()
