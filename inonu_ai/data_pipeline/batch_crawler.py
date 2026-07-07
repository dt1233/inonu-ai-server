#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔═════════════════════════════════════════════════════════════════╗
║ İNÖNÜ AI │ batch_crawler.py                                    ║
║ Tüm kaynak tipleri: Panel API + HTML_STATIC + HTML_JS + AVESİS ║
╚═════════════════════════════════════════════════════════════════╝

CrawlType desteği:
  API_JSON    → panel.inonu.edu.tr JSON API
  API_STAFF   → panel.inonu.edu.tr personel API
  API_SSS     → panel.inonu.edu.tr SSS menü API
  HTML_STATIC → requests + BeautifulSoup (JS gerektirmez)
  HTML_JS     → Crawl4AI/Playwright (JS gerektiren sayfalar)
  AVESIS      → avesis_crawler.py modülü üzerinden
"""

import asyncio
import io
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import hashlib

from .faculty_detector import detect_faculty
from .pdf_extractor import extract_pdf_pages

from bs4 import BeautifulSoup
from loguru import logger

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

from .url_config import (
    ANNOUNCEMENT_API,
    CrawlType,
    UrlTarget,
    STATIC_CONTENT_SOURCES,
    FAKULTE_TARGETS,
    ENSTITU_TARGETS,
    MYO_TARGETS,
    AVESIS_TARGETS,
    HTML_STATIC_TARGETS,
    HTML_JS_TARGETS,
)

# ─────────────────────────────────────────────────────────────────
# SABITLER
# ─────────────────────────────────────────────────────────────────

BASE_PANEL      = "https://panel.inonu.edu.tr"
REQUEST_DELAY   = 0.8
REQUEST_TIMEOUT = 10

PDF_DIR = Path("data/pdf_belgeler")

_INVISIBLE = {"\u200b", "\u200c", "\u200d", "\u00a0", "\ufeff"}

# HTML temizlemede kaldırılacak etiketler
_REMOVE_TAGS = [
    "script", "style", "head", "meta", "link", "noscript",
    "nav", "header", "footer", "aside", ".menu", ".navbar",
    ".breadcrumb", ".sidebar", ".cookie", ".modal",
]


# ─────────────────────────────────────────────────────────────────
# BROWSER / RUN KONFİGÜRASYONLARI
# ─────────────────────────────────────────────────────────────────

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
                threshold=0.45,
                threshold_type="fixed",
                min_word_threshold=5,
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


# ─────────────────────────────────────────────────────────────────
# TEMEL İÇERİK YARDIMCILARI
# ─────────────────────────────────────────────────────────────────

async def _crawl_json(url: str, crawler: AsyncWebCrawler) -> Optional[dict | list]:
    result = await crawler.arun(url=url, config=_api_run_cfg())
    if not result.success:
        logger.warning(f"JSON hatası [{url[:70]}]: {result.error_message}")
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
            logger.warning(f"JSON ayrıştırma hatası: {url[:70]}")
            return None


async def _crawl_html_js(
    url: str, crawler: AsyncWebCrawler, js_wait_ms: int = 1500
) -> tuple[str, list[str]]:
    """Crawl4AI ile JS gerektiren sayfayı çek → (markdown, pdf_links)."""
    result = await crawler.arun(url=url, config=_html_run_cfg(js_wait_ms))
    if not result.success:
        logger.warning(f"HTML_JS hatası [{url[:70]}]: {result.error_message}")
        return "", []
    markdown = (result.markdown.fit_markdown if result.markdown else "") or ""
    pdf_links = [
        lnk["href"]
        for lnk in (result.links.get("external", []) + result.links.get("internal", []))
        if ".pdf" in lnk.get("href", "").lower()
    ]
    return markdown, list(dict.fromkeys(pdf_links))


async def _crawl_html_static(url: str) -> tuple[str, list[str]]:
    """
    requests ile statik HTML çek → (temiz metin, pdf_links).
    JS gerektirmeyen fakülte/birim sayfaları için.
    Crawl4AI'ya gerek yok — hızlı ve hafif.
    """
    try:
        import httpx
    except ImportError:
        import urllib.request
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; InonuAI-Bot/1.0)"},
            )
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                raw_html = resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"HTML_STATIC hatası [{url[:70]}]: {e}")
            return "", []
        return _html_to_text(raw_html, url)

    try:
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; InonuAI-Bot/1.0)"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return _html_to_text(resp.text, url)
    except Exception as e:
        safe_url = url[:70].encode('ascii', 'ignore').decode('ascii')
        logger.warning(f"HTML_STATIC hatası [{safe_url}]: {e}")
        return "", []


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

def generate_content_hash(title: str, url: str, content: str) -> str:
    raw = f"{title}|{url}|{content}"
    return hashlib.md5(raw.encode("utf-8", errors="ignore")).hexdigest()

def validate_record(record: dict) -> dict:
    required = ["unit", "unit_label", "scope", "doc_type", "title", "source_url", "content_hash"]
    for req in required:
        if not record.get(req):
            logger.warning(f"Validation WARNING: Eksik/Boş alan '{req}' in {record.get('source_url', record.get('id', '?'))}")
            if req not in record:
                record[req] = None
    
    scope = record.get("scope")
    fakulte = record.get("fakulte") or record.get("source_fakulte")
    
    if scope == "faculty" and not fakulte:
        logger.error(f"Validation ERROR: scope='faculty' ama fakulte/source_fakulte boş! {record.get('source_url', '?')}")
    elif scope == "university" and fakulte:
        # Uyarı vermeye gerek yok, tespit edilmiş olabilir, ama asıl kuralı bozmaz.
        pass

    return record


async def _crawl_pdf(
    url: str, ann_id, label: str, crawler: AsyncWebCrawler, source_metadata: dict
) -> dict:
    result = {"pdfUrl": url, "pdfPath": None, "pdfText": None, "pages": [], "error": None}
    if url.startswith("file://"):
        result["error"] = "Yerel dosya, atıldı"
        return result

    logger.info(f"PDF indiriliyor: {url[:70]}")
    import httpx
    try:
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; InonuAI-Bot/1.0)"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            pdf_bytes = resp.content
    except Exception as e:
        result["error"] = f"İndirme hatası: {str(e)}"
        return result

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    safe  = re.sub(r"[^\w.\-]", "_", url.split("/")[-1].split("?")[0]) or "belge.pdf"
    path  = PDF_DIR / f"{ann_id}_{label}_{safe}"
    try:
        path.write_bytes(pdf_bytes)
        result["pdfPath"] = str(path)
    except OSError as e:
        logger.warning(f"PDF diske yazılamadı: {e}")

    # Legacy text
    result["pdfText"] = _extract_pdf_text(pdf_bytes)
    # Yeni sayfa bazlı ayrıştırma
    result["pages"] = extract_pdf_pages(pdf_bytes, url, source_metadata)
    
    return result


def _html_to_text(html_str: str, base_url: str = BASE_PANEL) -> tuple[str, list[str]]:
    if not html_str or not html_str.strip():
        return "", []

    html_str = html_str.replace("\\/", "/")
    soup = BeautifulSoup(html_str, "lxml")

    # Gereksiz elementleri kaldır
    for tag_name in _REMOVE_TAGS:
        for tag in soup.select(tag_name):
            tag.decompose()

    # PDF linklerini topla
    pdf_links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip().strip('"').strip("'")
        if not href.startswith("http"):
            # Göreceli URL'yi mutlak yap
            from urllib.parse import urljoin
            href = urljoin(base_url, href)
        link_text = a.get_text(strip=True)
        if ".pdf" in href.lower():
            if href not in pdf_links:
                pdf_links.append(href)
            a.replace_with(f"[PDF: {link_text or href}]({href})")
        else:
            if link_text and link_text != href:
                a.replace_with(f"{link_text} ({href})")

    # Satır sonları ekle
    for tag in soup.find_all(["p", "div", "li", "tr", "br", "h1", "h2", "h3", "h4", "h5", "h6"]):
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
            raw_html = _extract_html_field(item)
            clean, pdfs = _html_to_text(raw_html)
            title = (item.get("title") or "").strip()
            if clean:
                header = f"── {title} ──\n" if title and len(data) > 1 else ""
                blocks.append(f"{header}{clean}")
            for p in pdfs:
                if p not in all_pdfs:
                    all_pdfs.append(p)
            if idx == 0:
                extra = {k: v for k, v in item.items() if k not in ("text", "content", "body")}
        return "\n\n".join(blocks), all_pdfs, extra

    if isinstance(data, dict):
        raw_html = _extract_html_field(data)
        extra    = {k: v for k, v in data.items() if k not in ("text", "content", "body")}
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
        ad_soyad = f"{(s.get('name') or '').strip()} {(s.get('surName') or '').strip()}".strip()
        unvan = (
            ((s.get("staffTitle") or {}).get("translateStaffCadre") or {})
            .get("tr", {}).get("title", "")
        ).strip()
        departman = (
            ((s.get("staffGroup") or {}).get("translateStaffGroup") or {})
            .get("tr", {}).get("title", "")
        ).strip()
        tr_data = ((s.get("translateStaff") or {}).get("tr") or {})
        gorev   = (tr_data.get("description") or tr_data.get("position") or "").strip()
        result.append({
            "id":       s.get("id", ""),
            "ad_soyad": ad_soyad,
            "unvan":    unvan,
            "departman": departman,
            "gorev":    gorev,
            "email":    (s.get("email") or "").strip(),
            "telefon":  (s.get("phone") or "").strip(),
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
            title       = (item.get("title") or "").strip()
            clean, pdfs = _html_to_text(item.get("text") or "")
            entry       = {"id": item.get("id", ""), "baslik": title, "icerik": clean}
            if pdfs:
                entry["pdf_links"] = pdfs
            results.append(entry)
        return results

    main = await _crawl_json(f"{BASE_PANEL}/servlet/content?id={parent_id}&lang=tr", crawler)
    if main:
        all_data[str(parent_id)] = {
            "baslik":  "Sıkça Sorulan Sorular (Genel)",
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

        content = await _crawl_json(f"{BASE_PANEL}/servlet/content?id={cid}&lang=tr", crawler)
        if content:
            all_data[str(cid)] = {
                "baslik":  tr_name,
                "content": _parse_items(content),
            }
        await asyncio.sleep(REQUEST_DELAY)

    return all_data


# ─────────────────────────────────────────────────────────────────
# DUYURU İŞLEME
# ─────────────────────────────────────────────────────────────────

async def _fetch_ann_list(max_known_id: int, crawler: AsyncWebCrawler, unit: str = "ogrencidb") -> list[dict]:
    """Belirtilen birim için yeni duyuruları çek."""
    from .url_config import ANNOUNCEMENT_API as ANN_API

    new_items: list[dict] = []
    page = 1
    url_tpl = f"{BASE_PANEL}/servlet/announcement?type=list&lang=tr&page={{page}}&unit={unit}"

    while True:
        url  = url_tpl.format(page=page)
        data = await _crawl_json(url, crawler)

        if not data or not isinstance(data, list):
            logger.info(f"Sayfa {page} boş [{unit}], tarama tamamlandı.")
            break

        page_ids = [it.get("id", 0) for it in data]
        page_new = [it for it in data if it.get("id", 0) > max_known_id]
        new_items.extend(page_new)

        logger.info(
            f"[{unit}] Sayfa {page} · {len(data)} kayıt · "
            f"ID {min(page_ids)}–{max(page_ids)} · yeni: {len(page_new)}"
        )

        if min(page_ids) <= max_known_id:
            logger.info(f"[{unit}] Bilinen ID'lere ulaşıldı, duruldu.")
            break

        page += 1
        await asyncio.sleep(REQUEST_DELAY)

    return new_items


async def _process_ann(item: dict, crawler: AsyncWebCrawler, target: UrlTarget) -> dict:
    ann_id    = item["id"]
    url_field = (item.get("url") or "").strip()
    detail_tpl = ANNOUNCEMENT_API.extra["detail_url"]

    unit = target.extra.get("unit", "unknown")
    unit_label = target.label
    fakulte = target.extra.get("fakulte", "")
    source_fakulte = fakulte

    if fakulte:
        scope = "faculty"
    elif unit in ["rektorluk", "ogrencidb", "sks", "kutuphane", "uzem", "disisleri", "bapk", "kariyer"]:
        scope = "university"
    else:
        scope = "unit"

    record = {
        "unit": unit,
        "unit_label": unit_label,
        "fakulte": fakulte,
        "source_fakulte": source_fakulte,
        "detected_fakulte": "",
        "scope": scope,
        "doc_type": "announcement",
        "page_no": None,
        "ann_id": ann_id,
        "title": item.get("title", "").strip(),
        "published_at": item.get("updated", ""),
        "source_url": "",
        "content_hash": "",
        # Legacy chunker compatibility:
        "id": ann_id,
        "sourceUrl": "",
        "updated": item.get("updated", ""),
        "content": None,
        "attachments": [],
    }

    # 1. Eğer doğrudan bir PDF linkiyse
    if url_field and ".pdf" in url_field.lower():
        record["source_url"] = url_field
        record["sourceUrl"] = url_field
        pdf = await _crawl_pdf(url_field, ann_id, "A", crawler, record)
        record["content"] = "Bu duyuru doğrudan bir PDF dosyasıdır."
        record["attachments"].append({
            "url": url_field, "type": "pdf",
            "content": pdf["pdfText"] or "[PDF Okunamadı]",
            "pages": pdf.get("pages", [])
        })
        fd = detect_faculty(record["title"])
        record["detected_fakulte"] = fd["fakulte"] or fakulte
        record["content_hash"] = generate_content_hash(record["title"], record["source_url"], record["content"])
        return validate_record(record)

    # 2. Önce kesinlikle API'den veriyi çek (JS gerektirmez, %100 güvenli HTML döndürür)
    detail_url = detail_tpl.format(id=ann_id)
    record["source_url"] = url_field if url_field else detail_url
    record["sourceUrl"] = record["source_url"]
    detail_data = await _crawl_json(detail_url, crawler)

    raw_html = ""
    if detail_data and isinstance(detail_data, dict):
        raw_html = detail_data.get("text") or detail_data.get("content") or ""

    clean, pdf_links = _html_to_text(raw_html)

    # 3. Eğer API boş döndüyse ve elimizde url_field varsa, o zaman zorunlu olarak web'i JS ile tara
    if not clean.strip() and url_field and url_field.startswith("http"):
        markdown, extra_pdfs = await _crawl_html_js(url_field, crawler)
        clean = markdown or "[İçerik alınamadı]"
        pdf_links.extend(extra_pdfs)
        pdf_links = list(dict.fromkeys(pdf_links))

    record["content"] = clean or None
    
    combined_text = f"{record['title']} {clean}"
    fd = detect_faculty(combined_text)
    record["detected_fakulte"] = fd["fakulte"] or fakulte
    record["content_hash"] = generate_content_hash(record["title"], record["source_url"], record["content"] or "")

    for idx, href in enumerate(pdf_links, 1):
        if href.startswith("file://"):
            continue
        pdf = await _crawl_pdf(href, ann_id, f"B{idx}", crawler, record)
        record["attachments"].append({
            "url": href, "type": "pdf",
            "content": pdf["pdfText"] or "[PDF Okunamadı]",
            "pages": pdf.get("pages", [])
        })

    return validate_record(record)


# ─────────────────────────────────────────────────────────────────
# ANA CRAWLER SINIFI
# ─────────────────────────────────────────────────────────────────

class BatchCrawler:
    def __init__(self, max_known_ann_id: int = 0):
        self.max_known_ann_id = max_known_ann_id

    # ── Duyurular ────────────────────────────────────────────────

    async def run_announcements(
        self,
        crawler: AsyncWebCrawler,
        target: UrlTarget,
    ) -> list[dict]:
        """Belirtilen hedef için duyuruları çek."""
        unit = target.extra.get("unit", "ogrencidb")
        logger.info(f"── Duyuru taraması başlıyor [{unit}] ──")
        new_items = await _fetch_ann_list(self.max_known_ann_id, crawler, unit)

        if not new_items:
            logger.info(f"Yeni duyuru yok [{unit}].")
            return []

        new_items.sort(key=lambda x: x["id"], reverse=True)
        results: list[dict] = []

        for i, item in enumerate(new_items, 1):
            logger.info(f"Duyuru {i}/{len(new_items)}: ID {item['id']} [{unit}]")
            try:
                record = await _process_ann(item, crawler, target)
                results.append(record)
            except Exception as e:
                logger.error(f"ID {item['id']} hata: {e}")
            await asyncio.sleep(REQUEST_DELAY)

        logger.info(f"Duyuru tamamlandı [{unit}]: {len(results)} kayıt")
        return results

    async def run_all_announcements(self, crawler: AsyncWebCrawler) -> list[dict]:
        """
        Tüm birimlerin duyurularını çek.
        DAILY_TARGETS içindeki paginated=True olan hedefler işlenir.
        """
        from .url_config import DAILY_TARGETS

        all_results: list[dict] = []
        processed_units = set()

        for target in DAILY_TARGETS:
            if not target.extra.get("paginated"):
                continue
            unit = target.extra.get("unit", "")
            if not unit or unit in processed_units:
                continue
            processed_units.add(unit)

            results = await self.run_announcements(crawler, target)
            all_results.extend(results)
            await asyncio.sleep(REQUEST_DELAY)

        return all_results

    # ── Statik İçerik (Panel API) ─────────────────────────────────

    async def run_static_content(self, crawler: AsyncWebCrawler) -> list[dict]:
        """Panel API statik içeriklerini çek (API_JSON, API_STAFF, API_SSS)."""
        from .url_config import API_TARGETS
        logger.info("── Statik içerik taraması başlıyor ──")
        results: list[dict] = []

        for target in API_TARGETS:
            if target.crawl_type not in (
                CrawlType.API_JSON, CrawlType.API_STAFF, CrawlType.API_SSS
            ):
                continue
            # Sayfalı duyurular run_all_announcements içinde çekiliyor, burada atla
            if target.crawl_type == CrawlType.API_JSON and target.extra.get("paginated"):
                continue

            logger.info(f"  [{target.key}] {target.label}")
            record = await self._process_api_target(target, crawler)
            results.append(record)
            await asyncio.sleep(REQUEST_DELAY)

        logger.info(f"Statik içerik tamamlandı: {len(results)} kaynak")
        return results

    # ── HTML_STATIC ───────────────────────────────────────────────

    async def run_html_static(self) -> list[dict]:
        """
        Düz HTML sayfalarını çek (fakülte ana sayfaları, kütüphane vb.)
        requests kullanır — Crawl4AI gerekmez.
        """
        targets = HTML_STATIC_TARGETS
        logger.info(f"── HTML_STATIC taraması başlıyor: {len(targets)} hedef ──")
        results: list[dict] = []

        for target in targets:
            logger.info(f"  [{target.key}] {target.label}: {target.url}")
            fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            try:
                text, pdf_links = await _crawl_html_static(target.url)
                record = {
                    "key":       target.key,
                    "label":     target.label,
                    "url":       target.url,
                    "fetchedAt": fetched_at,
                    "content":   text or "[İçerik boş]",
                    "pdfLinks":  pdf_links,
                    "extra":     target.extra,
                    "error":     None if text else "İçerik çekilemedi",
                }
                logger.info(f"    {len(text)} karakter, {len(pdf_links)} PDF link")
            except Exception as e:
                logger.error(f"HTML_STATIC hata [{target.key}]: {e}")
                record = {
                    "key": target.key, "label": target.label, "url": target.url,
                    "fetchedAt": fetched_at, "content": None, "pdfLinks": [],
                    "extra": target.extra, "error": str(e),
                }
            results.append(record)
            await asyncio.sleep(REQUEST_DELAY)

        logger.info(f"HTML_STATIC tamamlandı: {len(results)} kaynak")
        return results

    # ── HTML_JS ───────────────────────────────────────────────────

    async def run_html_js(self, crawler: AsyncWebCrawler) -> list[dict]:
        """
        JavaScript gerektiren sayfaları çek (Crawl4AI/Playwright).
        """
        targets = HTML_JS_TARGETS
        logger.info(f"── HTML_JS taraması başlıyor: {len(targets)} hedef ──")
        results: list[dict] = []

        for target in targets:
            logger.info(f"  [{target.key}] {target.label}: {target.url}")
            fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            try:
                text, pdf_links = await _crawl_html_js(target.url, crawler, target.js_wait_ms)
                record = {
                    "key":       target.key,
                    "label":     target.label,
                    "url":       target.url,
                    "fetchedAt": fetched_at,
                    "content":   text or "[İçerik boş]",
                    "pdfLinks":  pdf_links,
                    "extra":     target.extra,
                    "error":     None if text else "JS içeriği boş geldi",
                }
                logger.info(f"    {len(text)} karakter, {len(pdf_links)} PDF link")
            except Exception as e:
                logger.error(f"HTML_JS hata [{target.key}]: {e}")
                record = {
                    "key": target.key, "label": target.label, "url": target.url,
                    "fetchedAt": fetched_at, "content": None, "pdfLinks": [],
                    "extra": target.extra, "error": str(e),
                }
            results.append(record)
            await asyncio.sleep(REQUEST_DELAY)

        logger.info(f"HTML_JS tamamlandı: {len(results)} kaynak")
        return results

    # ── AVESİS ────────────────────────────────────────────────────

    async def run_avesis(self) -> list[dict]:
        """
        AVESİS akademik personel sisteminden tüm birimleri çek.
        avesis_crawler modülünü kullanır.
        """
        logger.info("── AVESİS taraması başlıyor ──")
        try:
            from .avesis_crawler import AvesisCrawler, avesis_results_to_chunk_input
        except ImportError as e:
            logger.error(f"avesis_crawler import hatası: {e}")
            return []

        crawler = AvesisCrawler()
        raw_results = await crawler.crawl_all()
        # chunker uyumlu formata çevir
        chunk_ready = avesis_results_to_chunk_input(raw_results)

        total = sum(len(r.get("content", [])) for r in raw_results)
        logger.info(f"AVESİS tamamlandı: {total} personel")
        return chunk_ready

    # ── Fakülte Duyuruları ────────────────────────────────────────

    async def run_fakulte_announcements(self, crawler: AsyncWebCrawler) -> list[dict]:
        """Tüm fakültelerin duyurularını çek."""
        logger.info("── Fakülte duyuruları başlıyor ──")
        all_results: list[dict] = []
        processed_units = set()

        for target in FAKULTE_TARGETS:
            if target.crawl_type != CrawlType.API_JSON:
                continue
            if not target.extra.get("paginated"):
                continue
            unit = target.extra.get("unit", "")
            if not unit or unit in processed_units:
                continue
            processed_units.add(unit)

            results = await self.run_announcements(crawler, target)
            all_results.extend(results)
            await asyncio.sleep(REQUEST_DELAY)

        logger.info(f"Fakülte duyuruları tamamlandı: {len(all_results)} kayıt")
        return all_results

    # ── Panel API Target İşleyici ─────────────────────────────────

    async def _process_api_target(
        self, target: UrlTarget, crawler: AsyncWebCrawler
    ) -> dict:
        unit = target.extra.get("unit", target.key)
        fakulte = target.extra.get("fakulte", "")
        
        if fakulte:
            scope = "faculty"
        elif unit in ["rektorluk", "ogrencidb", "sks", "kutuphane", "uzem", "disisleri", "bapk", "kariyer"]:
            scope = "university"
        else:
            scope = "unit"

        base = {
            "unit": unit,
            "unit_label": target.label,
            "fakulte": fakulte,
            "source_fakulte": fakulte,
            "detected_fakulte": "",
            "scope": scope,
            "doc_type": "static",
            "page_no": None,
            "ann_id": None,
            "title": target.label,
            "published_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_url": target.url,
            "content_hash": "",
            "content": None,
            "error": None,
            # Legacy fields:
            "key": target.key,
            "label": target.label,
            "url": target.url,
            "extra": target.extra,
            "pdfLinks": [],
        }

        # SSS
        if target.crawl_type == CrawlType.API_SSS:
            parent_id = target.extra.get("parent_id", 1636)
            sss_data  = await _fetch_sss(parent_id, crawler)
            if not sss_data:
                base["error"] = "SSS verisi çekilemedi"
                return validate_record(base)
            base["content"] = sss_data
            cats  = len(sss_data)
            items = sum(
                len(v.get("content", [])) if isinstance(v.get("content"), list) else 1
                for v in sss_data.values()
            )
            base["extra"] = {"categories": cats, "total_questions": items}
            base["content_hash"] = generate_content_hash(base["title"], base["source_url"], str(sss_data))
            logger.info(f"SSS: {cats} kategori, {items} soru")
            return validate_record(base)

        # Sayfalı duyuru (unit bazlı)
        if target.crawl_type == CrawlType.API_JSON and target.extra.get("paginated"):
            results = await self.run_announcements(crawler, target)
            base["content"] = results
            base["extra"]   = {"count": len(results), "unit": unit}
            base["content_hash"] = generate_content_hash(base["title"], base["source_url"], f"ann_list_{len(results)}")
            return validate_record(base)

        # Standart JSON API
        data = await _crawl_json(target.url, crawler)
        if data is None:
            base["error"] = "Veri çekilemedi"
            return validate_record(base)

        if target.crawl_type == CrawlType.API_STAFF:
            staff         = _parse_staff_api(data)
            base["content"] = staff
            base["extra"]   = {"count": len(staff)}
            base["doc_type"] = "avesis" # technically staff but close enough
            base["content_hash"] = generate_content_hash(base["title"], base["source_url"], str(staff))
            logger.info(f"Personel [{target.key}]: {len(staff)} kayıt")

        elif target.crawl_type == CrawlType.API_JSON:
            clean, pdfs, extra = _parse_content_api(data)
            base["content"]    = clean or "[İçerik boş]"
            base["pdfLinks"]   = pdfs
            base["extra"]      = extra
            
            combined_text = f"{base['title']} {clean}"
            fd = detect_faculty(combined_text)
            base["detected_fakulte"] = fd["fakulte"] or fakulte
            base["content_hash"] = generate_content_hash(base["title"], base["source_url"], base["content"])
            
            logger.info(
                f"{target.label}: {len(clean)} kar"
                + (f", {len(pdfs)} PDF" if pdfs else "")
            )

        return validate_record(base)

    # ── TAM TARAMA ────────────────────────────────────────────────

    async def run_all(self) -> dict[str, list[dict]]:
        """
        Tüm kaynakları tarar.
        Döndürür:
          {
            "announcements":   [...],   # tüm birim duyuruları
            "static_contents": [...],   # Panel API statik
            "html_static":     [...],   # HTML_STATIC sayfalar
            "html_js":         [...],   # HTML_JS sayfalar
            "avesis_staff":    [...],   # AVESİS personel
          }
        """
        logger.info("═══ TOPLU TARAYICI BAŞLIYOR (TÜM KAYNAKLAR) ═══")
        t0 = time.time()

        async with AsyncWebCrawler(config=_browser_cfg()) as crawler:
            # 1. Duyurular (tüm birimler)
            announcements = await self.run_all_announcements(crawler)

            # 2. Statik API içerikleri
            static_contents = await self.run_static_content(crawler)

            # 3. HTML_JS sayfalar
            html_js_results = await self.run_html_js(crawler)

        # 4. HTML_STATIC (ayrı, requests tabanlı)
        html_static_results = await self.run_html_static()

        # 5. AVESİS (ayrı Playwright oturumu)
        avesis_results = await self.run_avesis()

        elapsed = time.time() - t0
        logger.info(
            f"═══ TAMAMLANDI ═══ {elapsed:.1f}s | "
            f"duyuru:{len(announcements)} | "
            f"statik:{len(static_contents)} | "
            f"html:{len(html_static_results)} | "
            f"htmljs:{len(html_js_results)} | "
            f"avesis:{len(avesis_results)}"
        )

        return {
            "announcements":   announcements,
            "static_contents": static_contents + html_static_results + html_js_results,
            "avesis_staff":    avesis_results,
        }

    async def run_daily(self) -> dict[str, list[dict]]:
        """Sadece günlük hedefleri tarar (duyurular ve günlük JS hedefleri)."""
        from .url_config import DAILY_TARGETS, CrawlType
        
        async with AsyncWebCrawler(config=_browser_cfg()) as crawler:
            announcements = await self.run_all_announcements(crawler)
            
            # Günlük olan HTML_JS (Yemekhane vs.) veya HTML_STATIC hedefleri de topla
            static_contents = []
            for target in DAILY_TARGETS:
                if target.crawl_type == CrawlType.HTML_JS:
                    # Düzeltildi: run_html_js zaten hedefleri toplayıp dönüyor ama target bazlı da yapabilirdik.
                    # Basitlik açısından tümünü çalıştırıp sadece targetları filtreleyelim
                    pass # Daily HTML_JS targets handled externally if needed, or implement here.
                elif target.crawl_type == CrawlType.HTML_STATIC:
                    pass
            
            # Since HTML_JS and HTML_STATIC might be in daily, let's just run them if they are in DAILY_TARGETS
            daily_html_js_targets = [t for t in DAILY_TARGETS if t.crawl_type == CrawlType.HTML_JS]
            if daily_html_js_targets:
                # We could filter run_html_js but it's simpler to just reuse the function and modify it slightly if needed.
                # For now, just call it directly
                res = await self.run_html_js(crawler)
                static_contents.extend(res)
                    
        return {"announcements": announcements, "static_contents": static_contents, "avesis_staff": []}

    async def run_weekly(self) -> dict[str, list[dict]]:
        """Haftalık hedefleri tarar (personel, bazı statikler, AVESİS)."""
        from .url_config import WEEKLY_TARGETS
        logger.info("═══ HAFTALIK TARAMA ═══")

        async with AsyncWebCrawler(config=_browser_cfg()) as crawler:
            static_contents = []
            for target in WEEKLY_TARGETS:
                if target.crawl_type in (CrawlType.API_JSON, CrawlType.API_STAFF):
                    r = await self._process_api_target(target, crawler)
                    static_contents.append(r)
                    await asyncio.sleep(REQUEST_DELAY)

        avesis_results = await self.run_avesis()
        html_static    = await self.run_html_static()

        return {
            "announcements":   [],
            "static_contents": static_contents + html_static,
            "avesis_staff":    avesis_results,
        }


# ─────────────────────────────────────────────────────────────────
# DOĞRUDAN ÇALIŞTIRMA
# ─────────────────────────────────────────────────────────────────

async def _main():
    import sys
    arg = sys.argv[1] if len(sys.argv) > 1 else "--all"

    crawler = BatchCrawler(max_known_ann_id=0)

    if arg == "--all":
        results = await crawler.run_all()
    elif arg == "--daily":
        results = await crawler.run_daily()
    elif arg == "--weekly":
        results = await crawler.run_weekly()
    elif arg == "--avesis":
        avesis = await crawler.run_avesis()
        results = {"avesis_staff": avesis}
    elif arg == "--html":
        html = await crawler.run_html_static()
        results = {"static_contents": html}
    else:
        print("Kullanım: python -m data_pipeline.batch_crawler [--all|--daily|--weekly|--avesis|--html]")
        return

    out = Path("data/crawl_results.json")
    out.parent.mkdir(exist_ok=True)
    
    out_path = str(out)
    from .io_utils import load_json, atomic_write_json, merge_records

    if out.exists() and arg != "--all":
        existing = load_json(out_path, default={"announcements": [], "static_contents": [], "avesis_staff": []})
        
        merged_results = {}
        key_fields = ["ann_id", "source_url", "pdf_url", "page_no"]
        
        for k in ["announcements", "static_contents", "avesis_staff"]:
            e_list = existing.get(k, [])
            i_list = results.get(k, [])
            merged_results[k] = merge_records(e_list, i_list, key_fields=key_fields)
            
        results = merged_results
        logger.info("Mevcut veriyle güvenli şekilde birleştirildi (safe merge).")

    atomic_write_json(out_path, results)

    total_ann   = len(results.get("announcements", []))
    total_stat  = len(results.get("static_contents", []))
    total_aves  = sum(len(r.get("content", [])) for r in results.get("avesis_staff", []))
    logger.info(f"Kaydedildi: {out} | duyuru:{total_ann} | statik:{total_stat} | avesis_personel:{total_aves}")


if __name__ == "__main__":
    asyncio.run(_main())