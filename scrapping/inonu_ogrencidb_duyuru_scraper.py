#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║        İNÖNÜ ÜNİVERSİTESİ DUYURU SCRAPER                         ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝

Kullanım:
    python inonu_scraper.py

Gereksinimler (pip install):
    requests pypdf beautifulsoup4 lxml

Opsiyonel (daha iyi PDF desteği):
    pip install pdfminer.six
"""

import io
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────────────────────────
# BÖLÜM 0 │ Terminal renk & loglama yardımcıları
# ─────────────────────────────────────────────────────────────────

class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN    = "\033[96m"
    WHITE   = "\033[97m"

_ICONS = {
    "INFO":    f"{C.BLUE}[ℹ]{C.RESET}",
    "OK":      f"{C.GREEN}[✔]{C.RESET}",
    "WARN":    f"{C.YELLOW}[⚠]{C.RESET}",
    "ERROR":   f"{C.RED}[✘]{C.RESET}",
    "FETCH":   f"{C.MAGENTA}[↓]{C.RESET}",
    "NEW":     f"{C.GREEN}[★]{C.RESET}",
    "PDF":     f"{C.CYAN}[📄]{C.RESET}",
    "SKIP":    f"{C.DIM}[→]{C.RESET}",
    "STOP":    f"{C.RED}[■]{C.RESET}",
}

def log(level: str, msg: str) -> None:
    ts   = datetime.now().strftime("%H:%M:%S")
    icon = _ICONS.get(level, "[?]")
    print(f"  {C.DIM}{ts}{C.RESET}  {icon}  {msg}")

def section(title: str) -> None:
    pad = (58 - len(title)) // 2
    print()
    print(f"  {C.CYAN}{'─' * pad} {C.BOLD}{title}{C.RESET}{C.CYAN} {'─' * pad}{C.RESET}")
    print()

def progress_bar(current: int, total: int, prefix: str = "", width: int = 32) -> None:
    pct    = int(current / max(total, 1) * 100)
    filled = int(width * current / max(total, 1))
    bar    = f"{C.GREEN}{'█' * filled}{C.DIM}{'░' * (width - filled)}{C.RESET}"
    sys.stdout.write(f"\r  {C.DIM}{prefix:<14}{C.RESET} [{bar}] {C.BOLD}{pct:3d}%{C.RESET} ({current}/{total})  ")
    sys.stdout.flush()
    if current >= total:
        print()

def banner() -> None:
    lines = [
        "",
        f"{C.CYAN}{C.BOLD}  ╔══════════════════════════════════════════════════════════════════╗{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║    {C.WHITE}██╗███╗   ██╗ ██████╗ ███╗   ██╗██╗   ██╗{C.CYAN}                    ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║    {C.WHITE}██║████╗  ██║██╔═══██╗████╗  ██║██║   ██║{C.CYAN}                    ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║    {C.WHITE}██║██╔██╗ ██║██║   ██║██╔██╗ ██║██║   ██║{C.CYAN}                    ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║    {C.WHITE}██║██║╚██╗██║██║   ██║██║╚██╗██║██║   ██║{C.CYAN}                    ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║    {C.WHITE}██║██║ ╚████║╚██████╔╝██║ ╚████║╚██████╔╝{C.CYAN}                    ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║    {C.DIM}╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═══╝ ╚═════╝ {C.CYAN}                   ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║                                                                  ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║    {C.YELLOW}mert ege sungur  {C.GREEN}meges.com.tr{C.CYAN}                      ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║    {C.DIM}İnönü Üniversitesi Öğrenci DB Scraper{C.CYAN}            ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ╚══════════════════════════════════════════════════════════════════╝{C.RESET}",
        "",
    ]
    for line in lines:
        print(line)


# ─────────────────────────────────────────────────────────────────
# BÖLÜM 1 │ Konfigürasyon
# ─────────────────────────────────────────────────────────────────

URL_LIST   = "https://panel.inonu.edu.tr/servlet/announcement?type=list&lang=tr&page={page}&unit=ogrencidb"
URL_DETAIL = "https://panel.inonu.edu.tr/servlet/announcement?type=get&lang=tr&id={id}"
BASE_URL   = "https://panel.inonu.edu.tr"

DATA_FILE   = "duyurular.json"
OUTPUT_FILE = "yeni_duyurular.json"
PDF_DIR     = "pdf_belgeler"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36 "
        "MegeSolutions-Bot/2.0"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}
REQUEST_DELAY   = 0.5 
REQUEST_TIMEOUT = 20  


# ─────────────────────────────────────────────────────────────────
# BÖLÜM 2 │ HTTP yardımcısı
# ─────────────────────────────────────────────────────────────────

def http_get(url: str, stream: bool = False) -> Optional[requests.Response]:
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            stream=stream,
            allow_redirects=True,
        )
        response.raise_for_status()
        return response
    except requests.exceptions.Timeout:
        log("ERROR", f"Zaman aşımı: {C.YELLOW}{url[:80]}{C.RESET}")
    except requests.exceptions.HTTPError as e:
        log("ERROR", f"HTTP {e.response.status_code}: {C.YELLOW}{url[:80]}{C.RESET}")
    except requests.exceptions.ConnectionError:
        log("ERROR", f"Bağlantı hatası: {C.YELLOW}{url[:80]}{C.RESET}")
    except requests.exceptions.RequestException as e:
        log("ERROR", f"İstek hatası: {e}")
    return None


# ─────────────────────────────────────────────────────────────────
# BÖLÜM 3 │ Veritabanı işlemleri
# ─────────────────────────────────────────────────────────────────

def load_database() -> tuple[dict[int, dict], int]:
    path = Path(DATA_FILE)
    if not path.exists():
        log("WARN", f"Veritabanı bulunamadı ({C.YELLOW}{DATA_FILE}{C.RESET}). İlk çalıştırma kabul edildi.")
        return {}, 0

    with open(path, encoding="utf-8") as f:
        records: list[dict] = json.load(f)

    db = {rec["id"]: rec for rec in records}
    max_id = max(db.keys(), default=0)
    return db, max_id

def save_database(db: dict[int, dict]) -> None:
    sorted_records = sorted(db.values(), key=lambda r: r["id"], reverse=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted_records, f, ensure_ascii=False, indent=2)
    log("OK", f"Veritabanı güncellendi → {C.GREEN}{DATA_FILE}{C.RESET} ({len(db)} toplam kayıt)")

def save_new_results(results: list[dict]) -> None:
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    log("OK", f"Yeni duyurular kaydedildi → {C.GREEN}{OUTPUT_FILE}{C.RESET} ({len(results)} kayıt)")


# ─────────────────────────────────────────────────────────────────
# BÖLÜM 4 │ HTML Temizleme & Parse (Gelişmiş)
# ─────────────────────────────────────────────────────────────────

def parse_html_comprehensive(html_str: str) -> tuple[str, list]:
    """
    HTML içeriğini BeautifulSoup ile düz metne dönüştürür.
    Linkleri (<a>) kaybetmeden metne gömer ve varsa PDF linklerini liste olarak döndürür.
    """
    if not html_str or not html_str.strip():
        return "", []

    soup = BeautifulSoup(html_str, "lxml")

    # Gereksiz blokları kaldır
    for tag in soup(["script", "style", "head", "meta", "link"]):
        tag.decompose()

    pdf_links = []

    # Bütün linkleri işle (PDF ise listeye al, değilse metne ekle)
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        
        # Göreli (relative) linkleri düzelt
        if href.startswith("/"):
            href = BASE_URL + href
            
        if href.lower().endswith(".pdf") or ".pdf" in href.lower():
            if href not in pdf_links:
                pdf_links.append(href)
            a.string = f"{a.text.strip()} [PDF EKTEDİR]"
        else:
            link_text = a.text.strip()
            if link_text and href not in link_text:
                a.string = f"{link_text} ({href})"
            else:
                a.string = href

    # Blok elementlere newline ekle (metinlerin yapışmasını engeller)
    for tag in soup.find_all(["br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"]):
        tag.insert_after("\n")

    text = soup.get_text(separator=" ")

    # Çoklu boşluk / satır atlamalarını temizle
    lines = [line.strip() for line in text.splitlines()]
    clean_text = "\n".join([line for line in lines if line])

    # Sadece unique PDF linklerini döndür
    return clean_text, list(dict.fromkeys(pdf_links))


# ─────────────────────────────────────────────────────────────────
# BÖLÜM 5 │ PDF indirme ve metin çıkarma
# ─────────────────────────────────────────────────────────────────

def _extract_with_pypdf(pdf_bytes: bytes) -> str:
    import pypdf  # noqa: PLC0415
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    parts  = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(parts).strip()

def _extract_with_pdfminer(pdf_bytes: bytes) -> str:
    from pdfminer.high_level import extract_text as pm_extract  # noqa: PLC0415
    return pm_extract(io.BytesIO(pdf_bytes)).strip()

def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> Optional[str]:
    for extractor in (_extract_with_pypdf, _extract_with_pdfminer):
        try:
            text = extractor(pdf_bytes)
            if text:
                return text
        except ImportError:
            continue
        except Exception as e:
            log("WARN", f"PDF metin çıkarma hatası ({extractor.__name__}): {e}")
    log("WARN", f"PDF okunamadı. {C.YELLOW}pypdf{C.RESET} veya {C.YELLOW}pdfminer.six{C.RESET} kurunuz.")
    return None

def download_and_parse_pdf(url: str, ann_id: int, label: str = "") -> dict:
    result = {"pdfUrl": url, "pdfPath": None, "pdfText": None, "error": None}

    log("PDF", f"İndiriliyor: {C.CYAN}{url[:60]}{'…' if len(url) > 60 else ''}{C.RESET}")
    response = http_get(url, stream=True)
    if response is None:
        result["error"] = "HTTP isteği başarısız"
        return result

    content_type = response.headers.get("Content-Type", "").lower()
    pdf_bytes    = response.content

    if "pdf" not in content_type and not url.lower().endswith(".pdf"):
        log("WARN", f"PDF beklendi ama HTML geldi. Metin olarak işleniyor.")
        clean_text, _ = parse_html_comprehensive(response.text)
        result["pdfText"] = clean_text
        result["error"]   = "PDF değil, HTML içerik alındı"
        return result

    os.makedirs(PDF_DIR, exist_ok=True)
    safe_name = re.sub(r"[^\w.\-]", "_", url.split("/")[-1].split("?")[0]) or "belge.pdf"
    pdf_path  = os.path.join(PDF_DIR, f"{ann_id}_{label}_{safe_name}")
    try:
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)
        result["pdfPath"] = pdf_path
        log("OK", f"Kaydedildi: {C.GREEN}{pdf_path}{C.RESET}")
    except OSError as e:
        log("WARN", f"PDF diske yazılamadı: {e}")

    result["pdfText"] = extract_text_from_pdf_bytes(pdf_bytes)
    if result["pdfText"]:
        log("OK", f"PDF metin çıkarıldı: {C.GREEN}{len(result['pdfText'])} karakter{C.RESET}")

    return result


# ─────────────────────────────────────────────────────────────────
# BÖLÜM 6 │ Duyuru listesi çekme (pagination + delta)
# ─────────────────────────────────────────────────────────────────

def fetch_new_announcement_list(max_known_id: int) -> list[dict]:
    section("DUYURU LİSTESİ TARAMA")
    log("INFO", f"Referans ID (en güncel kayıt): {C.BOLD}{C.CYAN}{max_known_id}{C.RESET}")

    new_items = []
    page      = 1

    while True:
        url      = URL_LIST.format(page=page)
        response = http_get(url)

        if response is None:
            log("ERROR", f"Sayfa {page} alınamadı. Tarama durduruluyor.")
            break

        try:
            items: list[dict] = response.json()
        except Exception:
            log("ERROR", f"Sayfa {page} JSON parse hatası. Tarama durduruluyor.")
            break

        if not items:
            log("INFO", f"Sayfa {page} boş döndü. Tüm sayfalar tarandı.")
            break

        page_ids = [item.get("id", 0) for item in items]
        log(
            "FETCH",
            f"Sayfa {C.BOLD}{page}{C.RESET} · "
            f"{len(items)} kayıt · "
            f"ID aralığı: {C.DIM}{min(page_ids)} – {max(page_ids)}{C.RESET}",
        )

        page_new = [item for item in items if item.get("id", 0) > max_known_id]
        new_items.extend(page_new)

        if min(page_ids) <= max_known_id:
            log("STOP", f"Sayfa {page}'de bilinen ID'lere ulaşıldı. Tarama tamamlandı.")
            break

        page += 1
        time.sleep(REQUEST_DELAY)

    log("NEW", f"Toplam yeni duyuru: {C.BOLD}{C.GREEN}{len(new_items)}{C.RESET}")
    return new_items


# ─────────────────────────────────────────────────────────────────
# BÖLÜM 7 │ Tek duyurunun içeriğini işleme
# ─────────────────────────────────────────────────────────────────

def process_announcement(item: dict) -> dict:
    ann_id    = item["id"]
    title     = item.get("title", "")
    url_field = (item.get("url") or "").strip()
    updated   = item.get("updated", "")
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    record = {
        "fetchedAt": fetched_at,
        "sourceUrl": "",
        "id":        ann_id,
        "title":     title,
        "updated":   updated,
        "content":   None,
        "attachments": []
    }

    # ── DURUM A: url alanı dolu ──────────────────────────────────
    if url_field:
        print() # Progress bar kırılmasın diye boş satır
        log("FETCH", f"[DURUM A] ID {C.BOLD}{ann_id}{C.RESET} · URL: {C.CYAN}{url_field[:60]}{C.RESET}")
        record["sourceUrl"] = url_field

        if ".pdf" in url_field.lower():
            # Doğrudan PDF Dosyası
            pdf_result = download_and_parse_pdf(url_field, ann_id, label="A")
            record["content"] = "Bu duyuru doğrudan bir PDF dosyasıdır."
            record["attachments"].append({
                "url": url_field,
                "type": "pdf",
                "content": pdf_result["pdfText"] if pdf_result["pdfText"] else "[PDF Okunamadı]"
            })
        else:
            # HTML Dış Link / Sayfa
            response = http_get(url_field)
            if response is not None:
                clean_text, pdf_links = parse_html_comprehensive(response.text)
                record["content"] = clean_text if clean_text else None
                
                # HTML içindeki PDF'leri indir ve attachments'a ekle
                for idx, pdf_href in enumerate(pdf_links, start=1):
                    pdf_result = download_and_parse_pdf(pdf_href, ann_id, label=f"A{idx}")
                    record["attachments"].append({
                        "url": pdf_href,
                        "type": "pdf",
                        "content": pdf_result["pdfText"] if pdf_result["pdfText"] else "[PDF Okunamadı]"
                    })
            else:
                record["content"] = "[İçerik alınamadı]"
                
        return record

    # ── DURUM B: url alanı boş → detay endpoint ─────────────────
    detail_url = URL_DETAIL.format(id=ann_id)
    print() # Progress bar kırılmasın diye boş satır
    log("FETCH", f"[DURUM B] ID {C.BOLD}{ann_id}{C.RESET} · Detay endpoint'i sorgulanıyor…")
    record["sourceUrl"] = detail_url

    response = http_get(detail_url)
    if response is None:
        record["content"] = "[Detay içeriği alınamadı]"
        return record

    try:
        detail_json = response.json()
    except Exception:
        log("WARN", f"ID {ann_id} detay JSON parse hatası.")
        record["content"] = "[JSON parse hatası]"
        return record

    raw_html = detail_json.get("text") or detail_json.get("content") or ""

    # HTML'i parse et
    clean_text, pdf_links = parse_html_comprehensive(raw_html)
    record["content"] = clean_text if clean_text else None

    # Bulunan PDF'leri attachments'a ekle
    for idx, pdf_href in enumerate(pdf_links, start=1):
        pdf_result = download_and_parse_pdf(pdf_href, ann_id, label=f"B{idx}")
        record["attachments"].append({
            "url": pdf_href,
            "type": "pdf",
            "content": pdf_result["pdfText"] if pdf_result["pdfText"] else "[PDF Okunamadı]"
        })

    return record


# ─────────────────────────────────────────────────────────────────
# BÖLÜM 8 │ Ana iş akışı
# ─────────────────────────────────────────────────────────────────

def run() -> None:
    banner()
    t0 = time.time()

    # 8.1 — Mevcut veritabanını yükle
    section("VERİTABANI YÜKLEME")
    db, max_known_id = load_database()
    log("OK", f"Mevcut kayıt sayısı : {C.BOLD}{len(db)}{C.RESET}")
    log("OK", f"En güncel kayıt ID  : {C.BOLD}{C.CYAN}{max_known_id}{C.RESET}")

    # 8.2 — Yeni duyuru listesini çek (delta fetch)
    new_items = fetch_new_announcement_list(max_known_id)

    if not new_items:
        log("INFO", "Yeni duyuru bulunamadı. Program sonlanıyor.")
        _summary(0, 0, t0, len(db))
        return

    # ID'ye göre azalan sırala (en yeni önce işlensin)
    new_items.sort(key=lambda x: x["id"], reverse=True)

    # 8.3 — Her yeni duyurunun içeriğini işle
    section(f"İÇERİK İŞLEME  ({len(new_items)} duyuru)")
    results: list[dict] = []
    pdf_count = 0

    for idx, item in enumerate(new_items, start=1):
        progress_bar(idx, len(new_items), prefix="Duyurular")
        time.sleep(REQUEST_DELAY)

        try:
            record = process_announcement(item)
        except Exception as e:
            log("ERROR", f"ID {item['id']} işlenirken hata: {e}")
            continue

        results.append(record)

        # İstatistik için PDF miktarını hesapla
        pdf_count += len(record.get("attachments", []))

        # Ana veritabanına ekle (Basit liste formatında tutuluyor)
        db[item["id"]] = {
            "id":      item["id"],
            "title":   item.get("title", ""),
            "updated": item.get("updated", ""),
            "url":     item.get("url", ""),
        }

    # 8.4 — Kaydet
    print()
    section("KAYIT")
    save_new_results(results)
    save_database(db)

    # 8.5 — Özet
    _summary(len(results), pdf_count, t0, len(db))


def _summary(new_count: int, pdf_count: int, t0: float, total_db: int) -> None:
    elapsed = time.time() - t0
    section("ÖZET RAPOR")

    rows = [
        ("Veritabanı (toplam kayıt)", str(total_db)),
        ("Bu çalışmada eklenen",       str(new_count)),
        ("İndirilen PDF Sayısı",       str(pdf_count)),
        ("Geçen süre",                  f"{elapsed:.1f} sn"),
        ("Tamamlanma",                  datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    ]
    for label, val in rows:
        print(f"  {C.DIM}{label:<35}{C.RESET}  {C.BOLD}{C.WHITE}{val}{C.RESET}")

    print()
    print(f"  {C.CYAN}{'═' * 62}{C.RESET}")
    print(f"  {C.GREEN}{C.BOLD}  ✔  İşlem başarıyla tamamlandı.{C.RESET}  "
          f"{C.DIM}{C.RESET}")
    print(f"  {C.CYAN}{'═' * 62}{C.RESET}")
    print()


# ─────────────────────────────────────────────────────────────────
# GİRİŞ NOKTASI
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print(f"\n\n  {C.YELLOW}[⚠]  Kullanıcı tarafından iptal edildi.{C.RESET}\n")
        sys.exit(0)
    except Exception as exc:
        print(f"\n  {C.RED}[✘]  Kritik hata: {exc}{C.RESET}\n")
        raise
