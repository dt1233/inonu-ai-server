#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İNÖNÜ AI │ url_config.py
"""

from dataclasses import dataclass, field
from enum import Enum


class CrawlType(str, Enum):
    API_JSON    = "api_json"
    API_STAFF   = "api_staff"
    API_SSS     = "api_sss"
    HTML_STATIC = "html_static"
    HTML_JS     = "html_js"


class CrawlFrequency(str, Enum):
    DAILY   = "daily"
    WEEKLY  = "weekly"
    MONTHLY = "monthly"
    ONCE    = "once"


@dataclass
class UrlTarget:
    key:         str
    label:       str
    url:         str
    crawl_type:  CrawlType
    frequency:   CrawlFrequency
    priority:    int = 1
    js_wait_ms:  int = 1000
    extra:       dict = field(default_factory=dict)


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
    }
)

STATIC_CONTENT_SOURCES: list[UrlTarget] = [
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
        key="personeller", label="Personeller",
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

ALL_TARGETS: list[UrlTarget] = [ANNOUNCEMENT_API] + STATIC_CONTENT_SOURCES

DAILY_TARGETS   = [t for t in ALL_TARGETS if t.frequency == CrawlFrequency.DAILY]
WEEKLY_TARGETS  = [t for t in ALL_TARGETS if t.frequency == CrawlFrequency.WEEKLY]
MONTHLY_TARGETS = [t for t in ALL_TARGETS if t.frequency == CrawlFrequency.MONTHLY]