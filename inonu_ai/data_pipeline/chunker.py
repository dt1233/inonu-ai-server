#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İNÖNÜ AI │ chunker.py
2 Stratejili Akıllı Parçalama — AVESİS desteği eklenmiş
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)
from loguru import logger

# ─────────────────────────────────────────────────────────────────
# AYARLAR
# ─────────────────────────────────────────────────────────────────

CHUNK_SIZE    = 1000
CHUNK_OVERLAP = 150
MIN_CHUNK_LEN = 40


# ─────────────────────────────────────────────────────────────────
# VERİ YAPISI
# ─────────────────────────────────────────────────────────────────

@dataclass
class Chunk:
    text:        str
    source_url:  str
    source_key:  str
    doc_id:      str | int
    chunk_index: int
    metadata:    dict
    created_at:  str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─────────────────────────────────────────────────────────────────
# SPLITTER'LAR
# ─────────────────────────────────────────────────────────────────

_HEADER_SPLITTER = MarkdownHeaderTextSplitter(
    headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")],
    strip_headers=False,
)

_RECURSIVE_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", "! ", "? ", ", ", " ", ""],
    length_function=len,
)


# ─────────────────────────────────────────────────────────────────
# FORMAT YARDIMCILARI
# ─────────────────────────────────────────────────────────────────

def _staff_to_text(staff_list: list[dict]) -> str:
    """
    Panel API personel listesini metin formatına dönüştür.
    Her kişi tek satır: "Ad Soyad | Unvan | Bölüm | Görev | E-posta | Tel"
    """
    lines = []
    for p in staff_list:
        parts = [p.get("ad_soyad", "")]
        if p.get("unvan"):
            parts.append(p["unvan"])
        if p.get("departman"):
            parts.append(p["departman"])
        if p.get("gorev"):
            parts.append(f"Görev: {p['gorev']}")
        if p.get("email"):
            parts.append(f"E-posta: {p['email']}")
        if p.get("telefon"):
            parts.append(f"Tel: {p['telefon']}")
        lines.append(" | ".join(filter(None, parts)))
    return "\n".join(lines)


def _avesis_staff_to_text(staff_list: list[dict]) -> str:
    """
    AVESİS personel listesini metin formatına dönüştür.
    Panel API formatından daha zengin: çalışma alanları + profil URL.
    """
    lines = []
    for p in staff_list:
        parts = [p.get("ad_soyad", "")]
        if p.get("unvan"):
            parts.append(p["unvan"])
        if p.get("idari_gorev"):
            parts.append(f"İdari Görev: {p['idari_gorev']}")
        if p.get("bolum"):
            parts.append(f"Bölüm: {p['bolum']}")
        if p.get("fakulte"):
            parts.append(f"Fakülte: {p['fakulte']}")
        if p.get("email"):
            parts.append(f"E-posta: {p['email']}")
        if p.get("telefon"):
            parts.append(f"Tel: {p['telefon']}")
        if p.get("calisma_alanlari"):
            alans = ", ".join(p["calisma_alanlari"][:5])
            parts.append(f"Alanlar: {alans}")
        if p.get("profil_url"):
            parts.append(f"Profil: {p['profil_url']}")
        lines.append(" | ".join(filter(None, parts)))
    return "\n".join(lines)


def _sss_to_text(sss_dict: dict) -> str:
    """SSS sözlüğünü Markdown formatına dönüştür."""
    blocks = []
    for cat_data in sss_dict.values():
        title = cat_data.get("baslik", "")
        if title:
            blocks.append(f"## {title}")
        items = cat_data.get("content", [])
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                if item.get("baslik"):
                    blocks.append(f"### {item['baslik']}")
                if item.get("icerik"):
                    blocks.append(item["icerik"])
    return "\n\n".join(blocks)


# ─────────────────────────────────────────────────────────────────
# CHUNKER SINIFI
# ─────────────────────────────────────────────────────────────────

class Chunker:

    def chunk_announcements(self, records: list[dict]) -> list[Chunk]:
        """Duyuru ve eklerini chunk'la."""
        all_chunks: list[Chunk] = []

        for rec in records:
            unit = rec.get("unit", "")
            ann_id = rec.get("ann_id") or rec.get("id", "")
            
            # Ana duyuru metnini chunk'la
            ana_metin = rec.get("content") or ""
            source_key = f"announcement:{unit}"
            
            # Ortak metadata
            base_meta = {
                "unit": unit,
                "unit_label": rec.get("unit_label", ""),
                "fakulte": rec.get("fakulte", ""),
                "source_fakulte": rec.get("source_fakulte", ""),
                "detected_fakulte": rec.get("detected_fakulte", ""),
                "scope": rec.get("scope", "unknown"),
                "doc_type": "announcement",
                "page_no": None,
                "page_count": None,
                "ann_id": ann_id,
                "title": rec.get("title", ""),
                "published_at": rec.get("published_at", "") or rec.get("updated", ""),
                "source_url": rec.get("source_url") or rec.get("sourceUrl", ""),
                "pdf_url": "",
                "content_hash": rec.get("content_hash", "")
            }

            if ana_metin.strip() and ana_metin not in ("[İçerik alınamadı]", "Bu duyuru doğrudan bir PDF dosyasıdır."):
                all_chunks.extend(
                    self._chunk_text(ana_metin, base_meta["source_url"], source_key, str(ann_id), base_meta.copy())
                )

            for i, att in enumerate(rec.get("attachments", [])):
                pages = att.get("pages")
                if pages:
                    for page in pages:
                        # Skip empty/ocr_required
                        if page.get("pdf_text_quality") != "text" or not page.get("content"):
                            continue
                            
                        page_no = page.get("page_no")
                        page_source_key = f"pdf_page:{unit}:{ann_id}:{page_no}"
                        
                        page_meta = {
                            "unit": page.get("unit", unit),
                            "unit_label": page.get("unit_label", base_meta["unit_label"]),
                            "fakulte": page.get("fakulte", base_meta["fakulte"]),
                            "source_fakulte": page.get("source_fakulte", base_meta["source_fakulte"]),
                            "detected_fakulte": page.get("detected_fakulte", ""),
                            "scope": page.get("scope", base_meta["scope"]),
                            "doc_type": "pdf_page",
                            "page_no": page_no,
                            "page_count": page.get("page_count"),
                            "ann_id": ann_id,
                            "title": page.get("title", base_meta["title"]),
                            "published_at": page.get("published_at", base_meta["published_at"]),
                            "source_url": page.get("source_url", base_meta["source_url"]),
                            "pdf_url": page.get("pdf_url", att.get("url", "")),
                            "content_hash": page.get("content_hash", "")
                        }
                        
                        all_chunks.extend(
                            self._chunk_text(page.get("content"), page_meta["pdf_url"] or page_meta["source_url"], page_source_key, f"{ann_id}_p{page_no}", page_meta)
                        )
                else:
                    # Legacy fallback
                    att_text = att.get("content", "")
                    if not att_text or att_text in ("[PDF Okunamadı]", "[İçerik alınamadı]"):
                        continue
                    att_meta = base_meta.copy()
                    att_meta["doc_type"] = "pdf_attachment"
                    att_meta["pdf_url"] = att.get("url", "")
                    att_source_key = f"pdf_attachment:{unit}:{ann_id}:{i}"
                    
                    all_chunks.extend(self._chunk_text(
                        f"{base_meta['title']} (Ek {i + 1})\n\n{att_text}",
                        att_meta["pdf_url"] or att_meta["source_url"],
                        att_source_key,
                        f"{ann_id}_att{i}",
                        att_meta
                    ))

        logger.info(f"Duyuru chunk: {len(records)} kayıt → {len(all_chunks)} chunk")
        return all_chunks

    def chunk_static_contents(self, records: list[dict]) -> list[Chunk]:
        """
        Panel API statik içeriklerini + HTML sayfa içeriklerini chunk'la.
        content tipi: str | list[dict] (personel) | dict (SSS)
        """
        all_chunks: list[Chunk] = []

        for rec in records:
            key        = rec.get("key", "")
            label      = rec.get("label", key)
            source_url = rec.get("url", "")
            content    = rec.get("content")
            fakulte = rec.get("extra", {}).get("fakulte", "")
            metadata   = {
                "unit": key,
                "unit_label": label,
                "fakulte": fakulte,
                "source_fakulte": fakulte,
                "detected_fakulte": "",
                "scope": "faculty" if fakulte else "university",
                "doc_type": "static",
                "page_no": None,
                "page_count": None,
                "ann_id": None,
                "title": label,
                "published_at": "",
                "source_url": source_url,
                "pdf_url": "",
                "content_hash": "",
                "key": key
            }

            if isinstance(content, list):
                # Personel listesi (Panel API veya AVESİS formatından gelmiş olabilir)
                text = f"{label}\n\n{_staff_to_text(content)}"
            elif isinstance(content, dict):
                # SSS formatı
                text = _sss_to_text(content)
            elif isinstance(content, str) and content.strip():
                text = f"{label}\n\n{content}"
            else:
                continue

            source_key = f"static:{key}"
            all_chunks.extend(self._chunk_text(text, source_url, source_key, key, metadata))

        logger.info(f"Statik chunk: {len(records)} kayıt → {len(all_chunks)} chunk")
        return all_chunks

    def chunk_avesis_staff(self, records: list[dict]) -> list[Chunk]:
        """
        AVESİS personel kayıtlarını chunk'la.

        Her birim (fakülte) için büyük bir metin oluşturulur,
        sonra chunk'lanır. Kişi başına ayrı chunk da yazılır
        (isim bazlı arama için).
        """
        all_chunks: list[Chunk] = []

        for rec in records:
            key        = rec.get("key", "")
            label      = rec.get("label", key)
            source_url = rec.get("url", "")
            staff_list = rec.get("content", [])

            if not staff_list:
                continue

            unit_id  = rec.get("extra", {}).get("unit_id", "")
            fakulte  = rec.get("extra", {}).get("fakulte", "")
            metadata_base = {
                "unit": unit_id or key,
                "unit_label": label,
                "fakulte": fakulte,
                "source_fakulte": fakulte,
                "detected_fakulte": "",
                "scope": "faculty" if fakulte else "university",
                "doc_type": "avesis",
                "page_no": None,
                "page_count": None,
                "ann_id": None,
                "title": f"{label} Personel",
                "published_at": "",
                "source_url": source_url,
                "pdf_url": "",
                "content_hash": "",
                "key": key,
                "unit_id": unit_id
            }

            # Strateji 1: Birim geneli chunk (tüm kadro tek blok)
            full_text = f"{label} — Akademik Kadro\n\n{_avesis_staff_to_text(staff_list)}"
            source_key = f"avesis:{unit_id or key}"
            all_chunks.extend(
                self._chunk_text(full_text, source_url, source_key, key, metadata_base)
            )

            # Strateji 2: Kişi başına ayrı mini chunk (isim araması için)
            for i, person in enumerate(staff_list):
                person_text = _avesis_staff_to_text([person])
                if not person_text.strip():
                    continue
                person_metadata = {
                    **metadata_base,
                    "type":      "kisi",
                    "ad_soyad":  person.get("ad_soyad", ""),
                    "avesis_id": person.get("avesis_id", ""),
                }
                # Kişi metni genellikle tek chunk'a sığar, ama context seal alması için _chunk_text'ten geçmeli
                person_source_key = f"avesis_person:{person.get('avesis_id') or i}"
                all_chunks.extend(
                    self._chunk_text(
                        text=person_text,
                        source_url=person.get("profil_url", source_url),
                        source_key=person_source_key,
                        doc_id=f"{key}_p{i}",
                        metadata=person_metadata
                    )
                )

        logger.info(
            f"AVESİS chunk: {len(records)} birim → {len(all_chunks)} chunk "
            f"(birim geneli + kişi bazlı)"
        )
        return all_chunks

    def chunk_all(self, crawler_results: dict[str, list[dict]]) -> list[Chunk]:
        """
        Tüm crawler sonuçlarını chunk'la.

        Beklenen dict anahtarları:
          - "announcements"   → duyuru kayıtları
          - "static_contents" → Panel API + HTML statik/JS içerikler
          - "avesis_staff"    → AVESİS personel kayıtları
        """
        chunks: list[Chunk] = []

        chunks.extend(self.chunk_announcements(
            crawler_results.get("announcements", [])
        ))
        chunks.extend(self.chunk_static_contents(
            crawler_results.get("static_contents", [])
        ))
        chunks.extend(self.chunk_avesis_staff(
            crawler_results.get("avesis_staff", [])
        ))

        logger.info(f"Toplam chunk: {len(chunks)}")
        return chunks

    # ─────────────────────────────────────────────────────────────
    # İÇ METOD
    # ─────────────────────────────────────────────────────────────

    def _chunk_text(
        self,
        text:       str,
        source_url: str,
        source_key: str,
        doc_id:     str | int,
        metadata:   dict,
    ) -> list[Chunk]:
        if not text or not text.strip():
            return []

        # Markdown başlıklı içerik → başlık bazlı böl, sonra recursive
        if "\n#" in text or text.startswith("#"):
            sections = [
                d.page_content
                for d in _HEADER_SPLITTER.split_text(text)
                if d.page_content.strip()
            ]
        else:
            sections = [text]

        final_texts: list[str] = []
        for section in sections:
            if len(section) <= CHUNK_SIZE:
                if len(section.strip()) >= MIN_CHUNK_LEN:
                    final_texts.append(section.strip())
            else:
                for sub in _RECURSIVE_SPLITTER.split_text(section):
                    if len(sub.strip()) >= MIN_CHUNK_LEN:
                        final_texts.append(sub.strip())

        chunks_list = []
        for i, t in enumerate(final_texts):
            seal_lines = []
            
            scope = metadata.get("scope")
            if scope: seal_lines.append(f"Kapsam: {scope}")
                
            unit_label = metadata.get("unit_label")
            if unit_label: seal_lines.append(f"Kaynak Birim: {unit_label}")
                
            fakulte = metadata.get("fakulte")
            if fakulte: seal_lines.append(f"Ana Fakülte: {fakulte}")
                
            source_fakulte = metadata.get("source_fakulte")
            if source_fakulte: seal_lines.append(f"Kaynak Fakülte: {source_fakulte}")
                
            detected_fakulte = metadata.get("detected_fakulte")
            if detected_fakulte: seal_lines.append(f"Tespit Edilen Fakülte: {detected_fakulte}")
                
            title = metadata.get("title")
            if title: seal_lines.append(f"Başlık: {title}")
                
            doc_type = metadata.get("doc_type")
            if doc_type: seal_lines.append(f"Belge Tipi: {doc_type}")
                
            page_no = metadata.get("page_no")
            if page_no: seal_lines.append(f"Sayfa No: {page_no}")

            baglam = "\n".join(seal_lines) + "\n\nİçerik:\n" if seal_lines else ""

            if len(final_texts) > 1:
                baglam = baglam.replace("\n\nİçerik:", f"\n(Uzun belgenin {i+1}. bölümü)\n\nİçerik:")

            final_t = f"{baglam}{t}".strip() if baglam else t

            chunks_list.append(Chunk(
                text        = final_t,
                source_url  = source_url,
                source_key  = source_key,
                doc_id      = doc_id,
                chunk_index = i,
                metadata    = {**metadata, "chunk_index": i, "total_chunks": len(final_texts)},
            ))

        return chunks_list