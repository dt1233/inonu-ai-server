#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║         İNÖNÜ AI — MERKEZİ VERİTABANI YÖNETİCİSİ               ║
║         scrapping/db_manager.py  (v1.1)                          ║
╚══════════════════════════════════════════════════════════════════╝

v1.1 Düzeltmeleri:
  - chunkify(): Tablo/liste içerikler artık satır bazlı chunk'lanır
  - upsert_chunks(): Personel (list[dict]) verisi artık düz metne
    çevrilerek chunk'lanır; dict/list direkt geçilince hata vermez
  - Genel chunk boyutları iyileştirildi (max_chars: 800 → 1000)

Kullanım (diğer scraper dosyalarından):
    from db_manager import DBManager

    with DBManager() as db:
        db.upsert("announcements", doc, id_field="id")
        db.upsert_chunks(chunks, source_url="https://...", collection="announcements")

Gereksinimler:
    pip install pymongo
"""

import re
from datetime import datetime, timezone
from typing import Any

from pymongo import MongoClient, UpdateOne
from pymongo.collection import Collection
from pymongo.errors import BulkWriteError, ConnectionFailure


# ─────────────────────────────────────────────────────────────────
# BÖLÜM 0 │ Sabitler
# ─────────────────────────────────────────────────────────────────

MONGO_URI  = "mongodb://localhost:27017"
DB_NAME    = "inonu_ai"

# Koleksiyon adları
COL_ANNOUNCEMENTS    = "announcements"
COL_STATIC_CONTENTS  = "static_contents"
COL_ACADEMIC_UNITS   = "academic_units"
COL_PERSONNEL        = "personnel_details"
COL_CHUNKS           = "chunks"

# Chunking ayarları
CHUNK_MIN_CHARS  = 60
# v1.1: max_chars artırıldı (800 → 1000) — tablo satırları daha az bölünür
CHUNK_MAX_CHARS  = 1000
CHUNK_OVERLAP    = 1


# ─────────────────────────────────────────────────────────────────
# BÖLÜM 1 │ Terminal renk yardımcıları
# ─────────────────────────────────────────────────────────────────

class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    CYAN    = "\033[96m"

def _log(level: str, msg: str) -> None:
    icons = {"OK": f"{C.GREEN}[✔]{C.RESET}", "ERR": f"{C.RED}[✘]{C.RESET}",
             "INFO": f"{C.CYAN}[ℹ]{C.RESET}", "WARN": f"{C.YELLOW}[⚠]{C.RESET}"}
    ts   = datetime.now().strftime("%H:%M:%S")
    icon = icons.get(level, "[?]")
    print(f"  {C.DIM}{ts}{C.RESET}  {icon}  {msg}")


# ─────────────────────────────────────────────────────────────────
# BÖLÜM 1.5 │ v1.1 YENİ: Personel / dict→metin dönüştürücü
# ─────────────────────────────────────────────────────────────────

def _personnel_to_text(staff_list: list) -> str:
    """
    Personel listesini (list[dict]) okunabilir düz metne çevirir.
    Her personel için tek satır: "Ad Soyad | Unvan | Departman | E-posta | Telefon"

    Bu sayede personel bilgileri RAG chunk'larına doğru biçimde yazılır.
    Daha önce dict/list doğrudan geçildiği için chunk'lanamıyordu.
    """
    if not staff_list:
        return ""

    lines = ["── Personel Listesi ──"]
    for p in staff_list:
        if not isinstance(p, dict):
            continue
        ad      = p.get("ad_soyad", "").strip()
        unvan   = p.get("unvan", "").strip()
        dept    = p.get("departman", "").strip()
        gorev   = p.get("gorev", "").strip()
        email   = p.get("email", "").strip()
        telefon = p.get("telefon", "").strip()

        parts = [x for x in [ad, unvan, dept, gorev] if x]
        line  = " | ".join(parts)
        if email:
            line += f" | {email}"
        if telefon:
            line += f" | {telefon}"
        if line:
            lines.append(line)

    return "\n".join(lines)


def _sss_to_text(sss_dict: dict) -> list[str]:
    """
    SSS (Sıkça Sorulan Sorular) dict yapısını chunk'lanabilir metin listesine çevirir.
    Her kategori + soru-cevap çifti ayrı bir metin olarak döner.
    """
    texts = []
    for cat_key, cat_data in sss_dict.items():
        cat_label = cat_data.get("baslik", cat_key)
        cat_items = cat_data.get("content", [])

        if isinstance(cat_items, list):
            for item in cat_items:
                q   = (item.get("baslik") or "").strip()
                ans = (item.get("icerik") or "").strip()
                if q or ans:
                    full = f"{q}\n\n{ans}".strip() if q else ans
                    texts.append(full)
    return texts


# ─────────────────────────────────────────────────────────────────
# BÖLÜM 2 │ Anlamsal Chunking (chunkify)
# ─────────────────────────────────────────────────────────────────

def chunkify(
    text: str,
    source_url: str = "",
    source_collection: str = "",
    doc_id: Any = None,
    max_chars: int = CHUNK_MAX_CHARS,
    min_chars: int = CHUNK_MIN_CHARS,
    overlap: int = CHUNK_OVERLAP,
) -> list[dict]:
    """
    Bir metni anlamsal olarak (paragraf → cümle bazlı) parçalara böler.

    v1.1 Değişikliği:
      - Tablo/liste algılama eklendi: Eğer metin çoğunlukla kısa satırlardan
        (tablo satırı) oluşuyorsa, cümle bölme yerine satır grubu bazlı
        chunk'lama yapılır. Bu sayede sınav takvimi, kontenjan tablosu gibi
        yapılar parçalanmadan aktarılır.

    Strateji (öncelik sırası):
      1. İçerik tablo mu kontrol et → tablo ise satır grubu chunk'lama
      2. Önce çift satır sonu ile PARAGRAF bazlı böl
      3. Paragraf hâlâ max_chars'tan uzunsa cümle bazlı böl
      4. Çok kısa parçaları bir önceki chunk'a birleştir
      5. Bağlam kaybını azaltmak için overlap kadar cümleyi taşı
    """
    if not text or not text.strip():
        return []

    # ── Tablo/liste içerik tespiti ───────────────────────────────
    lines = [l for l in text.splitlines() if l.strip()]
    if lines:
        short_lines = [l for l in lines if len(l.strip()) < 120]
        table_ratio = len(short_lines) / len(lines)
    else:
        table_ratio = 0

    # Satırların %60'ı kısaysa → tablo/liste yapısı (sınav takvimi, personel vb.)
    if table_ratio >= 0.6 and len(lines) > 4:
        return _chunkify_table(text, source_url, source_collection, doc_id, max_chars)

    # ── 1. Paragraf bazlı ilk bölme ─────────────────────────────
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

    raw_sentences: list[str] = []

    for para in paragraphs:
        if len(para) <= max_chars:
            raw_sentences.append(para)
        else:
            sents = re.split(r"(?<=[.?!])\s+", para)
            raw_sentences.extend([s.strip() for s in sents if s.strip()])

    # ── 3. Kısa parçaları birleştir + max_chars'a sığdır ────────
    chunks_text: list[str] = []
    buffer = ""

    for sent in raw_sentences:
        candidate = (buffer + " " + sent).strip() if buffer else sent

        if len(candidate) <= max_chars:
            buffer = candidate
        else:
            if buffer:
                chunks_text.append(buffer)
            if len(sent) > max_chars:
                for i in range(0, len(sent), max_chars):
                    chunks_text.append(sent[i : i + max_chars])
            else:
                buffer = sent

    if buffer:
        chunks_text.append(buffer)

    # ── 4. Çok kısa son chunk'ı bir öncekiyle birleştir ─────────
    if len(chunks_text) >= 2 and len(chunks_text[-1]) < min_chars:
        chunks_text[-2] = (chunks_text[-2] + " " + chunks_text[-1]).strip()
        chunks_text.pop()

    # ── 5. Overlap ──────────────────────────────────────────────
    final_chunks: list[str] = []
    for i, chunk in enumerate(chunks_text):
        if overlap > 0 and i > 0:
            prev_sents = re.split(r"(?<=[.?!])\s+", chunks_text[i - 1])
            tail = " ".join(prev_sents[-overlap:]).strip()
            chunk = (tail + " " + chunk).strip() if tail else chunk
        final_chunks.append(chunk)

    return _build_chunk_docs(final_chunks, source_url, source_collection, doc_id)


def _chunkify_table(
    text: str,
    source_url: str,
    source_collection: str,
    doc_id: Any,
    max_chars: int,
) -> list[dict]:
    """
    v1.1 YENİ: Tablo/liste içerikler için satır grubu bazlı chunk'lama.

    Strateji:
      - Başlık satırlarını (── ... ──) tespit et → yeni grup başlatır
      - max_chars dolana kadar satırları aynı chunk'ta birleştir
      - Bu sayede "Eğitim Fakültesi | 10-16 Kasım" gibi tablo satırları
        aynı chunk içinde kalır, bölünmez.
    """
    lines = [l for l in text.splitlines() if l.strip()]
    chunks_text: list[str] = []
    buffer_lines: list[str] = []

    for line in lines:
        # Başlık satırı → mevcut buffer'ı kaydet, yeni grup başlat
        is_header = line.strip().startswith("──") or line.strip().startswith("│")

        candidate = "\n".join(buffer_lines + [line])
        if len(candidate) > max_chars:
            if buffer_lines:
                chunks_text.append("\n".join(buffer_lines))
            buffer_lines = [line]
        else:
            if is_header and buffer_lines and len("\n".join(buffer_lines)) > 60:
                chunks_text.append("\n".join(buffer_lines))
                buffer_lines = [line]
            else:
                buffer_lines.append(line)

    if buffer_lines:
        chunks_text.append("\n".join(buffer_lines))

    return _build_chunk_docs(chunks_text, source_url, source_collection, doc_id)


def _build_chunk_docs(
    chunks_text: list[str],
    source_url: str,
    source_collection: str,
    doc_id: Any,
) -> list[dict]:
    """Chunk metin listesinden MongoDB'ye yazılacak dict listesi üretir."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = []
    for idx, chunk_text in enumerate(chunks_text):
        if not chunk_text.strip():
            continue
        result.append({
            "chunk_index":  idx,
            "total_chunks": len(chunks_text),
            "text":         chunk_text,
            "char_count":   len(chunk_text),
            "metadata": {
                "source_url":        source_url,
                "source_collection": source_collection,
                "source_doc_id":     str(doc_id) if doc_id is not None else None,
                "created_at":        now,
            },
        })
    return result


# ─────────────────────────────────────────────────────────────────
# BÖLÜM 3 │ DBManager sınıfı
# ─────────────────────────────────────────────────────────────────

class DBManager:
    """
    Context manager olarak kullanılabilir:

        with DBManager() as db:
            db.upsert("announcements", doc, id_field="id")

    Ya da manuel:

        db = DBManager()
        db.connect()
        db.upsert(...)
        db.close()
    """

    def __init__(self, uri: str = MONGO_URI, db_name: str = DB_NAME):
        self.uri     = uri
        self.db_name = db_name
        self._client = None
        self._db     = None

    # ── Bağlantı yönetimi ────────────────────────────────────────

    def connect(self) -> "DBManager":
        try:
            self._client = MongoClient(self.uri, serverSelectionTimeoutMS=5000)
            self._client.admin.command("ping")
            self._db = self._client[self.db_name]
            _log("OK", f"MongoDB bağlantısı kuruldu → {C.CYAN}{self.uri}{C.RESET} / {C.BOLD}{self.db_name}{C.RESET}")
        except ConnectionFailure as e:
            _log("ERR", f"MongoDB'ye bağlanılamadı: {C.RED}{e}{C.RESET}")
            raise
        return self

    def close(self) -> None:
        if self._client:
            self._client.close()
            _log("INFO", "MongoDB bağlantısı kapatıldı.")

    def __enter__(self) -> "DBManager":
        return self.connect()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # ── Koleksiyon erişimi ───────────────────────────────────────

    def col(self, name: str) -> Collection:
        if self._db is None:
            raise RuntimeError("Önce connect() çağrılmalı veya 'with DBManager()' kullanılmalı.")
        return self._db[name]

    # ── UPSERT ──────────────────────────────────────────────────

    def upsert(self, collection: str, document: dict, id_field: str = "id") -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        doc = {**document}
        filter_query  = {id_field: doc[id_field]}
        set_on_insert = {"created_at": now}
        set_always    = {"updated_at": now}
        doc.pop("_id", None)

        result = self.col(collection).update_one(
            filter_query,
            {
                "$set":         {**doc, **set_always},
                "$setOnInsert": set_on_insert,
            },
            upsert=True,
        )

        if result.upserted_id:
            _log("OK", f"{C.GREEN}[YENİ]{C.RESET}  {collection} ← id={C.BOLD}{doc.get(id_field)}{C.RESET}")
            return "inserted"
        else:
            _log("INFO", f"{C.DIM}[GÜN.]{C.RESET}  {collection} ← id={C.DIM}{doc.get(id_field)}{C.RESET}")
            return "updated"

    def bulk_upsert(self, collection: str, documents: list[dict], id_field: str = "id") -> dict:
        if not documents:
            return {"inserted": 0, "updated": 0}

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ops = []

        for doc in documents:
            doc = {**doc}
            doc.pop("_id", None)
            filter_query = {id_field: doc[id_field]}
            ops.append(
                UpdateOne(
                    filter_query,
                    {
                        "$set":         {**doc, "updated_at": now},
                        "$setOnInsert": {"created_at": now},
                    },
                    upsert=True,
                )
            )

        try:
            result = self.col(collection).bulk_write(ops, ordered=False)
            inserted = result.upserted_count
            updated  = result.modified_count
            _log("OK", (
                f"Bulk upsert tamamlandı → {C.BOLD}{collection}{C.RESET} | "
                f"{C.GREEN}+{inserted} yeni{C.RESET} / "
                f"{C.DIM}{updated} güncellendi{C.RESET}"
            ))
            return {"inserted": inserted, "updated": updated}
        except BulkWriteError as bwe:
            _log("WARN", f"Bulk write kısmi hata: {bwe.details}")
            return {"inserted": 0, "updated": 0}

    # ── CHUNK UPSERT ─────────────────────────────────────────────

    def upsert_chunks(
        self,
        text: Any,          # v1.1: str | list[dict] (personel) | dict (SSS) kabul eder
        source_url: str,
        source_collection: str,
        doc_id: Any = None,
        max_chars: int = CHUNK_MAX_CHARS,
        replace_existing: bool = True,
    ) -> int:
        """
        Bir metni chunkify() ile parçalar ve 'chunks' koleksiyonuna yazar.

        v1.1 Değişikliği:
          - text parametresi artık str dışında list[dict] (personel) ve
            dict (SSS) türlerini de kabul eder.
          - list[dict] → _personnel_to_text() ile düz metne çevrilir
          - dict → _sss_to_text() ile metin listesine çevrilir ve
            her kategori ayrı çağrı olarak chunk'lanır
        """
        # v1.1: Tip dönüşümü
        if isinstance(text, list):
            # Personel listesi veya benzeri list[dict]
            text = _personnel_to_text(text)
        elif isinstance(text, dict):
            # SSS yapısı — her kategoriyi ayrı chunk et
            sss_texts = _sss_to_text(text)
            total = 0
            for i, t in enumerate(sss_texts):
                if t.strip():
                    total += self.upsert_chunks(
                        text=t,
                        source_url=f"{source_url}#sss{i}",
                        source_collection=source_collection,
                        doc_id=f"{doc_id}_sss{i}" if doc_id else f"sss{i}",
                        max_chars=max_chars,
                        replace_existing=(replace_existing and i == 0),
                    )
            return total

        if not isinstance(text, str) or not text.strip():
            _log("WARN", f"Chunk edilecek metin boş veya geçersiz tür → {type(text)}")
            return 0

        chunks = chunkify(
            text,
            source_url=source_url,
            source_collection=source_collection,
            doc_id=doc_id,
            max_chars=max_chars,
        )

        if not chunks:
            _log("WARN", f"Chunk üretilemedi → kaynak: {C.YELLOW}{source_url[:60]}{C.RESET}")
            return 0

        if replace_existing:
            deleted = self.col(COL_CHUNKS).delete_many(
                {"metadata.source_url": source_url}
            ).deleted_count
            if deleted:
                _log("INFO", f"{C.DIM}Eski {deleted} chunk silindi → {source_url[:50]}{C.RESET}")

        self.col(COL_CHUNKS).insert_many(chunks)
        _log("OK", (
            f"Chunk'lar yazıldı → {C.BOLD}{len(chunks)} parça{C.RESET} | "
            f"kaynak: {C.CYAN}{source_url[:55]}{C.RESET}"
        ))
        return len(chunks)

    # ── YARDIMCI: Koleksiyon istatistiği ────────────────────────

    def stats(self) -> None:
        collections = [
            COL_ANNOUNCEMENTS, COL_STATIC_CONTENTS,
            COL_ACADEMIC_UNITS, COL_PERSONNEL, COL_CHUNKS,
        ]
        print()
        print(f"  {C.CYAN}{C.BOLD}── İnönü AI · Veritabanı İstatistikleri ({self.db_name}) ──{C.RESET}")
        for name in collections:
            count = self.col(name).count_documents({})
            bar   = "█" * min(count // 10, 30)
            print(f"  {C.DIM}{name:<22}{C.RESET}  {C.BOLD}{count:>6} belge{C.RESET}  {C.CYAN}{bar}{C.RESET}")
        print()


# ─────────────────────────────────────────────────────────────────
# BÖLÜM 4 │ Bağımsız test
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n  {C.CYAN}{C.BOLD}── db_manager.py v1.1 · Bağlantı & Chunk Testi ──{C.RESET}\n")

    # 1. Tablo içerik testi
    table_text = (
        "2025-2026 Bahar Yarıyılı Ara Sınav Tarihleri\n"
        "Birim\tTarih\n"
        "Sağlık Hizmetleri Meslek Yüksekokulu\t30 Mart – 3 Nisan\n"
        "Hukuk Fakültesi\t2-3 Nisan\n"
        "İlahiyat Fakültesi\t6-10 Nisan\n"
        "Eczacılık Fakültesi\t6-10 Nisan\n"
        "Hemşirelik Fakültesi\t6-10 Nisan\n"
        "İktisadi ve İdari Bilimler Fakültesi\t6-10 Nisan\n"
        "Eğitim Fakültesi\t6-12 Nisan\n"
    )
    print(f"  {C.BOLD}[1] Tablo chunkify() testi:{C.RESET}")
    chunks = chunkify(table_text, source_url="https://test.inonu.edu.tr/sinav", source_collection="announcements", doc_id=1)
    for i, c in enumerate(chunks):
        print(f"    Chunk {i+1}/{len(chunks)} ({c['char_count']} karakter):\n{C.DIM}{c['text'][:200]}{C.RESET}\n")

    # 2. Personel metne çevirme testi
    print(f"  {C.BOLD}[2] Personel → Metin testi:{C.RESET}")
    sample_staff = [
        {"id": 117, "ad_soyad": "Tacettin KOYUNOĞLU", "unvan": "Öğrenci İşleri Daire Başkanı V.",
         "departman": "Daire Başkanı", "gorev": "Öğrenci İşleri Daire Başkanlığı",
         "email": "tacettin.koyunoglu@inonu.edu.tr", "telefon": "0 422 377 3041"},
        {"id": 101, "ad_soyad": "Nuriye KALI", "unvan": "Şef",
         "departman": "Şef", "gorev": "", "email": "nuriye.kali@inonu.edu.tr", "telefon": ""},
    ]
    text = _personnel_to_text(sample_staff)
    print(f"{C.DIM}{text}{C.RESET}\n")

    # 3. MongoDB testi
    print(f"  {C.BOLD}[3] MongoDB upsert testi:{C.RESET}")
    try:
        with DBManager() as db:
            db.upsert(COL_ANNOUNCEMENTS, {"id": 99999, "title": "Test Duyurusu", "content": "Test içerik."})
            db.upsert_chunks(
                text=table_text,
                source_url="https://test.inonu.edu.tr/sinav",
                source_collection="announcements",
                doc_id=99999,
            )
            db.upsert_chunks(
                text=sample_staff,
                source_url="https://panel.inonu.edu.tr/servlet/staff",
                source_collection="personnel_details",
                doc_id="personel_test",
            )
            db.stats()
    except Exception as e:
        print(f"\n  {C.RED}[✘] MongoDB bağlantı hatası: {e}{C.RESET}")
        print(f"  {C.YELLOW}[⚠] MongoDB'nin çalışır durumda olduğundan emin olun.{C.RESET}\n")
