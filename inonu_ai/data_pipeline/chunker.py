#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İNÖNÜ AI │ chunker.py
2 Stratejili Akıllı Parçalama
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)
from loguru import logger

CHUNK_SIZE    = 1000
CHUNK_OVERLAP = 150
MIN_CHUNK_LEN = 80


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


def _staff_to_text(staff_list: list[dict]) -> str:
    lines = []
    for p in staff_list:
        parts = [p.get("ad_soyad", "")]
        if p.get("unvan"):     parts.append(p["unvan"])
        if p.get("departman"): parts.append(p["departman"])
        if p.get("gorev"):     parts.append(f"Görev: {p['gorev']}")
        if p.get("email"):     parts.append(f"E-posta: {p['email']}")
        if p.get("telefon"):   parts.append(f"Tel: {p['telefon']}")
        lines.append(" | ".join(filter(None, parts)))
    return "\n".join(lines)


def _sss_to_text(sss_dict: dict) -> str:
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


class Chunker:

    def chunk_announcements(self, records: list[dict]) -> list[Chunk]:
        all_chunks: list[Chunk] = []
        for rec in records:
            ann_id     = rec.get("id", "")
            title      = rec.get("title", "")
            source_url = rec.get("sourceUrl", f"announcement:{ann_id}")
            metadata   = {
                "category": "duyuru",
                "title":    title,
                "updated":  rec.get("updated", ""),
                "ann_id":   ann_id,
            }

            content   = rec.get("content") or ""
            main_text = f"{title}\n\n{content}".strip() if title else content
            all_chunks.extend(
                self._chunk_text(main_text, source_url, "duyurular_api", ann_id, metadata)
            )

            for i, att in enumerate(rec.get("attachments", [])):
                att_text = att.get("content", "")
                if not att_text or att_text in ("[PDF Okunamadı]", "[İçerik alınamadı]"):
                    continue
                all_chunks.extend(self._chunk_text(
                    f"{title} (Ek {i+1})\n\n{att_text}",
                    att.get("url", source_url),
                    "duyurular_api",
                    f"{ann_id}_att{i}",
                    {**metadata, "type": "pdf_attachment", "att_index": i},
                ))

        logger.info(f"Duyuru chunk: {len(records)} kayıt → {len(all_chunks)} chunk")
        return all_chunks

    def chunk_static_contents(self, records: list[dict]) -> list[Chunk]:
        all_chunks: list[Chunk] = []
        for rec in records:
            key        = rec.get("key", "")
            label      = rec.get("label", key)
            source_url = rec.get("url", "")
            content    = rec.get("content")
            metadata   = {"category": "statik", "label": label, "key": key}

            if isinstance(content, list):
                text = f"{label}\n\n{_staff_to_text(content)}"
            elif isinstance(content, dict):
                text = _sss_to_text(content)
            elif isinstance(content, str) and content.strip():
                text = f"{label}\n\n{content}"
            else:
                continue

            all_chunks.extend(self._chunk_text(text, source_url, key, key, metadata))

        logger.info(f"Statik chunk: {len(records)} kayıt → {len(all_chunks)} chunk")
        return all_chunks

    def chunk_all(self, crawler_results: dict[str, list[dict]]) -> list[Chunk]:
        chunks = []
        chunks.extend(self.chunk_announcements(
            crawler_results.get("announcements", [])
        ))
        chunks.extend(self.chunk_static_contents(
            crawler_results.get("static_contents", [])
        ))
        logger.info(f"Toplam chunk: {len(chunks)}")
        return chunks

    def _chunk_text(self, text: str, source_url: str, source_key: str,
                     doc_id: str | int, metadata: dict) -> list[Chunk]:
        if not text or not text.strip():
            return []

        if "\n#" in text or text.startswith("#"):
            sections = [d.page_content for d in _HEADER_SPLITTER.split_text(text)
                        if d.page_content.strip()]
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

        return [
            Chunk(
                text        = t,
                source_url  = source_url,
                source_key  = source_key,
                doc_id      = doc_id,
                chunk_index = i,
                metadata    = {**metadata, "chunk_index": i,
                                "total_chunks": len(final_texts)},
            )
            for i, t in enumerate(final_texts)
        ]