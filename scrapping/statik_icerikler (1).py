#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║     İNÖNÜ ÜNİVERSİTESİ STATİK İÇERİK SCRAPER                    ║
║                  Powered by meges.com.tr                         ║
╚══════════════════════════════════════════════════════════════════╝

Kullanım:
    python inonu_static_scraper.py

Gereksinimler:
    pip install requests beautifulsoup4 lxml
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── MongoDB entegrasyonu ──────────────────────────────────────────
try:
    _PARENT = Path(__file__).resolve().parent
    import sys as _sys
    _sys.path.insert(0, str(_PARENT))
    from db_manager import DBManager, COL_STATIC_CONTENTS
    _MONGO_ENABLED = True
except ImportError:
    _MONGO_ENABLED = False

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
    "INFO":  f"{C.BLUE}[ℹ]{C.RESET}",
    "OK":    f"{C.GREEN}[✔]{C.RESET}",
    "WARN":  f"{C.YELLOW}[⚠]{C.RESET}",
    "ERROR": f"{C.RED}[✘]{C.RESET}",
    "FETCH": f"{C.MAGENTA}[↓]{C.RESET}",
    "SKIP":  f"{C.DIM}[→]{C.RESET}",
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

def banner() -> None:
    lines = [
        "",
        f"{C.CYAN}{C.BOLD}  ╔══════════════════════════════════════════════════════════════════╗{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║    {C.WHITE}██╗███╗   ██╗ ██████╗ ███╗   ██╗██╗   ██╗{C.CYAN}          ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║    {C.WHITE}██║████╗  ██║██╔═══██╗████╗  ██║██║   ██║{C.CYAN}          ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║    {C.WHITE}██║██╔██╗ ██║██║   ██║██╔██╗ ██║██║   ██║{C.CYAN}          ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║    {C.WHITE}██║██║╚██╗██║██║   ██║██║╚██╗██║██║   ██║{C.CYAN}          ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║    {C.WHITE}██║██║ ╚████║╚██████╔╝██║ ╚████║╚██████╔╝{C.CYAN}          ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║      {C.DIM}╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═══╝ ╚═════╝{C.CYAN}           ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║                                                                        ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║    {C.YELLOW}mert ege sungur {C.GREEN}meges.com.tr{C.CYAN}             ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║                {C.DIM}İnönü Üniversitesi {C.CYAN}          ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ╚══════════════════════════════════════════════════════════════════╝{C.RESET}",
        "",
    ]
    for line in lines:
        print(line)


# ─────────────────────────────────────────────────────────────────
# BÖLÜM 1 │ Konfigürasyon
# ─────────────────────────────────────────────────────────────────

BASE_URL  = "https://panel.inonu.edu.tr"
BASE_WWW  = "https://www.inonu.edu.tr"

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

REQUEST_DELAY   = 0.8
REQUEST_TIMEOUT = 20
OUTPUT_FILE     = "statik_icerikler.json"

SOURCES: list[dict] = [
    {
        "key":   "tarihce",
        "label": "Tarihçe",
        "url":   "https://panel.inonu.edu.tr/servlet/content?id=16204&lang=tr",
        "type":  "json",
    },
    {
        "key":   "oryantasyon",
        "label": "Oryantasyon",
        "url":   "https://panel.inonu.edu.tr/servlet/content?id=28600&lang=tr",
        "type":  "json",
    },
    {
        "key":   "personeller",
        "label": "Personeller",
        "url":   "https://panel.inonu.edu.tr/servlet/staff?unit=ogrencidb",
        "type":  "staff",
    },
    {
        "key":   "secmeli_dersler",
        "label": "Seçmeli Dersler",
        "url":   "https://panel.inonu.edu.tr/servlet/content?id=24674&lang=tr",
        "type":  "json",
    },
    {
        "key":   "misyon_vizyon",
        "label": "Misyon & Vizyon",
        "url":   "https://panel.inonu.edu.tr/servlet/content?id=1449&lang=tr",
        "type":  "json",
    },
    {
        "key":   "secmeli_sinav_programi",
        "label": "Seçmeli Ders Sınav Programı",
        "url":   "https://panel.inonu.edu.tr/servlet/content?id=24678&lang=tr",
        "type":  "json",
    },
    {
        "key":   "ic_kontrol",
        "label": "İç Kontrol",
        "url":   "https://panel.inonu.edu.tr/servlet/content?id=32074&lang=tr",
        "type":  "json",
    },
    {
        "key":   "usd_dersler",
        "label": "ÜSD Dersler (Dönemlik Açılan Ders Listesi)",
        "url":   "https://panel.inonu.edu.tr/servlet/content?id=24677&lang=tr",
        "type":  "json",
    },
    {
        "key":   "sss",
        "label": "Sıkça Sorulan Sorular",
        "url":   "https://panel.inonu.edu.tr/servlet/menu?type=inside&id=1636",
        "type":  "sss",
    },
]


# ─────────────────────────────────────────────────────────────────
# BÖLÜM 2 │ HTTP yardımcısı
# ─────────────────────────────────────────────────────────────────

def http_get(url: str) -> Optional[requests.Response]:
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
            verify=False,
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
# BÖLÜM 3 │ HTML → Düz metin dönüştürücü
# ─────────────────────────────────────────────────────────────────

# Görünmez unicode boşluk karakterleri
_INVISIBLE = {"\u200b", "\u200c", "\u200d", "\u00a0", "\ufeff"}

def html_to_text(html_str: str) -> tuple[str, list[str]]:
    """
    HTML'i tamamen saf düz metne dönüştürür.
    - Tüm HTML etiketleri kaldırılır
    - Kaçırılmış (\\/) slash'lar düzeltilir
    - PDF linkleri ayrı listeye alınır → metinde [PDF] olarak gösterilir
    - Diğer linkler: 'Metin (URL)' formatında bırakılır
    - Görünmez karakterler ve boş satırlar temizlenir
    """
    if not html_str or not html_str.strip():
        return "", []

    # Escaped slash'ları düzelt (\/ → /)
    html_str = html_str.replace("\\/", "/")

    soup = BeautifulSoup(html_str, "lxml")

    # Gereksiz elementleri tamamen kaldır
    for tag in soup(["script", "style", "head", "meta", "link", "noscript"]):
        tag.decompose()

    pdf_links: list[str] = []

    # <a> etiketlerini düz metne çevir
    for a in soup.find_all("a", href=True):
        href = a["href"].strip().strip('"').strip("'")

        # Göreli URL → mutlak URL
        if href.startswith("/"):
            href = BASE_URL + href

        link_text = a.get_text(strip=True)

        if ".pdf" in href.lower():
            # PDF linkleri → listeye al, metinde [PDF] bırak
            if href not in pdf_links:
                pdf_links.append(href)
            replacement = f"{link_text} [PDF]" if link_text else "[PDF]"
        else:
            # Normal link → "Metin (URL)" veya sadece URL
            if link_text and link_text != href:
                replacement = f"{link_text} ({href})"
            else:
                replacement = href

        a.replace_with(replacement)

    # Blok elementlerin önüne/arkasına yeni satır ekle
    for tag in soup.find_all(["p", "div", "li", "tr", "br",
                               "h1", "h2", "h3", "h4", "h5", "h6"]):
        tag.insert_after("\n")

    raw_text = soup.get_text(separator=" ")

    # Satır bazlı temizlik
    clean_lines = []
    for line in raw_text.splitlines():
        # Görünmez karakterleri kaldır
        line = "".join(ch for ch in line if ch not in _INVISIBLE).strip()
        # Sadece boşluk olan satırları atla
        if line:
            clean_lines.append(line)

    clean = "\n".join(clean_lines)
    return clean, list(dict.fromkeys(pdf_links))  # PDF listesinde tekrar yok


# ─────────────────────────────────────────────────────────────────
# BÖLÜM 4 │ API parse fonksiyonları
# ─────────────────────────────────────────────────────────────────

def _extract_html_from_item(item: dict) -> str:
    """
    Bir JSON öğesinden ham HTML'i çıkarır.
    'text' alanı bazen iç içe JSON string olabilir → tekrar parse eder.
    """
    raw = item.get("text") or item.get("content") or item.get("body") or ""

    # İç içe JSON string kontrolü
    stripped = raw.strip()
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            inner = json.loads(raw)
            if isinstance(inner, list) and inner:
                raw = inner[0].get("text", raw)
            elif isinstance(inner, dict):
                raw = inner.get("text", raw)
        except Exception:
            pass  # Parse edilemiyorsa orijinali kullan

    return raw


def parse_content_api(response: requests.Response) -> tuple[str, list[str], dict]:
    """
    /servlet/content endpoint'ini işler.
    API liste döndürür → her öğenin 'text' alanı HTML içerir.
    Birden fazla öğe varsa başlıkla ayrılarak birleştirilir.
    """
    extra: dict = {}

    try:
        data = response.json()
    except Exception:
        clean, pdfs = html_to_text(response.text)
        return clean, pdfs, extra

    # Liste formatı: [{"id":..., "title":..., "text":"<html>"}, ...]
    if isinstance(data, list):
        blocks:   list[str] = []
        all_pdfs: list[str] = []

        for idx, item in enumerate(data):
            if not isinstance(item, dict):
                continue

            raw_html       = _extract_html_from_item(item)
            clean, pdfs    = html_to_text(raw_html)
            title          = (item.get("title") or "").strip()

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

    # Dict formatı
    if isinstance(data, dict):
        raw_html    = _extract_html_from_item(data)
        extra       = {k: v for k, v in data.items()
                       if k not in ("text", "content", "body")}
        clean, pdfs = html_to_text(raw_html)
        return clean, pdfs, extra

    return "", [], extra


def parse_staff_api(response: requests.Response) -> list[dict]:
    """
    /servlet/staff endpoint'inden personel listesini çeker.
    Gerçek veriler her öğenin 'staff' alt anahtarında bulunur.

    Örnek yapı:
    [
      {
        "image": {...},
        "staff": {
          "name": "Tacettin ",
          "surName": "KOYUNOĞLU",
          "email": "...",
          "phone": "...",
          "staffGroup": { "translateStaffGroup": { "tr": { "title": "Daire Başkanı" } } },
          "staffTitle": { "translateStaffCadre": { "tr": { "title": "Öğrenci İşleri Daire Başkanı V." } } },
          "translateStaff": { "tr": { "description": "...", "position": "..." } }
        }
      }, ...
    ]
    """
    try:
        data = response.json()
    except Exception as e:
        log("WARN", f"Personel JSON parse hatası: {e}")
        return []

    if not isinstance(data, list):
        log("WARN", "Personel API beklenmedik format döndürdü.")
        return []

    result = []
    for item in data:
        s = item.get("staff") if isinstance(item, dict) else None
        if not s:
            continue

        # Ad Soyad
        ad    = (s.get("name")    or "").strip()
        soyad = (s.get("surName") or "").strip()
        ad_soyad = f"{ad} {soyad}".strip()

        # Unvan → staffTitle.translateStaffCadre.tr.title
        unvan = ""
        st = s.get("staffTitle") or {}
        cadre = st.get("translateStaffCadre") or {}
        unvan = (cadre.get("tr") or {}).get("title", "").strip()

        # Departman (Birim) → staffGroup.translateStaffGroup.tr.title
        departman = ""
        sg = s.get("staffGroup") or {}
        tsg = sg.get("translateStaffGroup") or {}
        departman = (tsg.get("tr") or {}).get("title", "").strip()

        # Görev açıklaması → translateStaff.tr.description veya .position
        gorev = ""
        ts = s.get("translateStaff") or {}
        tr_data = ts.get("tr") or {}
        desc = (tr_data.get("description") or "").strip()
        pos  = (tr_data.get("position")    or "").strip()
        gorev = desc if desc and desc != " " else pos

        result.append({
            "id":        s.get("id", ""),
            "ad_soyad":  ad_soyad,
            "unvan":     unvan,
            "departman": departman,
            "gorev":     gorev,
            "email":     (s.get("email")  or "").strip(),
            "telefon":   (s.get("phone")  or "").strip(),
        })

    return result


def fetch_sss_data(parent_id: int) -> dict:
    """
    Menü altındaki Sıkça Sorulan Sorular liste/içeriklerini çoklu istek atarak toplar.

    Akış:
      1) /servlet/menu?type=inside&id=1636  → Kategori listesi (id + translate)
      2) Her kategori id'si için /servlet/content?id={id}&lang=tr → İçerik
         Content API şu formatta döner:
         [{"id": ..., "title": "...", "text": "<html>...", "created": "..."}]
      3) text alanındaki HTML düz metne çevrilir.
    """
    menu_url = f"{BASE_URL}/servlet/menu?type=inside&id={parent_id}"
    log("FETCH", f"SSS Menü ağacı çekiliyor: {C.DIM}{menu_url}{C.RESET}")
    menu_resp = http_get(menu_url)

    if not menu_resp:
        return {}

    try:
        menu_items = menu_resp.json()
    except Exception:
        return {}

    all_data = {}

    def parse_content_items(data):
        """
        /servlet/content dönen JSON listesini parse eder.
        Her öğe: {"id": ..., "title": "...", "text": "<html>..."}
        text alanı HTML → düz metne çevrilir.
        """
        if not isinstance(data, list):
            return data

        results = []
        for item in data:
            if not isinstance(item, dict):
                continue

            title = (item.get("title") or "").strip()

            # text alanı HTML içerir → düz metne çevir
            raw_html = item.get("text") or ""
            clean_text, pdf_links = html_to_text(raw_html)

            entry = {
                "id":     item.get("id", ""),
                "baslik": title,
                "icerik": clean_text,
            }
            if pdf_links:
                entry["pdf_links"] = pdf_links

            results.append(entry)
        return results

    def get_faq_content(cid):
        url = f"{BASE_URL}/servlet/content?id={cid}&lang=tr"
        resp = http_get(url)
        if not resp:
            return None
        try:
            return resp.json()
        except Exception:
            return None

    # Ana içerik (parent_id kendisi, örn: 1636)
    log("FETCH", f"SSS Ana içerik çekiliyor: id={C.BOLD}{parent_id}{C.RESET}")
    main_content = get_faq_content(parent_id)
    if main_content:
        all_data[str(parent_id)] = {
            "baslik": "Sıkça Sorulan Sorular (Genel)",
            "content": parse_content_items(main_content)
        }

    # Alt menü içerikleri — her kategori için content endpoint'ine istek at
    for item in menu_items:
        cid = item.get("id")
        if not cid or cid == parent_id:
            # parent_id kendisini atla (zaten yukarıda çektik)
            continue

        try:
            tr_name = json.loads(item.get("translate", "{}")).get("tr", str(cid))
        except Exception:
            tr_name = str(cid)

        log("FETCH", f"SSS Kategori: {C.BOLD}{tr_name}{C.RESET} (id={cid})")
        content = get_faq_content(cid)
        if content:
            parsed = parse_content_items(content)
            all_data[str(cid)] = {
                "baslik": tr_name,
                "content": parsed
            }
            # Kısa önizleme
            if isinstance(parsed, list):
                for p in parsed[:1]:
                    preview = (p.get("icerik") or "")[:100]
                    if preview:
                        log("OK", f"  → {C.DIM}{preview}...{C.RESET}")
        time.sleep(REQUEST_DELAY)

    return all_data


# ─────────────────────────────────────────────────────────────────
# BÖLÜM 5 │ Her kaynağı işleyen ana fonksiyon
# ─────────────────────────────────────────────────────────────────

def process_source(source: dict) -> dict:
    key   = source["key"]
    label = source["label"]
    url   = source["url"]
    stype = source["type"]

    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    record = {
        "key":       key,
        "label":     label,
        "url":       url,
        "fetchedAt": fetched_at,
        "content":   None,
        "pdfLinks":  [],
        "extra":     {},
        "error":     None,
    }

    log("FETCH", f"{C.BOLD}{label}{C.RESET}  ←  {C.DIM}{url}{C.RESET}")

    if stype == "sss":
        # SSS için çoklu ağ isteği yapıldığı için akış farklı
        parent_id = 1636
        if "id=" in url:
            try:
                parent_id = int(url.split("id=")[1].split("&")[0])
            except:
                pass
                
        sss_data = fetch_sss_data(parent_id)
        if not sss_data:
            record["error"] = "SSS verisi çekilemedi"
            log("ERROR", f"{label} alınamadı.")
            return record

        record["content"] = sss_data
        
        cats = len(sss_data)
        item_count = sum(len(v.get("content", [])) if isinstance(v.get("content"), list) else 1 for v in sss_data.values())
        record["extra"] = {"categories": cats, "total_questions": item_count}
        log("OK", f"{C.GREEN}{label}{C.RESET} → {C.BOLD}{cats}{C.RESET} kategori, {C.CYAN}{item_count} soru{C.RESET}")
        return record

    response = http_get(url)
    if response is None:
        record["error"] = "HTTP isteği başarısız"
        log("ERROR", f"{label} alınamadı.")
        return record

    if stype == "staff":
        staff = parse_staff_api(response)
        record["content"] = staff
        record["extra"]   = {"count": len(staff)}
        log("OK", f"{C.GREEN}{label}{C.RESET} → {C.BOLD}{len(staff)}{C.RESET} personel")

    elif stype == "json":
        clean, pdfs, extra = parse_content_api(response)
        record["content"]  = clean or "[İçerik boş]"
        record["pdfLinks"] = pdfs
        record["extra"]    = extra
        log("OK", (
            f"{C.GREEN}{label}{C.RESET} → "
            f"{C.BOLD}{len(clean)}{C.RESET} karakter"
            + (f", {C.CYAN}{len(pdfs)} PDF{C.RESET}" if pdfs else "")
        ))

    return record


# ─────────────────────────────────────────────────────────────────
# BÖLÜM 6 │ Kaydetme
# ─────────────────────────────────────────────────────────────────

def save_results(results: list[dict]) -> None:
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    log("OK", f"Sonuçlar kaydedildi → {C.GREEN}{OUTPUT_FILE}{C.RESET} ({len(results)} kayıt)")


def save_to_mongo(results: list[dict]) -> None:
    """
    Statik içerikleri MongoDB'ye upsert eder ve metin içeriklerini
    anlamsal olarak 'chunks' koleksiyonuna yazar.
    """
    if not _MONGO_ENABLED:
        log("WARN", "db_manager bulunamadı, MongoDB'ye yazma atlandı.")
        return

    try:
        with DBManager() as db_mgr:
            inserted = updated = chunk_total = 0

            for record in results:
                key        = record.get("key", "")
                source_url = record.get("url", "")
                label      = record.get("label", key)
                content    = record.get("content")
                stype      = "sss" if isinstance(content, dict) else "json"

                # ── 1. Ana belge upsert ────────────────────────────
                status = db_mgr.upsert(COL_STATIC_CONTENTS, record, id_field="key")
                if status == "inserted":
                    inserted += 1
                else:
                    updated += 1

                # ── 2. İçeriği chunk'la ──────────────────────────
                if stype == "sss" and isinstance(content, dict):
                    # Her SSS kategorisini ayrı ayrı chunk'la
                    for cat_key, cat_data in content.items():
                        cat_label = cat_data.get("baslik", cat_key)
                        cat_items = cat_data.get("content", [])

                        if isinstance(cat_items, list):
                            for item in cat_items:
                                q      = (item.get("baslik") or "").strip()
                                ans    = (item.get("icerik") or "").strip()
                                if q or ans:
                                    full_text = f"{q}\n\n{ans}".strip() if q else ans
                                    n = db_mgr.upsert_chunks(
                                        text=full_text,
                                        source_url=f"{source_url}#cat{cat_key}",
                                        source_collection=COL_STATIC_CONTENTS,
                                        doc_id=f"{key}_{cat_key}",
                                    )
                                    chunk_total += n
                elif isinstance(content, str) and content.strip():
                    # Metin başlığıyla birlikte chunk'la
                    full_text = f"{label}\n\n{content}".strip()
                    n = db_mgr.upsert_chunks(
                        text=full_text,
                        source_url=source_url,
                        source_collection=COL_STATIC_CONTENTS,
                        doc_id=key,
                    )
                    chunk_total += n

            log("OK", (
                f"MongoDB → {C.GREEN}+{inserted} yeni{C.RESET} / "
                f"{C.DIM}{updated} güncellendi{C.RESET} | "
                f"{C.CYAN}{chunk_total} chunk yazıldı{C.RESET}"
            ))
    except Exception as e:
        log("WARN", f"MongoDB yazma hatası (JSON kaydı etkilenmedi): {C.RED}{e}{C.RESET}")


# ─────────────────────────────────────────────────────────────────
# BÖLÜM 7 │ Ana iş akışı
# ─────────────────────────────────────────────────────────────────

def run() -> None:
    banner()
    t0 = time.time()

    section(f"İÇERİK ÇEKME  ({len(SOURCES)} kaynak)")

    results: list[dict] = []
    errors = 0

    for idx, source in enumerate(SOURCES, start=1):
        print(f"  {C.DIM}[{idx}/{len(SOURCES)}]{C.RESET}", end="  ")
        try:
            record = process_source(source)
        except Exception as e:
            log("ERROR", f"{source['label']} işlenirken kritik hata: {e}")
            errors += 1
            continue

        if record["error"]:
            errors += 1

        results.append(record)
        time.sleep(REQUEST_DELAY)

    print()
    section("KAYIT")
    save_results(results)
    save_to_mongo(results)

    elapsed = time.time() - t0
    section("ÖZET RAPOR")
    rows = [
        ("Toplam kaynak",  str(len(SOURCES))),
        ("Başarılı",       str(len(results) - errors)),
        ("Hatalı",         str(errors)),
        ("Geçen süre",     f"{elapsed:.1f} sn"),
        ("Tamamlanma",     datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    ]
    for label, val in rows:
        print(f"  {C.DIM}{label:<35}{C.RESET}  {C.BOLD}{C.WHITE}{val}{C.RESET}")

    print()
    print(f"  {C.CYAN}{'═' * 62}{C.RESET}")
    print(f"  {C.GREEN}{C.BOLD}  ✔  İşlem başarıyla tamamlandı.{C.RESET}  {C.DIM}— MEGE SOLUTIONS{C.RESET}")
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
