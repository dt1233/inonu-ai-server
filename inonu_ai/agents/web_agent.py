#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İnönü AI — Web Agent
Crawl4AI ile canlı web kazıma — Dinamik içerik erişimi

NOT: Bu modül gelecek sürümde aktifleştirilecektir.
Şu an tüm bilgi erişimi Qdrant vektör veritabanı üzerinden yapılmaktadır.
"""

from loguru import logger


async def web_search(query: str) -> str:
    """
    Canlı web araması yaparak güncel bilgi getirir.
    Qdrant'ta yanıt bulunamadığında devreye girer.

    Args:
        query: Aranacak sorgu

    Returns:
        Web'den çekilen metin içeriği
    """
    logger.info(f"Web araması: {query[:60]}...")

    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

        browser_cfg = BrowserConfig(
            headless=True,
            verbose=False,
            extra_args=["--no-sandbox"],
        )

        search_url = f"https://www.google.com/search?q=site:inonu.edu.tr+{query}"

        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            result = await crawler.arun(
                url=search_url,
                config=CrawlerRunConfig(verbose=False),
            )
            if result.success and result.markdown:
                content = result.markdown.fit_markdown or ""
                logger.info(f"Web sonucu: {len(content)} karakter")
                return content[:2000]  # İlk 2000 karakter yeterli

    except Exception as e:
        logger.warning(f"Web araması başarısız: {e}")

    return ""
