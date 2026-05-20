import asyncio
from inonu_ai.data_pipeline.avesis_crawler import AvesisCrawler

async def main():
    crawler = AvesisCrawler()
    # Mock the internal targets to just test one faculty (e.g., Hukuk)
    from inonu_ai.data_pipeline.url_config import UrlTarget, CrawlType, CrawlFrequency
    crawler._targets = [UrlTarget(
        key="hukuk_avesis", label="Hukuk Fakültesi", url="https://avesis.inonu.edu.tr/unitreport/reports?unitId=12", crawl_type=CrawlType.AVESIS, frequency=CrawlFrequency.WEEKLY, priority=1, extra={"unit_id": 12, "fakulte": "Hukuk Fakültesi"}
    )]
    results = await crawler.crawl_all()
    
    for r in results:
        print(f"Birim: {r['label']} - Personel Sayisi: {len(r['content'])}")
        for p in r['content'][:3]:
            print("  -", p['ad_soyad'], p.get('unvan', ''), p.get('bolum', ''))

if __name__ == "__main__":
    asyncio.run(main())
