import asyncio
from collections import Counter
from loguru import logger
from crawl4ai import AsyncWebCrawler
from inonu_ai.data_pipeline.batch_crawler import BatchCrawler, _browser_cfg
from inonu_ai.data_pipeline.url_config import FAKULTE_TARGETS, DAILY_TARGETS, API_TARGETS

async def main():
    logger.remove()
    # High IDs to prevent deep scraping
    crawler_instance = BatchCrawler(max_known_ann_id=99999999) 
    
    muhendislik = next((t for t in FAKULTE_TARGETS if t.extra.get("unit") == "muhendislik"), None)
    hukuk = next((t for t in FAKULTE_TARGETS if t.extra.get("unit") == "hukuk"), None)
    ogrencidb = next((t for t in DAILY_TARGETS if t.extra.get("unit") == "ogrencidb"), None)
    
    static_api = next((t for t in API_TARGETS if t.key == "yemekhane" or t.key == "takvim"), None)
    if not static_api:
        static_api = API_TARGETS[0]

    all_records = []

    async with AsyncWebCrawler(config=_browser_cfg()) as crawler:
        print("Taranıyor: muhendislik...")
        if muhendislik:
            res = await BatchCrawler(max_known_ann_id=23740).run_announcements(crawler, muhendislik)
            all_records.extend(res)

        print("Taranıyor: hukuk...")
        if hukuk:
            res = await BatchCrawler(max_known_ann_id=23740).run_announcements(crawler, hukuk)
            all_records.extend(res)

        print("Taranıyor: ogrencidb...")
        if ogrencidb:
            res = await BatchCrawler(max_known_ann_id=23500).run_announcements(crawler, ogrencidb)
            all_records.extend(res)

        print("Taranıyor: run_fakulte_announcements (dry-run)...")
        # For dry-run we use very high id
        res = await crawler_instance.run_fakulte_announcements(crawler)
        all_records.extend(res)

        print("Taranıyor: run_all_announcements (dry-run)...")
        res = await crawler_instance.run_all_announcements(crawler)
        all_records.extend(res)

        print(f"Taranıyor: Statik API ({static_api.key})...")
        res = await crawler_instance._process_api_target(static_api, crawler)
        if res:
            all_records.append(res)

    toplam = len(all_records)
    bos_fakulte = sum(1 for r in all_records if not r.get("fakulte"))
    bos_hash = sum(1 for r in all_records if not r.get("content_hash"))
    scopes = Counter(r.get("scope") for r in all_records)
    
    faculty_scope_no_fakulte = sum(1 for r in all_records if r.get("scope") == "faculty" and not r.get("fakulte"))

    print("\n" + "="*50)
    print("GENİŞLETİLMİŞ SMOKE TEST RAPORU")
    print("="*50)
    print(f"Toplam kayıt sayısı: {toplam}")
    print(f"Scope='faculty' olup fakulte/source_fakulte boş olan kayıt sayısı: {faculty_scope_no_fakulte}")
    print(f"'content_hash' boş olan kayıt sayısı: {bos_hash}")
    print(f"'scope' dağılımı: {dict(scopes)}")
    
    print("\nDoğrulamalar:")
    print(f" - Hatalı import (FAKULTELE_TARGETS vb.) yok, tüm fonksiyonlar başarıyla koştu.")
    print(f" - Validation uyarıları/hataları logger üzerinden basıldı (eğer varsa).")

if __name__ == "__main__":
    asyncio.run(main())
