"""
=============================================================
  İNÖNÜ ÜNİVERSİTESİ - TAM PERSONEL SCRAPER v2
  Yazar: Claude (Anthropic)
  
  KURULUM:
    pip install requests beautifulsoup4 lxml
  
  ÇALIŞTIRMA:
    python inonu_scraper_v2.py
  
  ÇIKTI:
    inonu_personel.json
=============================================================
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import re
import urllib3
urllib3.disable_warnings()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
}

BASE = "https://www.inonu.edu.tr"

# =====================================================================
# GERÇEK URL SLUG'LARI (Google taramasından doğrulandı)
# Her bölümün kendi slug'u var, fakülte değil bölüm adına göre
# =====================================================================

FAKULTELER = [
    {
        "ad": "Dis Hekimligi Fakultesi",
        "slug": "dishekimligi",
        "dekan_menu": "dekan",   # /dishekimligi/menu/XXX/dekan
        "bolumler": [
            {"ad": "Agiz Dis ve Cene Cerrahisi",   "slug": "agizdisvecene"},
            {"ad": "Agiz Dis Cene Radyolojisi",    "slug": "agizradyoloji"},
            {"ad": "Endodonti",                     "slug": "endodonti"},
            {"ad": "Cocuk Dis Hekimligi",           "slug": "cocukdis"},
            {"ad": "Ortodonti",                     "slug": "ortodonti"},
            {"ad": "Periodontoloji",                "slug": "periodontoloji"},
            {"ad": "Protetik Dis Tedavisi",         "slug": "protetikdis"},
            {"ad": "Restoratif Dis Tedavisi",       "slug": "restoratifdis"},
        ],
    },
    {
        "ad": "Eczacilik Fakultesi",
        "slug": "eczacilik",
        "dekan_menu": "dekan",
        "bolumler": [
            {"ad": "Eczacilik Teknolojisi",         "slug": "eczaciliktekn"},
            {"ad": "Farmasotik Botanik",            "slug": "farmasotikbot"},
            {"ad": "Farmasotik Kimya",              "slug": "farmasotikkimya"},
            {"ad": "Farmasotik Mikrobiyoloji",      "slug": "farmasotikmirobiyoloji"},
            {"ad": "Farmasotik Toksikoloji",        "slug": "farmasotiktoks"},
            {"ad": "Farmakognozi",                  "slug": "farmakognozi"},
            {"ad": "Farmakoloji",                   "slug": "farmakoloji"},
            {"ad": "Biyofarmasi ve Farmakokinetik", "slug": "biyofarmasi"},
        ],
    },
    {
        "ad": "Egitim Fakultesi",
        "slug": "egitim",
        "dekan_menu": "dekan",
        "bolumler": [
            {"ad": "Bilgisayar ve Ogretim Teknolojileri",  "slug": "bot"},
            {"ad": "Egitim Bilimleri",                     "slug": "egitimbilimleri"},
            {"ad": "Guzel Sanatlar Egitimi",               "slug": "gse"},
            {"ad": "Ilkogretim",                           "slug": "ilkogretim"},
            {"ad": "Matematik ve Fen Bilimleri",           "slug": "mfb"},
            {"ad": "Ozel Egitim",                          "slug": "ozelegitim"},
            {"ad": "PDR",                                  "slug": "pdr"},
            {"ad": "Turk Dili ve Edebiyati",               "slug": "turkedebiyatiegitim"},
            {"ad": "Yabanci Diller",                       "slug": "yabancidiller"},
        ],
    },
    {
        "ad": "Fen Edebiyat Fakultesi",
        "slug": "fenedebiyat",
        "dekan_menu": "dekan",
        "bolumler": [
            {"ad": "Biyoloji",                             "slug": "biyoloji"},
            {"ad": "Cografya",                             "slug": "cografya"},
            {"ad": "Felsefe",                              "slug": "felsefe"},
            {"ad": "Fizik",                                "slug": "fizik"},
            {"ad": "Kimya",                                "slug": "kimyafe"},
            {"ad": "Matematik",                            "slug": "matematik"},
            {"ad": "Psikoloji",                            "slug": "psikoloji"},
            {"ad": "Sosyoloji",                            "slug": "sosyoloji"},
            {"ad": "Tarih",                                "slug": "tarih"},
            {"ad": "Turk Dili ve Edebiyati",               "slug": "turkdili"},
        ],
    },
    {
        "ad": "Guzel Sanatlar ve Tasarim Fakultesi",
        "slug": "gsf",
        "dekan_menu": "dekan",
        "bolumler": [
            {"ad": "Grafik Tasarim",                       "slug": "grafiktasarim"},
            {"ad": "Heykel",                               "slug": "heykel"},
            {"ad": "Ic Mimarlik",                          "slug": "icmimarlik"},
            {"ad": "Moda Tasarim",                         "slug": "modatasarim"},
            {"ad": "Muzik",                                "slug": "muzikgsf"},
            {"ad": "Resim",                                "slug": "resim"},
            {"ad": "Seramik ve Cam Tasarimi",              "slug": "seramik"},
        ],
    },
    {
        "ad": "Hemsirelik Fakultesi",
        "slug": "hemsirelik",
        "dekan_menu": "dekan",
        "bolumler": [
            {"ad": "Hemsirelik",                           "slug": "hemsirelikbolum"},
        ],
    },
    {
        "ad": "Hukuk Fakultesi",
        "slug": "hukuk",
        "dekan_menu": "dekan",
        "bolumler": [
            {"ad": "Kamu Hukuku",                          "slug": "kamuhukuku"},
            {"ad": "Ozel Hukuk",                           "slug": "ozelhukuk"},
        ],
    },
    {
        "ad": "Iktisadi ve Idari Bilimler Fakultesi",
        "slug": "iibf",
        "dekan_menu": "dekan",
        "bolumler": [
            {"ad": "Calisma Ekonomisi ve End. Iliskileri", "slug": "calismaekonomisi"},
            {"ad": "Isletme",                              "slug": "isletme"},
            {"ad": "Iktisat",                              "slug": "iktisat"},
            {"ad": "Kamu Yonetimi",                        "slug": "kamuyonetimi"},
            {"ad": "Maliye",                               "slug": "maliye"},
            {"ad": "Siyaset Bilimi ve Kamu Yonetimi",     "slug": "sbky"},
            {"ad": "Uluslararasi Iliskiler",               "slug": "uluslararasiiliskiler"},
        ],
    },
    {
        "ad": "Ilahiyat Fakultesi",
        "slug": "ilahiyat",
        "dekan_menu": "dekan",
        "bolumler": [
            {"ad": "Felsefe ve Din Bilimleri",             "slug": "felsefevedin"},
            {"ad": "Islam Tarihi ve Sanatlari",            "slug": "islamtarihi"},
            {"ad": "Temel Islam Bilimleri",                "slug": "temelislam"},
        ],
    },
    {
        "ad": "Iletisim Fakultesi",
        "slug": "iletisim",
        "dekan_menu": "dekan",
        "bolumler": [
            {"ad": "Gazetecilik",                          "slug": "gazetecilik"},
            {"ad": "Halkla Iliskiler ve Tanitim",          "slug": "halklailis"},
            {"ad": "Radyo Televizyon ve Sinema",           "slug": "rts"},
            {"ad": "Yeni Medya ve Iletisim",               "slug": "yenimedya"},
        ],
    },
    {
        "ad": "Muhendislik Fakultesi",
        "slug": "muhendislik",
        "dekan_menu": "dekan",
        "bolumler": [
            {"ad": "Biyomedikal Muhendisligi",             "slug": "biyomedikal"},
            {"ad": "Bilgisayar Muhendisligi",              "slug": "bilgisayar"},
            {"ad": "Elektrik Elektronik Muhendisligi",     "slug": "elektrikelektronik"},
            {"ad": "Endustri Muhendisligi",                "slug": "endustrimuh"},
            {"ad": "Insaat Muhendisligi",                  "slug": "insaat"},
            {"ad": "Kimya Muhendisligi",                   "slug": "kimya"},
            {"ad": "Makine Muhendisligi",                  "slug": "makine"},
            {"ad": "Metalurji ve Malzeme Muh.",            "slug": "metalurji"},
            {"ad": "Maden Muhendisligi",                   "slug": "maden"},
            {"ad": "Yazilim Muhendisligi",                 "slug": "yazilim"},
        ],
    },
    {
        "ad": "Saglik Bilimleri Fakultesi",
        "slug": "saglikbilimleri",
        "dekan_menu": "dekan",
        "bolumler": [
            {"ad": "Beslenme ve Diyetetik",                "slug": "beslenme"},
            {"ad": "Cocuk Bakimi ve Genclik Hizmetleri",  "slug": "cocuk.bakimi"},
            {"ad": "Ergoterapi",                           "slug": "ergoterapi"},
            {"ad": "Fizyoterapi ve Rehabilitasyon",        "slug": "fizyoterapi"},
            {"ad": "Saglik Yonetimi",                      "slug": "saglikyonetimi"},
            {"ad": "Sosyal Hizmet",                        "slug": "sosyalhizmet"},
        ],
    },
    {
        "ad": "Spor Bilimleri Fakultesi",
        "slug": "sporbilimleri",
        "dekan_menu": "dekan",
        "bolumler": [
            {"ad": "Beden Egitimi ve Spor Ogretmenligi",  "slug": "beso"},
            {"ad": "Rekreasyon",                           "slug": "rekreasyon"},
            {"ad": "Spor Yonetimi",                        "slug": "sporyonetimi"},
            {"ad": "Antrenorluk Egitimi",                  "slug": "antrenorluk"},
        ],
    },
    {
        "ad": "Tip Fakultesi",
        "slug": "tip",
        "dekan_menu": "dekan",
        "bolumler": [
            # Tıp Fakültesi anabilim dallarını ayrı tarar
            {"ad": "Dahili Tip Bilimleri",                 "slug": "dahilitip"},
            {"ad": "Cerrahi Tip Bilimleri",                "slug": "cerrahitip"},
            {"ad": "Temel Tip Bilimleri",                  "slug": "temeltip"},
        ],
    },
]

# =====================================================================
# YARDIMCI FONKSİYONLAR
# =====================================================================

def get_soup(url, retries=2):
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=12, verify=False)
            r.encoding = "utf-8"
            if r.status_code == 200:
                return BeautifulSoup(r.text, "html.parser")
            else:
                print(f"    [HTTP {r.status_code}] {url}")
                return None
        except Exception as e:
            print(f"    [HATA attempt {attempt+1}] {url} -> {e}")
            time.sleep(1)
    return None

UNVAN_PREFIXES = ["Prof. Dr.", "Doç. Dr.", "Dr. Öğr. Üyesi", "Öğr. Gör. Dr.",
                  "Öğr. Gör.", "Arş. Gör. Dr.", "Arş. Gör.", "Prof.", "Doç."]

def extract_person(soup, keywords):
    """
    Sayfada keyword'ü bul, sonrasındaki satırlarda unvan+isim ara.
    Aynı satırda veya +10 satır içinde.
    """
    if not soup:
        return None
    
    # Önce tüm metni al
    text = soup.get_text(separator="\n")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    
    for i, line in enumerate(lines):
        for kw in keywords:
            if kw.lower() in line.lower():
                # Aynı satırda veya sonraki 12 satırda unvan ara
                for j in range(i, min(i + 12, len(lines))):
                    for prefix in UNVAN_PREFIXES:
                        if prefix in lines[j]:
                            return lines[j]
    return None

def find_menu_url(soup, slug, keywords):
    """
    Ana sayfanın nav menüsünden belirli bir keyword'e ait linki bul.
    Örnek: "Dekan" -> /dishekimligi/menu/948/dekan
    """
    if not soup:
        return None
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True).lower()
        href = a["href"]
        for kw in keywords:
            if kw in text:
                full = href if href.startswith("http") else BASE + href
                if slug in full or "inonu.edu.tr" in full:
                    return full
    return None

def scrape_dekan(f):
    slug = f["slug"]
    print(f"  → Dekan sayfası aranıyor...")
    
    # Fakülte ana sayfasına git, menüden dekan linkini bul
    ana_soup = get_soup(f"{BASE}/{slug}")
    time.sleep(0.5)
    
    dekan_url = None
    if ana_soup:
        dekan_url = find_menu_url(ana_soup, slug, ["dekan"])
    
    # Deneme URL'leri
    attempts = []
    if dekan_url:
        attempts.append(dekan_url)
    
    # Yönetim sayfasını da dene
    if ana_soup:
        yonetim_url = find_menu_url(ana_soup, slug, ["yönetim", "yonetim"])
        if yonetim_url:
            attempts.append(yonetim_url)
    
    # Genel fallback'ler
    attempts += [
        f"{BASE}/{slug}/menu/dekan",
        f"{BASE}/{slug}/yonetim",
    ]
    
    for url in attempts:
        soup = get_soup(url)
        if not soup:
            continue
        person = extract_person(soup, ["Dekan", "dekan"])
        if person:
            print(f"    ✓ Dekan: {person}")
            return {"ad": person, "url": url}
        time.sleep(0.3)
    
    print(f"    ✗ Dekan bulunamadı")
    return {"ad": None, "url": None}

def scrape_bolum(bolum_slug, bolum_ad):
    """
    Bir bölümün ana sayfasına git.
    Oradan bölüm başkanı ve sekreter sayfalarını bul.
    """
    bolum_url = f"{BASE}/{bolum_slug}"
    ana_soup = get_soup(bolum_url)
    time.sleep(0.4)
    
    baskan = None
    sekreter = None
    baskan_url = None
    sekreter_url = None
    
    if ana_soup:
        # Menüden Bölüm Başkanı linkini bul
        baskan_url = find_menu_url(ana_soup, bolum_slug,
                                   ["bölüm başkanı", "bolum baskani", "başkan"])
        # Menüden Sekreter linkini bul
        sekreter_url = find_menu_url(ana_soup, bolum_slug,
                                     ["sekreter"])
    
    # Başkan
    if baskan_url:
        bs = get_soup(baskan_url)
        time.sleep(0.3)
        baskan = extract_person(bs, ["Bölüm Başkanı", "Başkan", "bolum baskani"])
    
    # Sekreter
    if sekreter_url:
        ss = get_soup(sekreter_url)
        time.sleep(0.3)
        sekreter = extract_person(ss, ["Sekreter", "sekreter"])
    
    return {
        "ad": bolum_ad,
        "slug": bolum_slug,
        "url": bolum_url,
        "bolum_baskani": baskan,
        "bolum_baskani_url": baskan_url,
        "bolum_sekreteri": sekreter,
        "bolum_sekreteri_url": sekreter_url,
    }

# =====================================================================
# MAIN
# =====================================================================

def main():
    sonuc = []
    
    for f in FAKULTELER:
        print(f"\n{'='*60}")
        print(f"FAKÜLTE: {f['ad']} [{f['slug']}]")
        print(f"{'='*60}")
        
        # Dekan
        dekan_bilgi = scrape_dekan(f)
        
        # Bölümler
        bolumler_sonuc = []
        for b in f["bolumler"]:
            print(f"  → Bölüm: {b['ad']} [{b['slug']}]")
            bilgi = scrape_bolum(b["slug"], b["ad"])
            print(f"      Başkan : {bilgi['bolum_baskani']}")
            print(f"      Sekreter: {bilgi['bolum_sekreteri']}")
            bolumler_sonuc.append(bilgi)
            time.sleep(0.5)
        
        sonuc.append({
            "fakulte_adi": f["ad"],
            "fakulte_slug": f["slug"],
            "fakulte_url": f"{BASE}/{f['slug']}",
            "dekan": dekan_bilgi["ad"],
            "dekan_url": dekan_bilgi["url"],
            "bolumler": bolumler_sonuc,
        })
        
        time.sleep(1)
    
    # JSON'a yaz
    with open("inonu_personel.json", "w", encoding="utf-8") as fp:
        json.dump(sonuc, fp, ensure_ascii=False, indent=2)
    
    # İstatistik
    print("\n" + "="*60)
    print("✅ TAMAMLANDI → inonu_personel.json")
    print("="*60)
    toplam_bolum = sum(len(f["bolumler"]) for f in sonuc)
    eksik_dekan  = [f["fakulte_adi"] for f in sonuc if not f["dekan"]]
    eksik_baskan = [(f["fakulte_adi"], b["ad"])
                    for f in sonuc for b in f["bolumler"] if not b["bolum_baskani"]]
    eksik_sek    = [(f["fakulte_adi"], b["ad"])
                    for f in sonuc for b in f["bolumler"] if not b["bolum_sekreteri"]]
    
    print(f"  Toplam fakülte  : {len(sonuc)}")
    print(f"  Toplam bölüm    : {toplam_bolum}")
    print(f"  Eksik dekan     : {len(eksik_dekan)}")
    print(f"  Eksik başkan    : {len(eksik_baskan)}")
    print(f"  Eksik sekreter  : {len(eksik_sek)}")
    
    if eksik_dekan:
        print("\n⚠️  Dekan bulunamayan fakülteler:")
        for x in eksik_dekan:
            print(f"    - {x}")
    
    if eksik_baskan:
        print("\n⚠️  Başkan bulunamayan bölümler:")
        for fad, bad in eksik_baskan:
            print(f"    - {fad} > {bad}")
    
    if eksik_sek:
        print("\n⚠️  Sekreter bulunamayan bölümler:")
        for fad, bad in eksik_sek:
            print(f"    - {fad} > {bad}")

if __name__ == "__main__":
    main()