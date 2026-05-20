#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İnönü AI — Canlı Kazıma Aracı
Crawl4AI ile anlık web sayfası içerik çekme
"""

from typing import Optional
from loguru import logger


async def scrape_url(url: str, js_wait_ms: int = 1500) -> dict:
    """
    Verilen URL'den anlık olarak içerik çeker.

    Args:
        url: Kazınacak web sayfası URL'si
        js_wait_ms: JavaScript yükleme bekleme süresi (ms)

    Returns:
        {"content": str, "pdf_links": list, "success": bool}
    """
    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
        from crawl4ai.content_filter_strategy import PruningContentFilter
        from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

        browser_cfg = BrowserConfig(
            headless=True,
            verbose=False,
            extra_args=["--no-sandbox", "--disable-dev-shm-usage"],
        )

        run_cfg = CrawlerRunConfig(
            markdown_generator=DefaultMarkdownGenerator(
                content_filter=PruningContentFilter(
                    threshold=0.45, threshold_type="fixed", min_word_threshold=5,
                )
            ),
            cache_mode=CacheMode.BYPASS,
            wait_for_timeout=js_wait_ms,
            page_timeout=30000,
            verbose=False,
        )

        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            result = await crawler.arun(url=url, config=run_cfg)

            if not result.success:
                logger.warning(f"Kazıma başarısız [{url[:70]}]: {result.error_message}")
                return {"content": "", "pdf_links": [], "success": False}

            markdown = (result.markdown.fit_markdown if result.markdown else "") or ""
            pdf_links = [
                lnk["href"]
                for lnk in (
                    result.links.get("external", [])
                    + result.links.get("internal", [])
                )
                if ".pdf" in lnk.get("href", "").lower()
            ]

            logger.info(f"Kazıma başarılı [{url[:50]}]: {len(markdown)} karakter")
            return {
                "content": markdown,
                "pdf_links": list(dict.fromkeys(pdf_links)),
                "success": True,
            }

    except Exception as e:
        logger.error(f"Kazıma hatası [{url[:50]}]: {e}")
        return {"content": "", "pdf_links": [], "success": False}


async def scrape_multiple(urls: list[str]) -> list[dict]:
    """Birden fazla URL'yi sırayla kazır."""
    results = []
    for url in urls:
        result = await scrape_url(url)
        results.append({"url": url, **result})
    return results
