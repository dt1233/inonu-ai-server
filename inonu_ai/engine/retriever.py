#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İNÖNÜ AI │ engine/retriever.py
Merkezi Retriever — Strict/Fallback Fakülte Filtreleme

Tüm arama hattı buradan geçer.
CLI (eski) ve API (nodes.py Adım 7) aynı fonksiyonu kullanır.
"""

import os
import re
from datetime import datetime
from loguru import logger

from data_pipeline.faculty_detector import extract_requested_faculties

# ── Zaman duyarlı sorgu zenginleştirme ──────────────────────
_TIME_KEYWORDS = [
    'sınav', 'büt', 'final', 'vize', 'kayıt', 'mezun', 'takvim',
    'dönem', 'yaz okulu', 'staj', 'başvuru', 'tarih', 'ne zaman',
    'açılacak', 'kapanacak', 'son gün', 'süre', 'başla', 'bitir',
    'bütünleme', 'ders seçim', 'not giriş', 'mazeret',
]

# ── Retrieval Parametreleri ──────────────────────────────────
STRICT_MIN_RESULTS = 2


def _get_current_academic_year() -> str:
    """Güncel akademik yılı döndür (Eylül→Ağustos döngüsü)."""
    now = datetime.now()
    if now.month >= 9:
        return f"{now.year}-{now.year + 1}"
    return f"{now.year - 1}-{now.year}"


def _augment_query(query: str) -> str:
    """
    Zaman duyarlı sorulara otomatik olarak güncel akademik yılı ekler.
    Soruda zaten bir yıl varsa dokunmaz.
    """
    q = query.lower()
    if re.search(r'20\d{2}', query):
        return query
    if any(kw in q for kw in _TIME_KEYWORDS):
        year = _get_current_academic_year()
        augmented = f"{query} {year} eğitim öğretim yılı güncel"
        logger.info(f"Sorgu zenginleştirildi: '{query}' → '{augmented}'")
        return augmented
    return query


# ── Fakülte Filtreleme (Strict / Fallback) ───────────────────

def _get_effective_fakulte(payload: dict) -> str | None:
    """
    Bir chunk'ın *gerçek* fakülte sahipliğini belirler.
    Öncelik sırası:
      1. detected_fakulte (PDF sayfa bazlı tespit — en güvenilir)
      2. fakulte veya source_fakulte (crawler metadata)
    """
    detected = (payload.get("detected_fakulte") or "").strip()
    if detected:
        return detected
    return (payload.get("fakulte") or payload.get("source_fakulte") or "").strip() or None


def _is_chunk_safe_for_query(payload: dict, requested_fakulteler: list[str]) -> bool:
    """
    Bir chunk'ın, requested_fakulte listesine güvenle döndürülüp
    döndürülemeyeceğini belirler.

    Kurallar:
    1. scope="university" ve detected_fakulte boş → Genel kaynak, GEÇ.
    2. scope="university" ama detected_fakulte dolu ve rakip → ELEN.
    3. Chunk'ın efektif fakültesi requested listede → GEÇ.
    4. Chunk'ın efektif fakültesi requested listede DEĞİL → ELEN.
    """
    scope = (payload.get("scope") or "").strip()
    effective = _get_effective_fakulte(payload)

    # Genel üniversite kaynağı
    if scope == "university":
        if not effective:
            return True  # Genel kaynak, fakülte tespiti yapılamamış → güvenli
        # University ama sayfada rakip fakülte tespit edilmiş
        return effective in requested_fakulteler

    # Fakülte/birim bazlı kaynak
    if not effective:
        return True  # Fakülte tespiti yapılamadı → eleme yapma, geçir

    return effective in requested_fakulteler


def filter_by_fakulte(
    points: list,
    requested_fakulteler: list[str],
) -> dict:
    """
    Qdrant point listesini fakülte sahiplik kurallarına göre filtreler.

    Döndürdüğü dict:
    {
        "strict": [...],       # Kesin uyumlu chunklar
        "fallback_used": bool,
        "owner_mismatch": int,
        "debug": {...}
    }
    """
    strict_results = []
    owner_mismatch_count = 0

    for p in points:
        payload = p.payload if hasattr(p, "payload") else p.get("payload", {})
        if _is_chunk_safe_for_query(payload, requested_fakulteler):
            strict_results.append(p)
        else:
            owner_mismatch_count += 1
            effective = _get_effective_fakulte(payload)
            logger.debug(
                f"  ❌ Owner mismatch: effective={effective}, "
                f"requested={requested_fakulteler}, "
                f"url={payload.get('source_url', '?')[:80]}"
            )

    fallback_used = False

    # Fallback: strict çok az sonuç verdiyse genel üniversite kaynaklarını ekle
    if len(strict_results) < STRICT_MIN_RESULTS:
        logger.info(
            f"Strict sonuç yetersiz ({len(strict_results)}<{STRICT_MIN_RESULTS}), "
            f"university fallback devreye giriyor."
        )
        fallback_used = True
        for p in points:
            payload = p.payload if hasattr(p, "payload") else p.get("payload", {})
            scope = (payload.get("scope") or "").strip()
            detected = (payload.get("detected_fakulte") or "").strip()

            if scope == "university" and not detected:
                if p not in strict_results:
                    strict_results.append(p)

    debug = {
        "total_candidates": len(points),
        "strict_passed": len(strict_results),
        "owner_mismatch_eliminated": owner_mismatch_count,
        "fallback_used": fallback_used,
        "requested_fakulteler": requested_fakulteler,
    }

    logger.info(
        f"🔎 Filtre: {debug['total_candidates']} aday → "
        f"{debug['strict_passed']} geçti, "
        f"{debug['owner_mismatch_eliminated']} owner mismatch elendi"
        f"{', fallback kullanıldı' if fallback_used else ''}"
    )

    return {
        "strict": strict_results,
        "fallback_used": fallback_used,
        "owner_mismatch": owner_mismatch_count,
        "debug": debug,
    }


def _point_to_doc(hit, rerank_score: float | None = None) -> dict:
    """
    Qdrant ScoredPoint → standart doc dict dönüşümü.

    score alanı:
      - rerank_score verilmişse onu kullanır (reranker logit).
      - verilmemişse Qdrant/RRF fusion score'unu taşır.
    metadata içinde her iki skor kaynağı ayrıca saklanır.
    """
    payload = hit.payload if hasattr(hit, "payload") else hit.get("payload", {})
    retrieval_score = hit.score if hasattr(hit, "score") else 0.0

    # Reranker skoru varsa onu ana skor yap; yoksa retrieval score'u taşı.
    effective_score = rerank_score if rerank_score is not None else retrieval_score

    return {
        "text": payload.get("text", ""),
        "score": effective_score,
        "source_url": payload.get("source_url", ""),
        "metadata": {
            "unit": payload.get("unit", ""),
            "unit_label": payload.get("unit_label", ""),
            "fakulte": payload.get("fakulte", ""),
            "source_fakulte": payload.get("source_fakulte", ""),
            "detected_fakulte": payload.get("detected_fakulte", ""),
            "scope": payload.get("scope", ""),
            "doc_type": payload.get("doc_type", ""),
            "page_no": payload.get("page_no"),
            "ann_id": payload.get("ann_id"),
            "title": payload.get("title", ""),
            "source_url": payload.get("source_url", ""),
            "pdf_url": payload.get("pdf_url", ""),
            "content_hash": payload.get("content_hash", ""),
            "retrieval_score": retrieval_score,
            "rerank_score": rerank_score,
        },
    }


# ── Ana Retriever Sınıfı ─────────────────────────────────────

class Retriever:
    def __init__(self):
        from qdrant_client import QdrantClient

        db_path = os.path.join(os.getcwd(), "qdrant_storage")
        if not os.path.exists(db_path):
            logger.warning("qdrant_storage bulunamadı! Lütfen önce indexer'ı çalıştırın.")

        self.client = QdrantClient(path=db_path)
        self.collection_name = os.getenv("QDRANT_COLLECTION", "inonu_docs")

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        logger.info(f"Soru aranıyor: {query}")

        # 1. Sorguyu zenginleştir ve vektöre çevir
        from engine.embedding import encode_batch
        from tools.reranker import rerank
        from qdrant_client import models

        search_query = _augment_query(query)
        embeddings = encode_batch([search_query])
        dense_vec = embeddings["dense"][0]

        try:
            # 2. Hybrid (Dense + Sparse) arama
            sparse_dict = embeddings["sparse"][0]
            indices = [int(k) for k in sparse_dict.keys()]
            values = [float(v) for v in sparse_dict.values()]

            response = self.client.query_points(
                collection_name=self.collection_name,
                prefetch=[
                    models.Prefetch(
                        query=dense_vec,
                        using="dense",
                        limit=60,
                    ),
                    models.Prefetch(
                        query=models.SparseVector(
                            indices=indices,
                            values=values,
                        ),
                        using="sparse",
                        limit=60,
                    )
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=60,
                with_payload=True
            )

            # 3. Fakülte Strict/Fallback filtresi
            requested = extract_requested_faculties(query)
            if requested:
                logger.info(f"🔎 Fakülte filtresi aktif: {requested}")
                filter_result = filter_by_fakulte(response.points, requested)
                valid_points = filter_result["strict"]
            else:
                valid_points = response.points

            # 4. Re-Ranker
            reranked_points = rerank(search_query, valid_points, top_n=top_k)

            # 5. Doc dönüşümü
            # NOT: Skor eşiği (threshold) burada uygulanmaz.
            # RRF fusion score ve reranker logit score farklı ölçeklerdedir.
            # Reranker skoru ayrıştırıldığında (Adım 7) threshold reranker
            # logit'ine uygulanabilir. Şu an filtresiz geçirilir.
            docs = [_point_to_doc(hit) for hit in reranked_points]

            logger.info(f"{len(docs)} adet ilgili metin bulundu.")
            return docs

        except Exception as e:
            logger.error(f"Arama sırasında hata: {e}")
            return []


if __name__ == "__main__":
    retriever = Retriever()
    res = retriever.search("Yemekhane ücretleri ne kadar?")
    for r in res:
        print(f"\n[Score: {r['score']}] - {r['source_url']}\n{r['text']}")
