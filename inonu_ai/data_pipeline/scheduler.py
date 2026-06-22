#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║  İNÖNÜ AI │ scheduler.py                                         ║
║  APScheduler — Cron Tabanlı Otomatik Kazıma                      ║
║                                                                  ║
║  Günlük  02:00 → tüm birim duyuruları (delta fetch)             ║
║  Haftalık 03:00 → personel, statik içerik, AVESİS, HTML         ║
║  Aylık   04:00 → aylık statik içerikler                         ║
╚══════════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from .batch_crawler import BatchCrawler
from .chunker import Chunker

try:
    from .indexer import Indexer
    HAS_INDEXER = True
except ImportError:
    HAS_INDEXER = False
    logger.warning("Indexer modülü içe aktarılamadı (FlagEmbedding vb. bağımlılıklar eksik). Veriler diske yazılacak ancak Vektör DB'ye aktarılmayacak.")

# Çıktı dosyaları
DATA_DIR = Path("data")
CRAWL_RESULTS_FILE = DATA_DIR / "crawl_results.json"
CHUNKS_OUTPUT_FILE = DATA_DIR / "chunks_output.json"

# Klasör yoksa otomatik oluştur
DATA_DIR.mkdir(exist_ok=True)



# ─────────────────────────────────────────────────────────────────
# Max bilinen duyuru ID — Qdrant'tan okunur
# ─────────────────────────────────────────────────────────────────

def _get_max_ann_id() -> int:
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(
            host=os.getenv("QDRANT_HOST", "localhost"),
            port=int(os.getenv("QDRANT_PORT", "6333")),
        )
        results, _ = client.scroll(
            collection_name=os.getenv("QDRANT_COLLECTION", "inonu_docs"),
            scroll_filter=None, limit=1,
            with_payload=True, with_vectors=False,
        )
        if results:
            return int(results[0].payload.get("ann_id", 0))
    except Exception as e:
        logger.warning(f"Max ann_id Qdrant'tan okunamadı: {e}")
    return 0


def _save_results_to_disk(results: dict, chunks: list) -> None:
    """Ham crawler sonuçlarını ve chunk'ları JSON olarak diske yaz."""
    # 1. Ham crawler çıktısı (Takım 2 girdisi)
    CRAWL_RESULTS_FILE.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(f"Ham veri kaydedildi: {CRAWL_RESULTS_FILE} ({CRAWL_RESULTS_FILE.stat().st_size / 1024:.0f} KB)")

    # 2. Chunk'lar (Takım 4 / Qdrant girdisi)
    chunk_dicts = [asdict(c) for c in chunks]
    CHUNKS_OUTPUT_FILE.write_text(
        json.dumps(chunk_dicts, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(f"Chunk'lar kaydedildi: {CHUNKS_OUTPUT_FILE} ({CHUNKS_OUTPUT_FILE.stat().st_size / 1024:.0f} KB)")


# ─────────────────────────────────────────────────────────────────
# Pipeline: crawl → chunk → index
# ─────────────────────────────────────────────────────────────────

async def _run_and_index(label: str, mode: str) -> None:
    """
    Belirtilen modda crawl yap, chunk'la ve Qdrant'a yaz.
    mode: "full" | "daily" | "weekly"
    """
    logger.info(f"═══ {label} PIPELINE BAŞLIYOR ═══")
    t0 = datetime.now()

    crawler = BatchCrawler(max_known_ann_id=_get_max_ann_id())

    if mode == "full":
        results = await crawler.run_all()
    elif mode == "daily":
        results = await crawler.run_daily()
    elif mode == "weekly":
        results = await crawler.run_weekly()
    else:
        logger.error(f"Bilinmeyen mod: {mode}")
        return

    # Her durumda ham veriyi diske yaz (Takım 2 için gerekli)
    _save_results_to_disk(results, [])

    if mode in ("weekly", "full"):
        try:
            # rebuild_pipeline.py ana dizinde, onu import etmek için sys.path ekle
            parent_dir = str(Path(__file__).parent.parent.parent)
            if parent_dir not in sys.path:
                sys.path.append(parent_dir)
            from rebuild_pipeline import PipelineOrchestrator
            
            logger.info("Yönetim rolleri ve AVESIS senkronizasyonu başlatılıyor (rebuild_pipeline)...")
            orch = PipelineOrchestrator()
            orch.gather_roles()
            orch.update_databases()
            
            # Diskten (senkronize edilmiş) en taze veriyi geri yükle
            with open(CRAWL_RESULTS_FILE, "r", encoding="utf-8") as f:
                results = json.load(f)
            logger.info("Rol senkronizasyonu tamamlandı. Chunking'e geçiliyor.")
        except Exception as e:
            logger.error(f"Rebuild pipeline hatası: {e}")

    chunker = Chunker()
    chunks = chunker.chunk_all(results)

    if not chunks:
        logger.info(f"{label}: Yazılacak chunk yok.")
        return

    # Chunk'ları da diske yaz
    _save_results_to_disk(results, chunks)

    if HAS_INDEXER:
        indexer = Indexer()
        written = indexer.index_chunks(chunks)
    else:
        logger.warning(f"{label}: Indexer aktif değil. {len(chunks)} chunk diske kaydedildi.")
        written = 0

    elapsed = (datetime.now() - t0).total_seconds()
    logger.info(
        f"═══ {label} TAMAMLANDI ═══ "
        f"{elapsed:.0f}s | chunk:{len(chunks)} | yazılan:{written}"
    )


# ─────────────────────────────────────────────────────────────────
# Cron görevleri
# ─────────────────────────────────────────────────────────────────

async def _daily_job():
    await _run_and_index("GÜNLÜK", "daily")

async def _weekly_job():
    await _run_and_index("HAFTALIK", "weekly")

async def _full_initial_crawl():
    """İlk çalıştırma — tüm kaynakları sıfırdan index'le."""
    await _run_and_index("TAM KAZIMA", "full")


# ─────────────────────────────────────────────────────────────────
# Scheduler kurulumu
# ─────────────────────────────────────────────────────────────────

def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Istanbul")

    scheduler.add_job(
        _daily_job,
        CronTrigger(hour=2, minute=0),
        id="daily_crawl", name="Günlük Kazıma",
        replace_existing=True, misfire_grace_time=3600,
    )
    scheduler.add_job(
        _weekly_job,
        CronTrigger(day_of_week="mon", hour=3, minute=0),
        id="weekly_crawl", name="Haftalık Kazıma",
        replace_existing=True, misfire_grace_time=3600,
    )

    logger.info("Scheduler hazır: günlük 02:00 | haftalık Pzt 03:00")
    return scheduler


# ─────────────────────────────────────────────────────────────────
# Doğrudan çalıştırma
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""

    if arg == "--full":
        asyncio.run(_full_initial_crawl())
    elif arg == "--daily":
        asyncio.run(_daily_job())
    elif arg == "--weekly":
        asyncio.run(_weekly_job())
    else:
        scheduler = build_scheduler()
        scheduler.start()
        logger.info("Scheduler başlatıldı. Çıkmak için Ctrl+C")
        try:
            asyncio.get_event_loop().run_forever()
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown()