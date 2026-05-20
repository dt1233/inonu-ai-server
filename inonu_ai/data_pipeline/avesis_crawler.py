#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔═════════════════════════════════════════════════════════════════╗
║ İNÖNÜ AI │ avesis_crawler.py                                   ║
║ AVESİS Akademik Personel Sistemi — Toplu Kazıyıcı              ║
║                                                                 ║
║ avesis.inonu.edu.tr sayfalarını Playwright ile tarar,          ║
║ tüm akademik personeli çeker ve chunk'a hazır dict döndürür.   ║
╚═════════════════════════════════════════════════════════════════╝

Kullanım:
    from data_pipeline.avesis_crawler import AvesisCrawler
    crawler = AvesisCrawler()
    results = await crawler.crawl_all()   # tüm fakülteler
    # ya da tek fakülte:
    results = await crawler.crawl_unit(unit_id=3, label="Mühendislik")
"""

import asyncio
import re
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

# ─────────────────────────────────────────────────────────────────
# SABITLER
# ─────────────────────────────────────────────────────────────────

AVESIS_BASE      = "https://avesis.inonu.edu.tr"
UNIT_REPORT_URL  = f"{AVESIS_BASE}/unitreport/reports?unitId={{unit_id}}"
RESEARCHER_TAB   = f"{AVESIS_BASE}/unitreport/researchers?unitId={{unit_id}}"
PROFILE_BASE     = f"{AVESIS_BASE}"

REQUEST_DELAY    = 1.2   # saniye — AVESİS'e nazik ol
PAGE_TIMEOUT_MS  = 30000
JS_WAIT_MS       = 3000  # Araştırmacılar sekmesi yüklenmesi için


# ─────────────────────────────────────────────────────────────────
# VERİ YAPISI
# ─────────────────────────────────────────────────────────────────

def _empty_person() -> dict:
    return {
        "ad_soyad":        "",
        "unvan":           "",
        "bolum":           "",
        "fakulte":         "",
        "email":           "",
        "telefon":         "",
        "calisma_alanlari": [],
        "profil_url":      "",
        "avesis_id":       "",
        "unit_id":         None,
    }


# ─────────────────────────────────────────────────────────────────
# YARDIMCI FONKSİYONLAR
# ─────────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    """Metni temizle: fazla boşluk, görünmez karakter."""
    if not text:
        return ""
    text = re.sub(r"[\u200b\u200c\u200d\u00a0\ufeff]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_email(text: str) -> str:
    """Metinden e-posta adresini ayıkla."""
    match = re.search(r"[\w.+-]+@[\w.-]+\.\w+", text)
    return match.group(0).lower() if match else ""


def _parse_phone(text: str) -> str:
    """Metinden telefon numarasını ayıkla."""
    match = re.search(r"(\+90[\s\-]?)?(\(?\d{3,4}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2})", text)
    return match.group(0).strip() if match else ""


def _person_to_chunk_text(p: dict) -> str:
    """
    Personel dict'ini Qdrant'a yazılacak metin formatına dönüştür.
    Chunker bu metni alıp chunk'lar.
    """
    parts = []
    if p["ad_soyad"]:
        parts.append(p["ad_soyad"])
    if p["unvan"]:
        parts.append(p["unvan"])
    if p["bolum"]:
        parts.append(f"Bölüm: {p['bolum']}")
    if p["fakulte"]:
        parts.append(f"Fakülte: {p['fakulte']}")
    if p["email"]:
        parts.append(f"E-posta: {p['email']}")
    if p["telefon"]:
        parts.append(f"Tel: {p['telefon']}")
    if p["calisma_alanlari"]:
        alans = ", ".join(p["calisma_alanlari"][:5])  # max 5 alan
        parts.append(f"Çalışma Alanları: {alans}")
    if p["profil_url"]:
        parts.append(f"Profil: {p['profil_url']}")
    return " | ".join(filter(None, parts))


# ─────────────────────────────────────────────────────────────────
# PLAYWRIGHT TABANLI CRAWLER
# ─────────────────────────────────────────────────────────────────

class AvesisCrawler:
    """
    AVESİS'ten akademik personel bilgilerini çeker.

    Önce /unitreport/researchers endpoint'ini dener (sayfalı tablo),
    başarısız olursa /unitreport/reports sayfasını tarar.
    """

    def __init__(self, headless: bool = True, request_delay: float = REQUEST_DELAY):
        self.headless      = headless
        self.request_delay = request_delay

    # ── Ana metodlar ──────────────────────────────────────────────

    async def crawl_all(self, unit_list: Optional[list[tuple]] = None) -> list[dict]:
        """
        Tüm birimlerin personelini çeker.

        unit_list: [(unit_id, label, fakulte_adi), ...]
                   None ise url_config'den AVESIS_TARGETS kullanılır.

        Döndürür: batch_crawler ile uyumlu kayıt listesi
        [
          {
            "key":      "muhendislik_avesis",
            "label":    "Mühendislik Fakültesi AVESİS Akademik Kadro",
            "url":      "https://avesis...",
            "fetchedAt": "...",
            "content":  [{"ad_soyad": ..., "unvan": ..., ...}, ...],
            "extra":    {"count": N, "unit_id": X},
            "error":    None,
          },
          ...
        ]
        """
        if unit_list is None:
            from .url_config import AVESIS_TARGETS
            unit_list = [
                (t.extra["unit_id"], t.label, t.extra.get("fakulte", ""), t.key, t.url)
                for t in AVESIS_TARGETS
            ]

        logger.info(f"═══ AVESİS TARAMASI BAŞLIYOR: {len(unit_list)} birim ═══")
        all_results = []

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright yüklü değil. Çalıştır: pip install playwright && playwright install chromium")
            return []

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=self.headless,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (compatible; InönüAI-Bot/1.0)",
                locale="tr-TR",
            )

            for item in unit_list:
                # unit_list hem 3'lü hem 5'li tuple destekli
                if len(item) == 5:
                    unit_id, label, fakulte, key, url = item
                elif len(item) == 3:
                    unit_id, label, fakulte = item
                    key = f"avesis_{unit_id}"
                    url = UNIT_REPORT_URL.format(unit_id=unit_id)
                else:
                    logger.warning(f"Geçersiz unit_list öğesi: {item}")
                    continue

                try:
                    record = await self._crawl_unit_with_context(
                        context, unit_id, label, fakulte, key, url
                    )
                    all_results.append(record)
                    logger.info(
                        f"✓ {label}: {len(record['content'])} personel"
                        if record["content"]
                        else f"✗ {label}: hata — {record['error']}"
                    )
                except Exception as e:
                    logger.error(f"AVESİS birim hatası [{label}]: {e}")
                    all_results.append({
                        "key": key, "label": label, "url": url,
                        "fetchedAt": _now_iso(),
                        "content": [], "extra": {"count": 0, "unit_id": unit_id},
                        "error": str(e),
                    })

                await asyncio.sleep(self.request_delay)

            await context.close()
            await browser.close()

        total = sum(len(r["content"]) for r in all_results)
        logger.info(f"═══ AVESİS TAMAMLANDI: {total} personel, {len(all_results)} birim ═══")
        return all_results

    async def crawl_unit(
        self,
        unit_id: int,
        label: str,
        fakulte: str = "",
        key: str = "",
        url: str = "",
    ) -> dict:
        """Tek birim için kısayol."""
        if not url:
            url = UNIT_REPORT_URL.format(unit_id=unit_id)
        if not key:
            key = f"avesis_{unit_id}"

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright yüklü değil.")
            return {"key": key, "label": label, "url": url,
                    "fetchedAt": _now_iso(), "content": [], "extra": {}, "error": "playwright eksik"}

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self.headless)
            context = await browser.new_context(locale="tr-TR")
            record = await self._crawl_unit_with_context(context, unit_id, label, fakulte, key, url)
            await context.close()
            await browser.close()
        return record

    # ── İç metodlar ───────────────────────────────────────────────

    async def _crawl_unit_with_context(
        self,
        context,
        unit_id: int,
        label: str,
        fakulte: str,
        key: str,
        url: str,
    ) -> dict:
        """
        Birim personellerini yeni AVESİS Arama sayfasını kullanarak çeker.
        """
        fetched_at = _now_iso()
        base_record = {
            "key":       key,
            "label":     label,
            "url":       url,
            "fetchedAt": fetched_at,
            "content":   [],
            "extra":     {"count": 0, "unit_id": unit_id, "fakulte": fakulte},
            "error":     None,
        }

        staff = await self._search_researchers(context, label, fakulte, unit_id)

        if not staff:
            base_record["error"] = "Personel çekilemedi (Arama sayfası başarısız veya boş)"
            return base_record

        base_record["content"] = staff
        base_record["extra"]["count"] = len(staff)
        return base_record

    async def _search_researchers(
        self, context, label: str, fakulte: str, unit_id: int
    ) -> list[dict]:
        """
        AVESİS arama sayfasını (arama?aranan=Fakülte Adı) kullanarak
        Araştırmacılar sekmesindeki tüm personeli çeker.
        """
        import urllib.parse
        search_term = urllib.parse.quote(fakulte or label)
        url = f"https://avesis.inonu.edu.tr/arama?aranan={search_term}"
        
        page = await context.new_page()
        staff: list[dict] = []

        try:
            await page.goto(url, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
            await page.wait_for_timeout(JS_WAIT_MS)

            # "Araştırmacılar" filtresine tıkla (Eğer varsa)
            arastirmacilar_btn = page.locator("a:has-text('Araştırmacılar')").first
            if await arastirmacilar_btn.count() > 0:
                await arastirmacilar_btn.click()
                await page.wait_for_timeout(JS_WAIT_MS)
            
            # Sayfalama döngüsü
            page_num = 1
            while True:
                page_staff = await self._parse_html_researchers_table(page, label, fakulte, unit_id)
                
                # Mükerrer kayıtları engellemek için url veya isim kontrolü
                new_staff = []
                for p in page_staff:
                    if not any(s["ad_soyad"] == p["ad_soyad"] for s in staff):
                        new_staff.append(p)
                
                if not new_staff:
                    break
                    
                staff.extend(new_staff)
                logger.debug(f"  Sayfa {page_num}: {len(new_staff)} kişi eklendi [{label}]")

                # Sonraki sayfa butonuna tıkla
                next_btn = page.locator(".pagination .sk-toggle__item:not(.is-disabled):has-text('›')").first
                if await next_btn.count() == 0:
                    next_btn = page.locator("a[aria-label='Next'], li.next:not(.disabled) a").first

                try:
                    if await next_btn.count() > 0 and await next_btn.is_enabled():
                        await next_btn.click()
                        await page.wait_for_timeout(1500)
                        page_num += 1
                    else:
                        break
                except Exception:
                    break

                if page_num > 50:
                    break

        except Exception as e:
            logger.debug(f"Arama sayfası başarısız [{label}]: {e}")
        finally:
            await page.close()

        return staff

    async def _parse_html_researchers_table(
        self, page, label: str, fakulte: str, unit_id: int
    ) -> list[dict]:
        """
        Sayfadaki personel tablosunu veya listesini parse et.
        AVESİS farklı sayfalarda farklı yapılar kullanıyor.
        """
        staff: list[dict] = []

        # Strateji A: <table> içindeki satırlar
        rows = await page.query_selector_all("table tbody tr")
        if rows:
            for row in rows:
                p = await self._parse_table_row(row, label, fakulte, unit_id)
                if p and p["ad_soyad"]:
                    staff.append(p)
            if staff:
                return staff

        # Strateji B: Kart yapısı (.card, .researcher-card vb.)
        cards = await page.query_selector_all(
            ".researcher-title a, .researcher-card, .staff-card, .person-card, "
            ".card:has(.card-title), [class*='researcher']"
        )
        if cards:
            for card in cards:
                p = await self._parse_card(card, label, fakulte, unit_id)
                if p and p["ad_soyad"]:
                    staff.append(p)
            if staff:
                return staff

        # Strateji C: Liste elemanları
        items = await page.query_selector_all(
            "ul.researcher-list li, "
            ".staff-list li, "
            "[class*='staff'] li"
        )
        if items:
            for item in items:
                p = await self._parse_list_item(item, label, fakulte, unit_id)
                if p and p["ad_soyad"]:
                    staff.append(p)

        return staff

    async def _parse_table_row(self, row, label: str, fakulte: str, unit_id: int) -> Optional[dict]:
        """<tr> satırından personel bilgisi çıkar."""
        try:
            cells = await row.query_selector_all("td")
            if len(cells) < 2:
                return None

            p = _empty_person()
            p["unit_id"] = unit_id
            p["fakulte"] = fakulte

            # Hücrelerden metni al
            cell_texts = []
            for cell in cells:
                t = _clean(await cell.inner_text())
                cell_texts.append(t)

            if not cell_texts[0]:
                return None

            # İlk hücre genellikle ad-soyad veya bağlantı
            link = await cells[0].query_selector("a")
            if link:
                p["ad_soyad"] = _clean(await link.inner_text())
                href = await link.get_attribute("href") or ""
                if href:
                    p["profil_url"] = href if href.startswith("http") else PROFILE_BASE + href
                    # AVESİS ID URL'den çıkar: /author/12345
                    m = re.search(r"/author/(\d+)", href)
                    if m:
                        p["avesis_id"] = m.group(1)
            else:
                p["ad_soyad"] = cell_texts[0]

            # Diğer hücreler
            for i, text in enumerate(cell_texts[1:], 1):
                if not text:
                    continue
                text_lower = text.lower()
                # Unvan tespiti
                if any(u in text_lower for u in [
                    "prof.", "doç.", "dr.", "öğr.", "arş.", "uzm.", "yrd."
                ]):
                    p["unvan"] = text
                elif "@" in text:
                    p["email"] = _parse_email(text)
                elif re.search(r"\d{3}", text):
                    p["telefon"] = _parse_phone(text)
                elif not p["bolum"]:
                    p["bolum"] = text

            return p if p["ad_soyad"] else None

        except Exception as e:
            logger.debug(f"Tablo satırı parse hatası: {e}")
            return None

    async def _parse_card(self, card, label: str, fakulte: str, unit_id: int) -> Optional[dict]:
        """Kart elemanından personel bilgisi çıkar."""
        try:
            p = _empty_person()
            p["unit_id"] = unit_id
            p["fakulte"] = fakulte

            full_text = _clean(await card.inner_text())
            if not full_text:
                return None

            # Başlık / ad-soyad
            for sel in [".card-title", "h5", "h4", "h3", ".name", "[class*='name']"]:
                el = await card.query_selector(sel)
                if el:
                    p["ad_soyad"] = _clean(await el.inner_text())
                    break

            if not p["ad_soyad"]:
                # İlk satırı ad-soyad kabul et
                lines = [l.strip() for l in full_text.split("\n") if l.strip()]
                if lines:
                    p["ad_soyad"] = lines[0]

            # Profil linki veya AVESIS ID
            link = await card.query_selector("a")
            if link:
                href = await link.get_attribute("href") or ""
                if href and href != "#":
                    p["profil_url"] = href if href.startswith("http") else PROFILE_BASE + href
                    m = re.search(r"/author/(\d+)", href)
                    if m:
                        p["avesis_id"] = m.group(1)
                
                # Yeni Arama Sayfası Yapısı (Searchkit)
                network_id = await link.get_attribute("data-networkuserid")
                if network_id:
                    p["profil_url"] = f"https://avesis.inonu.edu.tr/{network_id}" # Geçici profil URL'si

            # Arama sayfasında ID genellikle img etiketinin içinde id=XXX olarak bulunur
            if not p["avesis_id"]:
                img = await card.query_selector("img.researcher-img, img[src*='user/image']")
                if img:
                    src = await img.get_attribute("src") or ""
                    m = re.search(r"id=(\d+)", src)
                    if m:
                        p["avesis_id"] = m.group(1)
                        p["profil_url"] = f"https://avesis.inonu.edu.tr/profil/{p['avesis_id']}"

            # E-posta
            p["email"] = _parse_email(full_text)

            # Unvan
            for unvan_kw in ["Prof. Dr.", "Doç. Dr.", "Dr. Öğr. Üyesi",
                             "Arş. Gör. Dr.", "Arş. Gör.", "Öğr. Gör. Dr.",
                             "Öğr. Gör.", "Uzm. Dr.", "Uzm."]:
                if unvan_kw.lower() in full_text.lower():
                    p["unvan"] = unvan_kw
                    break

            # Bölüm
            for sel in [".department", ".bolum", "[class*='department']", ".card-subtitle"]:
                el = await card.query_selector(sel)
                if el:
                    p["bolum"] = _clean(await el.inner_text())
                    break

            return p if p["ad_soyad"] else None

        except Exception as e:
            logger.debug(f"Kart parse hatası: {e}")
            return None

    async def _parse_list_item(self, item, label: str, fakulte: str, unit_id: int) -> Optional[dict]:
        """Liste elemanından personel bilgisi çıkar."""
        try:
            p = _empty_person()
            p["unit_id"] = unit_id
            p["fakulte"] = fakulte

            full_text = _clean(await item.inner_text())
            if not full_text:
                return None

            link = await item.query_selector("a")
            if link:
                p["ad_soyad"] = _clean(await link.inner_text())
                href = await link.get_attribute("href") or ""
                if href:
                    p["profil_url"] = href if href.startswith("http") else PROFILE_BASE + href
            else:
                p["ad_soyad"] = full_text.split("\n")[0].strip()

            p["email"] = _parse_email(full_text)
            return p if p["ad_soyad"] else None

        except Exception as e:
            logger.debug(f"Liste öğesi parse hatası: {e}")
            return None

    def _parse_json_researchers(
        self, data, label: str, fakulte: str, unit_id: int
    ) -> list[dict]:
        """JSON formatındaki araştırmacı listesini parse et."""
        staff: list[dict] = []
        if not isinstance(data, list):
            data = data.get("data", data.get("researchers", data.get("content", [])))
        if not isinstance(data, list):
            return []

        for item in data:
            if not isinstance(item, dict):
                continue
            p = _empty_person()
            p["unit_id"] = unit_id
            p["fakulte"] = fakulte

            # AVESİS JSON alan isimleri (birden fazla olabilir)
            p["ad_soyad"] = _clean(
                item.get("fullName") or
                item.get("name") or
                f"{item.get('firstName','')} {item.get('lastName','')}".strip()
            )
            p["unvan"]  = _clean(item.get("title") or item.get("academicTitle") or "")
            p["bolum"]  = _clean(item.get("department") or item.get("unit") or "")
            p["email"]  = _clean(item.get("email") or "")
            p["telefon"] = _clean(item.get("phone") or item.get("tel") or "")

            aid = item.get("authorId") or item.get("id") or ""
            if aid:
                p["avesis_id"] = str(aid)
                p["profil_url"] = f"{PROFILE_BASE}/author/{aid}"

            if isinstance(item.get("researchAreas"), list):
                p["calisma_alanlari"] = [
                    _clean(a.get("name", a) if isinstance(a, dict) else a)
                    for a in item["researchAreas"][:10]
                ]

            if p["ad_soyad"]:
                staff.append(p)

        return staff


# ─────────────────────────────────────────────────────────────────
# BATCH CRAWLER ENTEGRASYON ARAYÜZÜ
# batch_crawler.py'nin run_all() ile uyumlu çıktı formatı
# ─────────────────────────────────────────────────────────────────

async def crawl_avesis_all() -> list[dict]:
    """
    batch_crawler.run_all() ile aynı formatı döndürür.
    crawler_results["avesis_staff"] listesine eklenir.
    """
    crawler = AvecisCrawler()
    return await crawler.crawl_all()


def avesis_results_to_chunk_input(avesis_records: list[dict]) -> list[dict]:
    """
    AVESİS sonuçlarını chunker.chunk_static_contents() ile
    uyumlu formata dönüştürür.

    Çıktı chunker'ın beklediği:
      {"key": ..., "label": ..., "url": ..., "content": [staff_list]}
    """
    chunk_inputs = []
    for rec in avesis_records:
        if not rec.get("content"):
            continue
        # content: list[dict] → chunker _staff_to_text ile işler
        chunk_inputs.append({
            "key":      rec["key"],
            "label":    rec["label"],
            "url":      rec["url"],
            "fetchedAt": rec["fetchedAt"],
            "content":  rec["content"],  # list[dict] — personel listesi
            "pdfLinks": [],
            "extra":    rec.get("extra", {}),
        })
    return chunk_inputs


# ─────────────────────────────────────────────────────────────────
# YARDIMCI
# ─────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─────────────────────────────────────────────────────────────────
# DOĞRUDAN ÇALIŞTIRMA
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    async def main():
        arg = sys.argv[1] if len(sys.argv) > 1 else "--all"

        if arg == "--all":
            crawler = AvecisCrawler(headless=True)
            results = await crawler.crawl_all()
        elif arg == "--unit" and len(sys.argv) >= 4:
            unit_id = int(sys.argv[2])
            label   = sys.argv[3]
            crawler = AvecisCrawler(headless=False)  # debug için görünür
            results = [await crawler.crawl_unit(unit_id, label)]
        else:
            print("Kullanım:")
            print("  python -m data_pipeline.avesis_crawler --all")
            print("  python -m data_pipeline.avesis_crawler --unit 3 'Mühendislik'")
            return

        out = Path("avesis_results.json")
        out.write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        total = sum(len(r.get("content", [])) for r in results)
        print(f"\n✓ {total} personel çekildi, {len(results)} birim")
        print(f"✓ Kaydedildi: {out}")

    asyncio.run(main())