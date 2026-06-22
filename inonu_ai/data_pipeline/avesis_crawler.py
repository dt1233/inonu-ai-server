#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔═════════════════════════════════════════════════════════════════╗
║ İNÖNÜ AI │ avesis_crawler.py                                   ║
║ AVESİS Akademik Personel Sistemi — Elasticsearch API Crawler    ║
║                                                                 ║
║ avesis.inonu.edu.tr Elasticsearch API'sine doğrudan istek atarak║
║ TÜM akademik personeli (Rektörlük, MYO, Enstitü dahil) çeker  ║
║ ve chunk'a hazır dict döndürür.                                 ║
╚═════════════════════════════════════════════════════════════════╝

Kullanım:
    from data_pipeline.avesis_crawler import AvesisCrawler
    crawler = AvesisCrawler()
    results = await crawler.crawl_all()   # tüm araştırmacılar
"""

import asyncio
import re
from datetime import datetime, timezone
from typing import Optional

import aiohttp
from loguru import logger

# ─────────────────────────────────────────────────────────────────
# SABİTLER
# ─────────────────────────────────────────────────────────────────

AVESIS_BASE      = "https://avesis.inonu.edu.tr"
ES_API_URL       = f"{AVESIS_BASE}/proxy/search/_search"
PROFILE_BASE     = AVESIS_BASE

PAGE_SIZE        = 100     # Elasticsearch'ten tek seferde çekilecek kayıt
MAX_RESULTS      = 10000   # Güvenlik sınırı (ES varsayılan max_result_window)
REQUEST_DELAY    = 0.3     # Saniye — API'ye nazik ol


# ─────────────────────────────────────────────────────────────────
# VERİ YAPISI
# ─────────────────────────────────────────────────────────────────

def _empty_person() -> dict:
    return {
        "ad_soyad":        "",
        "unvan":           "",
        "bolum":           "",
        "fakulte":         "",
        "anabilim_dali":   "",
        "email":           "",
        "telefon":         "",
        "cinsiyet":        "",
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


def _safe_str(val) -> str:
    """Değer list ise ilk elemanı, str ise kendisini döndür."""
    if isinstance(val, list):
        return val[0] if val else ""
    return str(val) if val else ""


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
    if p.get("anabilim_dali"):
        parts.append(f"Anabilim Dalı: {p['anabilim_dali']}")
    if p["email"]:
        parts.append(f"E-posta: {p['email']}")
    if p["telefon"]:
        parts.append(f"Tel: {p['telefon']}")
    if p.get("cinsiyet"):
        parts.append(f"Cinsiyet: {p['cinsiyet']}")
    if p["calisma_alanlari"]:
        alans = ", ".join(p["calisma_alanlari"][:5])  # max 5 alan
        parts.append(f"Çalışma Alanları: {alans}")
    if p["profil_url"]:
        parts.append(f"Profil: {p['profil_url']}")
    return " | ".join(filter(None, parts))


# ─────────────────────────────────────────────────────────────────
# ELASTICSEARCH API TABANLI CRAWLER
# ─────────────────────────────────────────────────────────────────

class AvesisCrawler:
    """
    AVESİS Elasticsearch API üzerinden TÜM akademik personeli çeker.

    Playwright yerine doğrudan /proxy/search/_search endpoint'ine
    HTTP POST istekleri atar. Sayfalama (from/size) ile tüm
    araştırmacıları döner.
    """

    HEADERS = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Referer": f"{AVESIS_BASE}/arama",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
    }

    def __init__(self, request_delay: float = REQUEST_DELAY):
        self.request_delay = request_delay

    # ── Ana metodlar ──────────────────────────────────────────────

    async def crawl_all(self, unit_list: Optional[list[tuple]] = None) -> list[dict]:
        """
        Tüm üniversite personelini Elasticsearch API üzerinden çeker.

        unit_list parametresi artık kullanılmıyor (geriye uyumluluk).
        API tek seferde tüm araştırmacıları döndürür, biz fakültelere
        göre grupluyoruz.

        Döndürür: batch_crawler ile uyumlu kayıt listesi
        [
          {
            "key":      "avesis_tum_personel",
            "label":    "AVESİS Tüm Akademik Personel",
            "url":      "https://avesis.inonu.edu.tr/proxy/search/_search",
            "fetchedAt": "...",
            "content":  [{"ad_soyad": ..., "unvan": ..., ...}, ...],
            "extra":    {"count": N, "fakulte_dagilimi": {...}},
            "error":    None,
          }
        ]
        """
        logger.info("═══ AVESİS ELASTİCSEARCH API TARAMASI BAŞLIYOR ═══")

        all_staff = []
        offset = 0
        total_count = None

        try:
            async with aiohttp.ClientSession(headers=self.HEADERS) as session:
                while True:
                    payload = self._build_query(offset=offset, size=PAGE_SIZE)
                    async with session.post(
                        ES_API_URL, json=payload, timeout=aiohttp.ClientTimeout(total=30)
                    ) as resp:
                        if resp.status != 200:
                            body = await resp.text()
                            logger.error(f"API hatası: HTTP {resp.status} — {body[:200]}")
                            break

                        data = await resp.json()

                    hits_obj = data.get("hits", {})
                    if total_count is None:
                        total_count = hits_obj.get("total", 0)
                        logger.info(f"Toplam araştırmacı: {total_count}")

                    hits = hits_obj.get("hits", [])
                    if not hits:
                        break

                    for hit in hits:
                        person = self._parse_hit(hit)
                        if person:
                            all_staff.append(person)

                    offset += len(hits)
                    logger.debug(f"  Sayfa {offset // PAGE_SIZE}: "
                                 f"{len(hits)} kayıt okundu (toplam: {offset}/{total_count})")

                    if offset >= total_count or offset >= MAX_RESULTS:
                        break

                    await asyncio.sleep(self.request_delay)

        except Exception as e:
            logger.error(f"AVESİS API hatası: {e}")
            return [{
                "key": "avesis_tum_personel",
                "label": "AVESİS Tüm Akademik Personel",
                "url": ES_API_URL,
                "fetchedAt": _now_iso(),
                "content": all_staff,
                "extra": {"count": len(all_staff), "error": str(e)},
                "error": str(e),
            }]

        # Fakülte dağılımını hesapla
        fakulte_dagilimi = {}
        for p in all_staff:
            fak = p.get("fakulte", "Bilinmiyor")
            fakulte_dagilimi[fak] = fakulte_dagilimi.get(fak, 0) + 1

        logger.info(f"═══ AVESİS TAMAMLANDI: {len(all_staff)} personel ═══")
        for fak, cnt in sorted(fakulte_dagilimi.items(), key=lambda x: -x[1]):
            logger.info(f"  {fak}: {cnt} kişi")

        # Tek bir kayıt olarak döndür (fakülte bazlı gruplama gerekirse
        # batch_crawler tarafında yapılabilir)
        return [{
            "key": "avesis_tum_personel",
            "label": "AVESİS Tüm Akademik Personel",
            "url": ES_API_URL,
            "fetchedAt": _now_iso(),
            "content": all_staff,
            "extra": {
                "count": len(all_staff),
                "fakulte_dagilimi": fakulte_dagilimi,
            },
            "error": None,
        }]

    # ── Elasticsearch sorgusu oluştur ─────────────────────────────

    @staticmethod
    def _build_query(offset: int = 0, size: int = PAGE_SIZE) -> dict:
        """
        Sadece 'Araştırmacılar' tipindeki kayıtları döndüren
        Elasticsearch sorgusu.
        """
        return {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"isdeleted": "false"}},
                        {"term": {"type_primary.keyword": "Araştırmacılar"}},
                    ]
                }
            },
            "size": size,
            "from": offset,
        }

    # ── Tek hit'i personel dict'e dönüştür ───────────────────────

    @staticmethod
    def _parse_hit(hit: dict) -> Optional[dict]:
        """
        Elasticsearch _source nesnesini iç veri yapısına dönüştür.

        API'den gelen alanlar:
          name, surname, fullnamewithtitle_primary,
          title_primary (unvan), subtype_primary (kadro),
          facultyname_primary (fakülte listesi),
          departmentname_primary (bölüm listesi),
          programname_primary (anabilim dalı listesi),
          reference_primary (referans dict),
          profilepagealias, id, gendername_primary
        """
        src = hit.get("_source", {})
        if not src:
            return None

        p = _empty_person()

        # İsim-Soyisim
        name = _clean(src.get("name", ""))
        surname = _clean(src.get("surname", ""))
        if name and surname:
            p["ad_soyad"] = f"{name} {surname}"
        elif src.get("fullnamewithtitle_primary"):
            # Unvansız isim al
            full = _clean(src["fullnamewithtitle_primary"])
            # Unvanı çıkart
            title = _clean(src.get("title_primary", ""))
            if title and full.startswith(title):
                p["ad_soyad"] = full[len(title):].strip()
            else:
                p["ad_soyad"] = full

        if not p["ad_soyad"]:
            return None  # İsimsiz kayıtları atla

        # Unvan
        p["unvan"] = _clean(src.get("title_primary", ""))

        # Fakülte (liste olarak geliyor)
        p["fakulte"] = _safe_str(src.get("facultyname_primary", ""))

        # Bölüm
        p["bolum"] = _safe_str(src.get("departmentname_primary", ""))

        # Anabilim Dalı
        p["anabilim_dali"] = _safe_str(src.get("programname_primary", ""))

        # Cinsiyet
        p["cinsiyet"] = _clean(src.get("gendername_primary", ""))

        # Profil URL ve ID
        avesis_id = src.get("id", "")
        alias = src.get("profilepagealias", "")
        if alias:
            p["profil_url"] = f"{PROFILE_BASE}/{alias}"
        elif avesis_id:
            p["profil_url"] = f"{PROFILE_BASE}/user/{avesis_id}"

        p["avesis_id"] = str(avesis_id) if avesis_id else ""

        return p


# ─────────────────────────────────────────────────────────────────
# BATCH CRAWLER ENTEGRASYON ARAYÜZÜ
# batch_crawler.py'nin run_all() ile uyumlu çıktı formatı
# ─────────────────────────────────────────────────────────────────

async def crawl_avesis_all() -> list[dict]:
    """
    batch_crawler.run_all() ile aynı formatı döndürür.
    crawler_results["avesis_staff"] listesine eklenir.
    """
    crawler = AvesisCrawler()
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
        crawler = AvesisCrawler()
        results = await crawler.crawl_all()

        out = Path("data/avesis_results.json")
        out.parent.mkdir(exist_ok=True)
        out.write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        total = sum(len(r.get("content", [])) for r in results)
        logger.info(f"{total} personel cekildi")
        logger.info(f"Kaydedildi: {out}")

    asyncio.run(main())