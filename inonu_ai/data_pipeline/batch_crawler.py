#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İNÖNÜ AI │ batch_crawler.py
Sadece öğrenci DB duyuruları + statik içerikler
"""

import asyncio
import io
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup
from loguru import logger

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

from .url_config import ANNOUNCEMENT_API, CrawlType, UrlTarget

BASE_PANEL      = "https://panel.inonu.edu.tr"
REQUEST_DELAY   = 0.8
REQUEST_TIMEOUT = 30

PDF_DIR    = Path("pdf_belgeler")
_INVISIBLE = {"\u200b", "\u200c", "\u200d", "\u00a0", "\ufeff"}


def _browser_cfg() -> BrowserConfig:
    return BrowserConfig(
        headless=True,
        verbose=False,
        extra_args=["--no-sandbox", "--disable-dev-shm-usage"],
    )


def _api_run_cfg() -> CrawlerRunConfig:
    return CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        page_timeout=REQUEST_TIMEOUT * 1000,
        verbose=False,
    )


def _html_run_cfg(js_wait_ms: int = 1500) -> CrawlerRunConfig:
    return CrawlerRunConfig(
        markdown_generator=DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(
                threshold=0.45, threshold_type="fixed", min_word_threshold=5,
            )
        ),
        cache_mode=CacheMode.BYPASS,
        wait_for_timeout=js_wait_ms,
        page_timeout=REQUEST_TIMEOUT * 1000,
        verbose=False,
    )


def _pdf_run_cfg() -> CrawlerRunConfig:
    return CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        page_timeout=REQUEST_TIMEOUT * 1000,
        verbose=False,
    )


async def _crawl_json(url: str, crawler: AsyncWebCrawler) -> Optional[dict | list]:
    result = await crawler.arun(url=url, config=_api_run_cfg())
    if not result.success:
        logger.warning(f"JSON hata [{url[:70]}]: {result.error_message}")
        return None

    html = result.html or ""
    pre_match = re.search(r"<pre[^>]*>(.*?)</pre>", html, re.DOTALL)
    raw = pre_match.group(1) if pre_match else html
    raw = raw.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")

    try:
        return json.loads(raw)
    except Exception:
        try:
            return json.loads(result.cleaned_html or "")
        except Exception:
            logger.warning(f"JSON parse başarısız: {url[:70]}")
            return None


async def _crawl_html(url: str, crawler: AsyncWebCrawler,
                       js_wait_ms: int = 1500) -> tuple[str, list[str]]:
    result = await crawler.arun(url=url, config=_html_run_cfg(js_wait_ms))
    if not result.success:
        logger.warning(f"HTML hata [{url[:70]}]: {result.error_message}")
        return "", []

    markdown  = (result.markdown.fit_markdown if result.markdown else "") or ""
    pdf_links = [
        lnk["href"]
        for lnk in (result.links.get("external", []) + result.links.get("internal", []))
        if ".pdf" in lnk.get("href", "").lower()
    ]
    return markdown, list(dict.fromkeys(pdf_links))


def _extract_pdf_text(pdf_bytes: bytes) -> Optional[str]:
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = "\n".join(p.extract_text() or "" for p in reader.pages).strip()
        if text:
            return text
    except Exception:
        pass
    try:
        from pdfminer.high_level import extract_text as pm_extract
        text = pm_extract(io.BytesIO(pdf_bytes)).strip()
        if text:
            return text
    except Exception:
        pass
    return None


async def _crawl_pdf(url: str, ann_id, label: str,
                      crawler: AsyncWebCrawler) -> dict:
    result = {"pdfUrl": url, "pdfPath": None, "pdfText": None, "error": None}

    if url.startswith("file://"):
        result["error"] = "Yerel dosya, atlandı"
        return result

    logger.info(f"PDF indiriliyor: {url[:70]}")
    run = await crawler.arun(url=url, config=_pdf_run_cfg())
    if not run.success:
        result["error"] = run.error_message
        return result

    raw = run.html or ""
    if raw.strip().startswith("%PDF") or (run.media and run.media.get("raw_bytes")):
        pdf_bytes = (run.media or {}).get("raw_bytes") or raw.encode()
    else:
        result["pdfText"] = run.markdown.fit_markdown if run.markdown else raw
        result["error"]   = "PDF değil, HTML yanıt"
        return result

    PDF_DIR.mkdir(exist_ok=True)
    safe = re.sub(r"[^\w.\-]", "_", url.split("/")[-1].split("?")[0]) or "belge.pdf"
    path = PDF_DIR / f"{ann_id}_{label}_{safe}"
    try:
        path.write_bytes(pdf_bytes)
        result["pdfPath"] = str(path)
    except OSError as e:
        logger.warning(f"PDF diske yazılamadı: {e}")

    result["pdfText"] = _extract_pdf_text(pdf_bytes)
    return result


def _html_to_text(html_str: str, base_url: str = BASE_PANEL) -> tuple[str, list[str]]:
    if not html_str or not html_str.strip():
        return "", []

    html_str = html_str.replace("\\/", "/")
    soup = BeautifulSoup(html_str, "lxml")

    for tag in soup(["script", "style", "head", "meta", "link", "noscript"]):
        tag.decompose()

    pdf_links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip().strip('"').strip("'")
        if href.startswith("/"):
            href = base_url + href
        link_text = a.get_text(strip=True)
        if ".pdf" in href.lower():
            if href not in pdf_links:
                pdf_links.append(href)
            a.replace_with(f"{link_text} [PDF]" if link_text else "[PDF]")
        else:
            a.replace_with(f"{link_text} ({href})" if link_text and link_text != href else href)

    for tag in soup.find_all(["p", "div", "li", "tr", "br",
                               "h1", "h2", "h3", "h4", "h5", "h6"]):
        tag.insert_after("\n")

    raw = soup.get_text(separator=" ")
    lines = []
    for line in raw.splitlines():
        line = "".join(ch for ch in line if ch not in _INVISIBLE).strip()
        if line:
            lines.append(line)

    return "\n".join(lines), list(dict.fromkeys(pdf_links))


def _extract_html_field(item: dict) -> str:
    raw = item.get("text") or item.get("content") or item.get("body") or ""
    stripped = raw.strip()
    if stripped.startswith(("[", "{")):
        try:
            inner = json.loads(raw)
            if isinstance(inner, list) and inner:
                raw = inner[0].get("text", raw)
            elif isinstance(inner, dict):
                raw = inner.get("text", raw)
        except Exception:
            pass
    return raw


def _parse_content_api(data) -> tuple[str, list[str], dict]:
    extra: dict = {}

    if isinstance(data, list):
        blocks, all_pdfs = [], []
        for idx, item in enumerate(data):
            if not isinstance(item, dict):
                continue
            raw_html    = _extract_html_field(item)
            clean, pdfs = _html_to_text(raw_html)
            title       = (item.get("title") or "").strip()
            if clean:
                header = f"── {title} ──\n" if title and len(data) > 1 else ""
                blocks.append(f"{header}{clean}")
            for p in pdfs:
                if p not in all_pdfs:
                    all_pdfs.append(p)
            if idx == 0:
                extra = {k: v for k, v in item.items()
                         if k not in ("text", "content", "body")}
        return "\n\n".join(blocks), all_pdfs, extra

    if isinstance(data, dict):
        raw_html    = _extract_html_field(data)
        extra       = {k: v for k, v in data.items()
                       if k not in ("text", "content", "body")}
        clean, pdfs = _html_to_text(raw_html)
        return clean, pdfs, extra

    return "", [], extra


def _parse_staff_api(data) -> list[dict]:
    if not isinstance(data, list):
        return []
    result = []
    for item in data:
        s = item.get("staff") if isinstance(item, dict) else None
        if not s:
            continue
        ad_soyad  = f"{(s.get('name') or '').strip()} {(s.get('surName') or '').strip()}".strip()
        unvan     = (((s.get("staffTitle") or {}).get("translateStaffCadre") or {})
                     .get("tr", {}).get("title", "")).strip()
        departman = (((s.get("staffGroup") or {}).get("translateStaffGroup") or {})
                     .get("tr", {}).get("title", "")).strip()
        tr_data   = ((s.get("translateStaff") or {}).get("tr") or {})
        gorev     = (tr_data.get("description") or tr_data.get("position") or "").strip()
        result.append({
            "id":        s.get("id", ""),
            "ad_soyad":  ad_soyad,
            "unvan":     unvan,
            "departman": departman,
            "gorev":     gorev,
            "email":     (s.get("email") or "").strip(),
            "telefon":   (s.get("phone") or "").strip(),
        })
    return result


async def _fetch_sss(parent_id: int, crawler: AsyncWebCrawler) -> dict:
    menu_url  = f"{BASE_PANEL}/servlet/menu?type=inside&id={parent_id}"
    menu_data = await _crawl_json(menu_url, crawler)
    if not menu_data or not isinstance(menu_data, list):
        return {}

    all_data: dict = {}

    def _parse_items(data):
        if not isinstance(data, list):
            return data
        results = []
        for item in data:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            clean, pdf_links = _html_to_text(item.get("text") or "")
            entry = {"id": item.get("id", ""), "baslik": title, "icerik": clean}
            if pdf_links:
                entry["pdf_links"] = pdf_links
            results.append(entry)
        return results

    main = await _crawl_json(
        f"{BASE_PANEL}/servlet/content?id={parent_id}&lang=tr", crawler
    )
    if main:
        all_data[str(parent_id)] = {
            "baslik": "Sıkça Sorulan Sorular (Genel)",
            "content": _parse_items(main),
        }

    for item in menu_data:
        cid = item.get("id")
        if not cid or cid == parent_id:
            continue
        try:
            tr_name = json.loads(item.get("translate", "{}")).get("tr", str(cid))
        except Exception:
            tr_name = str(cid)

        content = await _crawl_json(
            f"{BASE_PANEL}/servlet/content?id={cid}&lang=tr", crawler
        )
        if content:
            all_data[str(cid)] = {
                "baslik": tr_name,
                "content": _parse_items(content),
            }
        await asyncio.sleep(REQUEST_DELAY)

    return all_data


async def _fetch_ann_list(max_known_id: int,
                           crawler: AsyncWebCrawler) -> list[dict]:
    new_items: list[dict] = []
    page = 1
    url_tpl = ANNOUNCEMENT_API.url

    while True:
        url  = url_tpl.format(page=page)
        data = await _crawl_json(url, crawler)
        if not data or not isinstance(data, list):
            logger.info(f"Sayfa {page} boş, tarama tamamlandı.")
            break

        page_ids = [it.get("id", 0) for it in data]
        page_new = [it for it in data if it.get("id", 0) > max_known_id]
        new_items.extend(page_new)

        logger.info(
            f"Sayfa {page} · {len(data)} kayıt · "
            f"ID {min(page_ids)}–{max(page_ids)} · yeni: {len(page_new)}"
        )

        if min(page_ids) <= max_known_id:
            logger.info("Bilinen ID'lere ulaşıldı, tarama durdu.")
            break

        page += 1
        await asyncio.sleep(REQUEST_DELAY)

    return new_items


async def _process_ann(item: dict, crawler: AsyncWebCrawler) -> dict:
    ann_id    = item["id"]
    url_field = (item.get("url") or "").strip()
    detail_tpl = ANNOUNCEMENT_API.extra["detail_url"]

    record = {
        "fetchedAt":   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sourceUrl":   "",
        "id":          ann_id,
        "title":       item.get("title", ""),
        "updated":     item.get("updated", ""),
        "content":     None,
        "attachments": [],
    }

    if url_field:
        record["sourceUrl"] = url_field
        if ".pdf" in url_field.lower():
            pdf = await _crawl_pdf(url_field, ann_id, "A", crawler)
            record["content"] = "Bu duyuru doğrudan bir PDF dosyasıdır."
            record["attachments"].append({
                "url": url_field, "type": "pdf",
                "content": pdf["pdfText"] or "[PDF Okunamadı]",
            })
        else:
            markdown, pdf_links = await _crawl_html(url_field, crawler)
            record["content"] = markdown or "[İçerik alınamadı]"
            for idx, href in enumerate(pdf_links, 1):
                pdf = await _crawl_pdf(href, ann_id, f"A{idx}", crawler)
                record["attachments"].append({
                    "url": href, "type": "pdf",
                    "content": pdf["pdfText"] or "[PDF Okunamadı]",
                })
        return record

    detail_url          = detail_tpl.format(id=ann_id)
    record["sourceUrl"] = detail_url

    detail_data = await _crawl_json(detail_url, crawler)
    if detail_data is None:
        record["content"] = "[Detay içeriği alınamadı]"
        return record

    raw_html = (detail_data.get("text") or detail_data.get("content") or ""
                if isinstance(detail_data, dict) else "")
    clean, pdf_links = _html_to_text(raw_html)
    record["content"] = clean or None

    for idx, href in enumerate(pdf_links, 1):
        if href.startswith("file://"):
            continue
        pdf = await _crawl_pdf(href, ann_id, f"B{idx}", crawler)
        record["attachments"].append({
            "url": href, "type": "pdf",
            "content": pdf["pdfText"] or "[PDF Okunamadı]",
        })

    return record


class BatchCrawler:

    def __init__(self, max_known_ann_id: int = 0):
        self.max_known_ann_id = max_known_ann_id

    async def run_announcements(self, crawler: AsyncWebCrawler) -> list[dict]:
        logger.info("── Duyuru taraması başlıyor ──")
        new_items = await _fetch_ann_list(self.max_known_ann_id, crawler)
        if not new_items:
            logger.info("Yeni duyuru yok.")
            return []

        new_items.sort(key=lambda x: x["id"], reverse=True)
        results: list[dict] = []

        for i, item in enumerate(new_items, 1):
            logger.info(f"Duyuru {i}/{len(new_items)}: ID {item['id']}")
            try:
                record = await _process_ann(item, crawler)
                results.append(record)
            except Exception as e:
                logger.error(f"ID {item['id']} hata: {e}")
            await asyncio.sleep(REQUEST_DELAY)

        logger.info(f"Duyuru taraması bitti: {len(results)} kayıt")
        return results

    async def run_static_content(self, crawler: AsyncWebCrawler) -> list[dict]:
        logger.info("── Statik içerik taraması başlıyor ──")
        from .url_config import STATIC_CONTENT_SOURCES

        results: list[dict] = []
        for target in STATIC_CONTENT_SOURCES:
            logger.info(f"[{target.key}] {target.label}")
            record = await self._process_api_target(target, crawler)
            results.append(record)
            await asyncio.sleep(REQUEST_DELAY)

        logger.info(f"Statik içerik bitti: {len(results)} kaynak")
        return results

    async def _process_api_target(self, target: UrlTarget,
                                    crawler: AsyncWebCrawler) -> dict:
        fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        base = {
            "key":       target.key,
            "label":     target.label,
            "url":       target.url,
            "fetchedAt": fetched_at,
            "content":   None,
            "pdfLinks":  [],
            "extra":     {},
            "error":     None,
        }

        if target.crawl_type == CrawlType.API_SSS:
            parent_id = target.extra.get("parent_id", 1636)
            sss_data  = await _fetch_sss(parent_id, crawler)
            if not sss_data:
                base["error"] = "SSS verisi çekilemedi"
                return base
            base["content"] = sss_data
            cats  = len(sss_data)
            items = sum(
                len(v.get("content", [])) if isinstance(v.get("content"), list) else 1
                for v in sss_data.values()
            )
            base["extra"] = {"categories": cats, "total_questions": items}
            logger.info(f"SSS: {cats} kategori, {items} soru")
            return base

        data = await _crawl_json(target.url, crawler)
        if data is None:
            base["error"] = "Veri çekilemedi"
            return base

        if target.crawl_type == CrawlType.API_STAFF:
            staff = _parse_staff_api(data)
            base["content"] = staff
            base["extra"]   = {"count": len(staff)}
            logger.info(f"Personel: {len(staff)} kayıt")

        elif target.crawl_type == CrawlType.API_JSON:
            clean, pdfs, extra = _parse_content_api(data)
            base["content"]  = clean or "[İçerik boş]"
            base["pdfLinks"] = pdfs
            base["extra"]    = extra
            logger.info(f"{target.label}: {len(clean)} kar" +
                        (f", {len(pdfs)} PDF" if pdfs else ""))

        return base

    async def run_all(self) -> dict[str, list[dict]]:
        logger.info("═══ BATCH CRAWLER BAŞLIYOR ═══")
        t0 = time.time()

        async with AsyncWebCrawler(config=_browser_cfg()) as crawler:
            ann_results    = await self.run_announcements(crawler)
            static_results = await self.run_static_content(crawler)

        elapsed = time.time() - t0
        logger.info(
            f"═══ TAMAMLANDI ═══ {elapsed:.1f}s | "
            f"duyuru:{len(ann_results)} statik:{len(static_results)}"
        )
        return {
            "announcements":   ann_results,
            "static_contents": static_results,
        }


async def _main():
    crawler = BatchCrawler(max_known_ann_id=0)
    results = await crawler.run_all()
    out = Path("crawl_results.json")
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Kaydedildi: {out}")


if __name__ == "__main__":
    asyncio.run(_main())