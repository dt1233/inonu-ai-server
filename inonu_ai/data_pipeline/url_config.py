#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔═════════════════════════════════════════════════════════════════╗
║ İNÖNÜ AI │ url_config.py                                       ║
║ Tüm İnönü Üniversitesi Birimleri — Genişletilmiş               ║
╚═════════════════════════════════════════════════════════════════╝

panel.inonu.edu.tr unit parametreleri:
  - /servlet/staff?unit=<unit_key>       → personel listesi
  - /servlet/announcement?unit=<unit_key> → birim duyuruları
  - /servlet/content?id=<content_id>     → statik içerik

AVESİS unitId parametreleri (avesis.inonu.edu.tr):
  - Her fakülte/bölüm için ayrı unitId
"""

from dataclasses import dataclass, field
from enum import Enum


# ─────────────────────────────────────────────────────────────────
# ENUM'LAR
# ─────────────────────────────────────────────────────────────────

class CrawlType(str, Enum):
    API_JSON    = "api_json"      # panel.inonu.edu.tr JSON API
    API_STAFF   = "api_staff"     # panel.inonu.edu.tr personel API
    API_SSS     = "api_sss"       # panel.inonu.edu.tr SSS menü API
    HTML_STATIC = "html_static"   # Düz HTML sayfası (requests + BS4)
    HTML_JS     = "html_js"       # JavaScript gerektiren sayfa (Playwright)
    AVESIS      = "avesis"        # AVESİS akademik personel sistemi


class CrawlFrequency(str, Enum):
    DAILY   = "daily"
    WEEKLY  = "weekly"
    MONTHLY = "monthly"
    ONCE    = "once"


# ─────────────────────────────────────────────────────────────────
# VERİ YAPISI
# ─────────────────────────────────────────────────────────────────

@dataclass
class UrlTarget:
    key:         str
    label:       str
    url:         str
    crawl_type:  CrawlType
    frequency:   CrawlFrequency
    priority:    int  = 1          # 1=en yüksek, 5=en düşük
    js_wait_ms:  int  = 1500
    extra:       dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────
# TEMEL PANEL API — Öğrenci İşleri Duyuru
# ─────────────────────────────────────────────────────────────────

ANNOUNCEMENT_API = UrlTarget(
    key        = "duyurular_api",
    label      = "Öğrenci DB Duyuruları",
    url        = "https://panel.inonu.edu.tr/servlet/announcement?type=list&lang=tr&page={page}&unit=ogrencidb",
    crawl_type = CrawlType.API_JSON,
    frequency  = CrawlFrequency.DAILY,
    priority   = 1,
    extra      = {
        "detail_url": "https://panel.inonu.edu.tr/servlet/announcement?type=get&lang=tr&id={id}",
        "base_url":   "https://panel.inonu.edu.tr",
        "unit":       "ogrencidb",
        "paginated":  True,
    },
)


# ─────────────────────────────────────────────────────────────────
# ÖĞRENCİ İŞLERİ — Mevcut (korundu)
# ─────────────────────────────────────────────────────────────────

OGRENCIDB_TARGETS: list[UrlTarget] = [
    UrlTarget(
        key="tarihce", label="Tarihçe",
        url="https://panel.inonu.edu.tr/servlet/content?id=16204&lang=tr",
        crawl_type=CrawlType.API_JSON, frequency=CrawlFrequency.MONTHLY, priority=3,
    ),
    UrlTarget(
        key="oryantasyon", label="Oryantasyon",
        url="https://panel.inonu.edu.tr/servlet/content?id=28600&lang=tr",
        crawl_type=CrawlType.API_JSON, frequency=CrawlFrequency.WEEKLY, priority=2,
    ),
    UrlTarget(
        key="personeller", label="Öğrenci İşleri Personelleri",
        url="https://panel.inonu.edu.tr/servlet/staff?unit=ogrencidb",
        crawl_type=CrawlType.API_STAFF, frequency=CrawlFrequency.WEEKLY, priority=2,
    ),
    UrlTarget(
        key="secmeli_dersler", label="Seçmeli Dersler",
        url="https://panel.inonu.edu.tr/servlet/content?id=24674&lang=tr",
        crawl_type=CrawlType.API_JSON, frequency=CrawlFrequency.WEEKLY, priority=2,
    ),
    UrlTarget(
        key="misyon_vizyon", label="Misyon & Vizyon",
        url="https://panel.inonu.edu.tr/servlet/content?id=1449&lang=tr",
        crawl_type=CrawlType.API_JSON, frequency=CrawlFrequency.MONTHLY, priority=3,
    ),
    UrlTarget(
        key="secmeli_sinav_programi", label="Seçmeli Ders Sınav Programı",
        url="https://panel.inonu.edu.tr/servlet/content?id=24678&lang=tr",
        crawl_type=CrawlType.API_JSON, frequency=CrawlFrequency.WEEKLY, priority=2,
    ),
    UrlTarget(
        key="ic_kontrol", label="İç Kontrol",
        url="https://panel.inonu.edu.tr/servlet/content?id=32074&lang=tr",
        crawl_type=CrawlType.API_JSON, frequency=CrawlFrequency.MONTHLY, priority=3,
    ),
    UrlTarget(
        key="usd_dersler", label="ÜSD Dersler",
        url="https://panel.inonu.edu.tr/servlet/content?id=24677&lang=tr",
        crawl_type=CrawlType.API_JSON, frequency=CrawlFrequency.WEEKLY, priority=2,
    ),
    UrlTarget(
        key="sss", label="Sıkça Sorulan Sorular",
        url="https://panel.inonu.edu.tr/servlet/menu?type=inside&id=1636",
        crawl_type=CrawlType.API_SSS, frequency=CrawlFrequency.MONTHLY, priority=3,
        extra={"parent_id": 1636},
    ),
]


# ─────────────────────────────────────────────────────────────────
# REKTÖRLÜK VE MERKEZ BİRİMLER
# ─────────────────────────────────────────────────────────────────

REKTORLUK_TARGETS: list[UrlTarget] = [
    UrlTarget(
        key="rektorluk_personel", label="Rektörlük Personeli",
        url="https://panel.inonu.edu.tr/servlet/staff?unit=rektorluk",
        crawl_type=CrawlType.API_STAFF, frequency=CrawlFrequency.WEEKLY, priority=2,
    ),
    UrlTarget(
        key="rektorluk_duyuru", label="Rektörlük Duyuruları",
        url="https://panel.inonu.edu.tr/servlet/announcement?type=list&lang=tr&page={page}&unit=rektorluk",
        crawl_type=CrawlType.API_JSON, frequency=CrawlFrequency.DAILY, priority=1,
        extra={"paginated": True, "unit": "rektorluk"},
    ),
    UrlTarget(
        key="genel_sekreterlik_personel", label="Genel Sekreterlik Personeli",
        url="https://panel.inonu.edu.tr/servlet/staff?unit=genelsek",
        crawl_type=CrawlType.API_STAFF, frequency=CrawlFrequency.WEEKLY, priority=2,
    ),
    UrlTarget(
        key="akademik_takvim", label="Akademik Takvim",
        url="https://panel.inonu.edu.tr/servlet/content?id=1451&lang=tr",
        crawl_type=CrawlType.API_JSON, frequency=CrawlFrequency.WEEKLY, priority=1,
    ),
    UrlTarget(
        key="bahar_yariyili", label="Bahar Yarıyılı Akademik Takvimi",
        url="https://www.inonu.edu.tr/ogrenci/menu/23280/bahar-yariyili",
        crawl_type=CrawlType.HTML_STATIC, frequency=CrawlFrequency.WEEKLY, priority=1,
    ),
    UrlTarget(
        key="guz_yariyili", label="Güz Yarıyılı Akademik Takvimi",
        url="https://www.inonu.edu.tr/ogrenci/menu/23279/guz-yariyili",
        crawl_type=CrawlType.HTML_STATIC, frequency=CrawlFrequency.WEEKLY, priority=1,
    ),
]


# ─────────────────────────────────────────────────────────────────
# FAKÜLTELER
# (unit_key, label, avesis_unit_id) tuple
# ─────────────────────────────────────────────────────────────────

FAKULTELER = [
    ("fen.edebiyat",   "Fen Edebiyat Fakültesi",             155),
    ("muhendislik",    "Mühendislik Fakültesi",               375),
    ("tip",            "Tıp Fakültesi",                       517),
    ("dishekimligi",   "Diş Hekimliği Fakültesi",             77),
    ("eczacilik",      "Eczacılık Fakültesi",                  87),
    ("egitim",         "Eğitim Fakültesi",                    116),
    ("iibf",           "İktisadi ve İdari Bilimler Fakültesi", 263),
    ("ilahiyat",       "İlahiyat Fakültesi",                   297),
    ("gsf",            "Güzel Sanatlar ve Tasarım Fakültesi", 212),
    ("sporbilimleri",  "Spor Bilimleri Fakültesi",            51),
    ("hukuk",          "Hukuk Fakültesi",                     243),
    ("sbf",            "Sağlık Bilimleri Fakültesi",          445),
    ("veteriner",      "Veteriner Fakültesi",                  None),
    ("mimarlik",       "Mimarlık Fakültesi",                   None),
    ("iletisim",       "İletişim Fakültesi",                   320),
]


def _fakulte_targets() -> list[UrlTarget]:
    targets = []
    for unit_key, label, avesis_id in FAKULTELER:
        # Duyurular
        targets.append(UrlTarget(
            key=f"{unit_key}_duyuru", label=f"{label} Duyuruları",
            url=f"https://panel.inonu.edu.tr/servlet/announcement?type=list&lang=tr&page={{page}}&unit={unit_key}",
            crawl_type=CrawlType.API_JSON, frequency=CrawlFrequency.DAILY, priority=1,
            extra={"paginated": True, "unit": unit_key, "fakulte": label},
        ))
        # Personel (panel API)
        targets.append(UrlTarget(
            key=f"{unit_key}_personel", label=f"{label} Personeli",
            url=f"https://panel.inonu.edu.tr/servlet/staff?unit={unit_key}",
            crawl_type=CrawlType.API_STAFF, frequency=CrawlFrequency.WEEKLY, priority=2,
            extra={"fakulte": label},
        ))
        # AVESİS akademik kadro
        if avesis_id is not None:
            targets.append(UrlTarget(
                key=f"{unit_key}_avesis", label=f"{label} AVESİS Akademik Kadro",
                url=f"https://avesis.inonu.edu.tr/unitreport/reports?unitId={avesis_id}",
                crawl_type=CrawlType.AVESIS, frequency=CrawlFrequency.WEEKLY, priority=2,
                js_wait_ms=3000,
                extra={"unit_id": avesis_id, "fakulte": label},
            ))
        # Fakülte ana sayfası (HTML)
        targets.append(UrlTarget(
            key=f"{unit_key}_anasayfa", label=f"{label} Ana Sayfası",
            url=f"https://www.inonu.edu.tr/{unit_key}",
            crawl_type=CrawlType.HTML_STATIC, frequency=CrawlFrequency.MONTHLY, priority=4,
            extra={"fakulte": label},
        ))
    return targets

FAKULTE_TARGETS: list[UrlTarget] = _fakulte_targets()


# ─────────────────────────────────────────────────────────────────
# ENSTİTÜLER
# ─────────────────────────────────────────────────────────────────

ENSTITU_LISTESI = [
    ("fbe",                "Fen Bilimleri Enstitüsü",      144),
    ("sosyalbilimler",     "Sosyal Bilimler Enstitüsü",     480),
    ("egitimbilimleri",    "Eğitim Bilimleri Enstitüsü",    105),
    ("saglikbilimleriens", "Sağlık Bilimleri Enstitüsü",    422),
]


def _enstitu_targets() -> list[UrlTarget]:
    targets = []
    for unit_key, label, avesis_id in ENSTITU_LISTESI:
        targets.append(UrlTarget(
            key=f"{unit_key}_duyuru", label=f"{label} Duyuruları",
            url=f"https://panel.inonu.edu.tr/servlet/announcement?type=list&lang=tr&page={{page}}&unit={unit_key}",
            crawl_type=CrawlType.API_JSON, frequency=CrawlFrequency.DAILY, priority=2,
            extra={"paginated": True, "unit": unit_key},
        ))
        targets.append(UrlTarget(
            key=f"{unit_key}_personel", label=f"{label} Personeli",
            url=f"https://panel.inonu.edu.tr/servlet/staff?unit={unit_key}",
            crawl_type=CrawlType.API_STAFF, frequency=CrawlFrequency.WEEKLY, priority=2,
        ))
        targets.append(UrlTarget(
            key=f"{unit_key}_avesis", label=f"{label} AVESİS",
            url=f"https://avesis.inonu.edu.tr/unitreport/reports?unitId={avesis_id}",
            crawl_type=CrawlType.AVESIS, frequency=CrawlFrequency.WEEKLY, priority=3,
            js_wait_ms=3000,
            extra={"unit_id": avesis_id},
        ))
    return targets

ENSTITU_TARGETS: list[UrlTarget] = _enstitu_targets()


# ─────────────────────────────────────────────────────────────────
# AVESIS SADECE (PANEL API'DE OLMAYAN / EKSİK OLAN BİRİMLER)
# ─────────────────────────────────────────────────────────────────

AVESIS_ONLY_BIRIMLER = [
    ("hemsirelik", "Hemşirelik Fakültesi", 99896503),
    ("malatya_saglik_yo", "Malatya Sağlık Yüksekokulu", 368),
    ("yabanci_diller_yo", "Yabancı Diller Yüksekokulu", 564),
    ("alevilik_ens", "Alevilik Araştırmaları Enstitüsü", 99896904),
    ("karaciger_ens", "Karaciğer Nakli Enstitüsü Müdürlüğü", 99896415),
    ("adalet_myo", "Adalet Meslek Yüksekokulu", 2),
    ("kale_myo", "Kale Turizm ve Otel İşletmeciliği Meslek Yüksekokulu", 334),
    ("malatya_myo", "Malatya Meslek Yüksekokulu", 345),
    ("osb_myo", "Osb Meslek Yüksekokulu", 585),
    ("saglik_hizm_myo", "Sağlık Hizmetleri Meslek Yüksekokulu", 461),
    ("beslenme_diyetetik", "Beslenme ve Diyetetik", 317276),
    ("devlet_konservatuvari", "Devlet Konservatuvarı", 73),
    ("hemsirelik_esaslari", "Hemşirelik Esasları Anabilim Dalı", 3265),
    ("reklamcilik_tanitim", "Reklamcılık ve Tanıtım", 201277),
    ("rektorluk_avesis", "Rektörlük (AVESİS)", 419),
]

def _avesis_only_targets() -> list[UrlTarget]:
    targets = []
    for unit_key, label, avesis_id in AVESIS_ONLY_BIRIMLER:
        targets.append(UrlTarget(
            key=f"{unit_key}_avesis", label=f"{label} AVESİS",
            url=f"https://avesis.inonu.edu.tr/unitreport/reports?unitId={avesis_id}",
            crawl_type=CrawlType.AVESIS, frequency=CrawlFrequency.WEEKLY, priority=2,
            js_wait_ms=3000,
            extra={"unit_id": avesis_id, "birim": label},
        ))
    return targets

AVESIS_ONLY_TARGETS: list[UrlTarget] = _avesis_only_targets()


# ─────────────────────────────────────────────────────────────────
# MYO'LAR
# ─────────────────────────────────────────────────────────────────

MYO_LISTESI = [
    ("battalgazi",   "Battalgazi MYO"),
    ("dogansehir",   "Doğanşehir Vahap Küçük MYO"),
    ("hekimhan",     "Hekimhan MYO"),
    ("arapgir",      "Arapgir MYO"),
    ("puturge",      "Pütürge MYO"),
    ("kale",         "Kale MYO"),
    ("darende",      "Darende Bekir Ilıcak MYO"),
    ("saglikhizm",   "Sağlık Hizmetleri MYO"),
    ("teknik",       "Teknik Bilimler MYO"),
    ("sosyalbilmyo", "Sosyal Bilimler MYO"),
]


def _myo_targets() -> list[UrlTarget]:
    targets = []
    for unit_key, label in MYO_LISTESI:
        targets.append(UrlTarget(
            key=f"{unit_key}_duyuru", label=f"{label} Duyuruları",
            url=f"https://panel.inonu.edu.tr/servlet/announcement?type=list&lang=tr&page={{page}}&unit={unit_key}",
            crawl_type=CrawlType.API_JSON, frequency=CrawlFrequency.DAILY, priority=2,
            extra={"paginated": True, "unit": unit_key},
        ))
        targets.append(UrlTarget(
            key=f"{unit_key}_personel", label=f"{label} Personeli",
            url=f"https://panel.inonu.edu.tr/servlet/staff?unit={unit_key}",
            crawl_type=CrawlType.API_STAFF, frequency=CrawlFrequency.WEEKLY, priority=3,
        ))
    return targets

MYO_TARGETS: list[UrlTarget] = _myo_targets()


# ─────────────────────────────────────────────────────────────────
# MERKEZ BİRİMLER (SKS, Kütüphane, UZEM, vb.)
# ─────────────────────────────────────────────────────────────────

BIRIM_TARGETS: list[UrlTarget] = [
    # SKS
    UrlTarget(
        key="sks_yemekhane_menu", label="SKS Yemekhane Günlük Menü",
        url="https://www.inonu.edu.tr/sks/menu/1677/yemek-listesi",
        crawl_type=CrawlType.HTML_JS, frequency=CrawlFrequency.DAILY, priority=1,
        js_wait_ms=3000,
    ),
    UrlTarget(
        key="sks_duyuru", label="SKS Duyuruları",
        url="https://panel.inonu.edu.tr/servlet/announcement?type=list&lang=tr&page={page}&unit=sks",
        crawl_type=CrawlType.API_JSON, frequency=CrawlFrequency.DAILY, priority=1,
        extra={"paginated": True, "unit": "sks"},
    ),
    UrlTarget(
        key="sks_personel", label="SKS Personeli",
        url="https://panel.inonu.edu.tr/servlet/staff?unit=sks",
        crawl_type=CrawlType.API_STAFF, frequency=CrawlFrequency.WEEKLY, priority=2,
    ),
    # Kütüphane
    UrlTarget(
        key="kutuphane_duyuru", label="Kütüphane Duyuruları",
        url="https://panel.inonu.edu.tr/servlet/announcement?type=list&lang=tr&page={page}&unit=kutuphane",
        crawl_type=CrawlType.API_JSON, frequency=CrawlFrequency.DAILY, priority=2,
        extra={"paginated": True, "unit": "kutuphane"},
    ),
    UrlTarget(
        key="kutuphane_personel", label="Kütüphane Personeli",
        url="https://panel.inonu.edu.tr/servlet/staff?unit=kutuphane",
        crawl_type=CrawlType.API_STAFF, frequency=CrawlFrequency.WEEKLY, priority=2,
    ),
    UrlTarget(
        key="kutuphane_site", label="Kütüphane Web Sitesi",
        url="https://kutuphane.inonu.edu.tr",
        crawl_type=CrawlType.HTML_STATIC, frequency=CrawlFrequency.MONTHLY, priority=3,
    ),
    # UZEM
    UrlTarget(
        key="uzem_duyuru", label="UZEM Duyuruları",
        url="https://panel.inonu.edu.tr/servlet/announcement?type=list&lang=tr&page={page}&unit=uzem",
        crawl_type=CrawlType.API_JSON, frequency=CrawlFrequency.DAILY, priority=2,
        extra={"paginated": True, "unit": "uzem"},
    ),
    UrlTarget(
        key="uzem_personel", label="UZEM Personeli",
        url="https://panel.inonu.edu.tr/servlet/staff?unit=uzem",
        crawl_type=CrawlType.API_STAFF, frequency=CrawlFrequency.WEEKLY, priority=2,
    ),
    # Uluslararası İlişkiler
    UrlTarget(
        key="dis_iliskiler_duyuru", label="Uluslararası İlişkiler Duyuruları",
        url="https://panel.inonu.edu.tr/servlet/announcement?type=list&lang=tr&page={page}&unit=disisleri",
        crawl_type=CrawlType.API_JSON, frequency=CrawlFrequency.DAILY, priority=1,
        extra={"paginated": True, "unit": "disisleri"},
    ),
    UrlTarget(
        key="dis_iliskiler_personel", label="Uluslararası İlişkiler Personeli",
        url="https://panel.inonu.edu.tr/servlet/staff?unit=disisleri",
        crawl_type=CrawlType.API_STAFF, frequency=CrawlFrequency.WEEKLY, priority=2,
    ),
    # BAPK
    UrlTarget(
        key="bapk_duyuru", label="BAPK Duyuruları",
        url="https://panel.inonu.edu.tr/servlet/announcement?type=list&lang=tr&page={page}&unit=bapk",
        crawl_type=CrawlType.API_JSON, frequency=CrawlFrequency.DAILY, priority=2,
        extra={"paginated": True, "unit": "bapk"},
    ),
    # Kariyer Merkezi
    UrlTarget(
        key="kariyer_duyuru", label="Kariyer Merkezi Duyuruları",
        url="https://panel.inonu.edu.tr/servlet/announcement?type=list&lang=tr&page={page}&unit=kariyer",
        crawl_type=CrawlType.API_JSON, frequency=CrawlFrequency.DAILY, priority=2,
        extra={"paginated": True, "unit": "kariyer"},
    ),
    # TOTM
    UrlTarget(
        key="totm_duyuru", label="TOTM Duyuruları",
        url="https://panel.inonu.edu.tr/servlet/announcement?type=list&lang=tr&page={page}&unit=totm",
        crawl_type=CrawlType.API_JSON, frequency=CrawlFrequency.DAILY, priority=2,
        extra={"paginated": True, "unit": "totm"},
    ),
    # Öğrenci Toplulukları
    UrlTarget(
        key="ogrenci_topluluklar", label="Öğrenci Toplulukları",
        url="https://ogrencitopluluklari.inonu.edu.tr",
        crawl_type=CrawlType.HTML_STATIC, frequency=CrawlFrequency.MONTHLY, priority=3,
    ),
]


# ─────────────────────────────────────────────────────────────────
# BİRLEŞTİRİLMİŞ LİSTELER
# ─────────────────────────────────────────────────────────────────

STATIC_CONTENT_SOURCES: list[UrlTarget] = (
    OGRENCIDB_TARGETS
    + REKTORLUK_TARGETS
    + BIRIM_TARGETS
)

ALL_TARGETS: list[UrlTarget] = (
    [ANNOUNCEMENT_API]
    + STATIC_CONTENT_SOURCES
    + FAKULTE_TARGETS
    + ENSTITU_TARGETS
    + AVESIS_ONLY_TARGETS
    + MYO_TARGETS
)

# Frekansa göre gruplar
DAILY_TARGETS   = [t for t in ALL_TARGETS if t.frequency == CrawlFrequency.DAILY]
WEEKLY_TARGETS  = [t for t in ALL_TARGETS if t.frequency == CrawlFrequency.WEEKLY]
MONTHLY_TARGETS = [t for t in ALL_TARGETS if t.frequency == CrawlFrequency.MONTHLY]

# Tipe göre gruplar
AVESIS_TARGETS      = [t for t in ALL_TARGETS if t.crawl_type == CrawlType.AVESIS]
HTML_STATIC_TARGETS = [t for t in ALL_TARGETS if t.crawl_type == CrawlType.HTML_STATIC]
HTML_JS_TARGETS     = [t for t in ALL_TARGETS if t.crawl_type == CrawlType.HTML_JS]
API_TARGETS         = [t for t in ALL_TARGETS if t.crawl_type in (
    CrawlType.API_JSON, CrawlType.API_STAFF, CrawlType.API_SSS
)]


if __name__ == "__main__":
    print(f"Toplam hedef sayısı  : {len(ALL_TARGETS)}")
    print(f"  Günlük             : {len(DAILY_TARGETS)}")
    print(f"  Haftalık           : {len(WEEKLY_TARGETS)}")
    print(f"  Aylık              : {len(MONTHLY_TARGETS)}")
    print(f"  AVESİS             : {len(AVESIS_TARGETS)}")
    print(f"  HTML Statik        : {len(HTML_STATIC_TARGETS)}")
    print(f"  Panel API          : {len(API_TARGETS)}")