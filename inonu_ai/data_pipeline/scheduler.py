#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║  İNÖNÜ AI │ scheduler.py                                         ║
║  APScheduler — Cron Tabanlı Otomatik Kazıma                      ║
║                                                                  ║
║  Günlük  02:00 → duyurular (delta fetch)                        ║
║  Haftalık 03:00 → personel, oryantasyon, seçmeli dersler,       ║
║                    sınav programı, ÜSD dersler                   ║
║  Aylık   04:00 → tarihçe, misyon/vizyon, iç kontrol, SSS        ║
╚══════════════════════════════════════════════════════════════════╝
"""

import asyncio
import os
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from .batch_crawler import BatchCrawler
from .chunker import Chunker
from .indexer import Indexer
from .url_config import DAILY_TARGETS, MONTHLY_TARGETS, WEEKLY_TARGETS


# ─────────────────────────────────────────────────────────────────
# Max bilinen duyuru ID — Qdrant'tan okunur
# ─────────────────────────────────────────────────────────────────

def _get_max_ann_id() -> int:
    """
    Qdrant'taki en yüksek duyuru ann_id'sini döndür.
    Delta fetch için kritik — sadece bu ID'den büyük duyurular çekilir.
    """
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(
            host=os.getenv("QDRANT_HOST", "localhost"),
            port=int(os.getenv("QDRANT_PORT", "6333")),
        )
        results, _ = client.scroll(
            collection_name=os.getenv("QDRANT_COLLECTION", "inonu_docs"),
            scroll_filter=None,
            limit=1,
            with_payload=True,
            with_vectors=False,
        )
        if results:
            return int(results[0].payload.get("ann_id", 0))
    except Exception as e:
        logger.warning(f"Max ann_id Qdrant'tan okunamadı: {e}")
    return 0


# ─────────────────────────────────────────────────────────────────
# Pipeline yardımcısı
# ─────────────────────────────────────────────────────────────────

async def _run_pipeline(target_keys: set[str], label: str) -> None:
    """
    Belirli key'lere ait hedefleri crawl → chunk → index pipeline'ından geçir.
    Tek Crawl4AI oturumu açılır, tüm işler bu oturumda tamamlanır.
    """
    logger.info(f"═══ {label} PIPELINE BAŞLIYOR ═══")
    t0 = datetime.now()

    from .url_config import ANNOUNCEMENT_API, STATIC_CONTENT_SOURCES
    from crawl4ai import AsyncWebCrawler
    from .batch_crawler import _browser_cfg

    crawler_obj = BatchCrawler(max_known_ann_id=_get_max_ann_id())
    chunker     = Chunker()
    indexer     = Indexer()

    results: dict[str, list] = {"announcements": [], "static_contents": []}

    async with AsyncWebCrawler(config=_browser_cfg()) as crawler:
        # Duyurular (sadece günlük pipeline'da)
        if ANNOUNCEMENT_API.key in target_keys:
            results["announcements"] = await crawler_obj.run_announcements(crawler)

        # Statik içerikler (hedef key'e göre filtrele)
        static_targets = [t for t in STATIC_CONTENT_SOURCES if t.key in target_keys]
        if static_targets:
            from .url_config import STATIC_CONTENT_SOURCES as _SC
            _orig = list(_SC)
            import data_pipeline.url_config as _cfg
            _cfg.STATIC_CONTENT_SOURCES = static_targets
            results["static_contents"] = await crawler_obj.run_static_content(crawler)
            _cfg.STATIC_CONTENT_SOURCES = _orig

    chunks  = chunker.chunk_all(results)
    written = indexer.index_chunks(chunks)

    elapsed = (datetime.now() - t0).total_seconds()
    logger.info(
        f"═══ {label} TAMAMLANDI ═══ "
        f"{elapsed:.0f}s | chunk:{len(chunks)} | yazılan:{written}"
    )


# ─────────────────────────────────────────────────────────────────
# Cron görevleri
# ─────────────────────────────────────────────────────────────────

async def _daily_job():
    await _run_pipeline({t.key for t in DAILY_TARGETS}, "GÜNLÜK")

async def _weekly_job():
    await _run_pipeline({t.key for t in WEEKLY_TARGETS}, "HAFTALIK")

async def _monthly_job():
    await _run_pipeline({t.key for t in MONTHLY_TARGETS}, "AYLIK")

async def _full_initial_crawl():
    """İlk çalıştırma — tüm kaynakları sıfırdan index'le."""
    logger.info("═══ TAM KAZIMA BAŞLIYOR ═══")
    crawler = BatchCrawler(max_known_ann_id=0)
    results = await crawler.run_all()
    chunks  = Chunker().chunk_all(results)
    written = Indexer().index_chunks(chunks)
    logger.info(f"Tam kazıma tamamlandı: {written} chunk yazıldı")


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
    scheduler.add_job(
        _monthly_job,
        CronTrigger(day=1, hour=4, minute=0),
        id="monthly_crawl", name="Aylık Kazıma",
        replace_existing=True, misfire_grace_time=7200,
    )

    logger.info("Scheduler hazır: günlük 02:00 | haftalık Pzt 03:00 | aylık 1. gün 04:00")
    return scheduler


# ─────────────────────────────────────────────────────────────────
# Doğrudan çalıştırma
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    arg = sys.argv[1] if len(sys.argv) > 1 else ""

    if arg == "--full":
        asyncio.run(_full_initial_crawl())
    elif arg == "--daily":
        asyncio.run(_daily_job())
    elif arg == "--weekly":
        asyncio.run(_weekly_job())
    elif arg == "--monthly":
        asyncio.run(_monthly_job())
    else:
        scheduler = build_scheduler()
        scheduler.start()
        logger.info("Scheduler başlatıldı. Çıkmak için Ctrl+C")
        try:
            asyncio.get_event_loop().run_forever()
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown()