#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║         İNÖNÜ AI — MERKEZİ VERİTABANI YÖNETİCİSİ               ║
║         scrapping/db_manager.py                                  ║
╚══════════════════════════════════════════════════════════════════╝

Tüm scraper'ların ortak kullandığı MongoDB modülü.

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
CHUNK_MIN_CHARS  = 60    # Bu kadardan kısa chunk'ları birleştir
CHUNK_MAX_CHARS  = 800   # Bu kadardan uzun chunk'ları böl
CHUNK_OVERLAP    = 1     # Bağlam kaybını önlemek için komşu cümlelerden taşma (cümle sayısı)


# ─────────────────────────────────────────────────────────────────
# BÖLÜM 1 │ Terminal renk yardımcıları (bağımsız kullanım için)
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

    Strateji (öncelik sırası):
      1. Önce çift satır sonu (\n\n) ile PARAGRAF bazlı böl.
      2. Paragraf hâlâ max_chars'tan uzunsa cümle bazlı (. ? ! ile biten) böl.
      3. Çok kısa parçaları (< min_chars) bir önceki chunk'a birleştir.
      4. Bağlam kaybını azaltmak için `overlap` kadar cümleyi bir sonraki chunk'a taşı.

    Returns:
        List of dicts — her biri 'chunks' koleksiyonuna yazılacak bir belge.
    """
    if not text or not text.strip():
        return []

    # ── 1. Paragraf bazlı ilk bölme ─────────────────────────────
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

    raw_sentences: list[str] = []

    for para in paragraphs:
        if len(para) <= max_chars:
            raw_sentences.append(para)
        else:
            # ── 2. Uzun paragrafı cümle bazlı böl ──────────────
            # Nokta/soru/ünlem + boşluk kombinasyonuna göre böl
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
            # Cümle tek başına max_chars'tan uzunsa zorla kes
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

    # ── 5. Overlap (bağlam taşması) ─────────────────────────────
    #    Her chunk'ın başına bir önceki chunk'ın son `overlap` cümlesi eklenir.
    #    Bu, RAG sorgularında bağlam kopmasını azaltır.
    final_chunks: list[str] = []
    for i, chunk in enumerate(chunks_text):
        if overlap > 0 and i > 0:
            prev_sents = re.split(r"(?<=[.?!])\s+", chunks_text[i - 1])
            tail = " ".join(prev_sents[-overlap:]).strip()
            chunk = (tail + " " + chunk).strip() if tail else chunk
        final_chunks.append(chunk)

    # ── 6. Chunk belgelerini oluştur ─────────────────────────────
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = []
    for idx, chunk_text in enumerate(final_chunks):
        result.append({
            "chunk_index":        idx,
            "total_chunks":       len(final_chunks),
            "text":               chunk_text,
            "char_count":         len(chunk_text),
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
            # Bağlantıyı test et
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
        """Koleksiyona erişim kısayolu."""
        if self._db is None:
            raise RuntimeError("Önce connect() çağrılmalı veya 'with DBManager()' kullanılmalı.")
        return self._db[name]

    # ── UPSERT (Ekle veya Güncelle) ──────────────────────────────

    def upsert(
        self,
        collection: str,
        document: dict,
        id_field: str = "id",
    ) -> str:
        """
        Tek bir belgeyi upsert eder.

        - id_field'a göre mevcut kayıt varsa → günceller (updated_at damgası eklenir).
        - Yoksa → yeni kayıt ekler (created_at damgası eklenir).

        Returns:
            "updated" | "inserted"
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        doc = {**document}  # Orijinali değiştirme

        filter_query = {id_field: doc[id_field]}

        set_on_insert = {"created_at": now}
        set_always    = {"updated_at": now}

        # _id alanını MongoDB'ye bırak, kendi id_field'ımızı kullan
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
            status = "inserted"
            _log("OK", f"{C.GREEN}[YENİ]{C.RESET}  {collection} ← id={C.BOLD}{doc.get(id_field)}{C.RESET}")
        else:
            status = "updated"
            _log("INFO", f"{C.DIM}[GÜN.]{C.RESET}  {collection} ← id={C.DIM}{doc.get(id_field)}{C.RESET}")

        return status

    def bulk_upsert(
        self,
        collection: str,
        documents: list[dict],
        id_field: str = "id",
    ) -> dict:
        """
        Birden fazla belgeyi tek seferde (bulk) upsert eder.
        Büyük veri setleri için tekli upsert'ten çok daha hızlıdır.

        Returns:
            {"inserted": int, "updated": int}
        """
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
        text: str,
        source_url: str,
        source_collection: str,
        doc_id: Any = None,
        max_chars: int = CHUNK_MAX_CHARS,
        replace_existing: bool = True,
    ) -> int:
        """
        Bir metni chunkify() ile parçalar ve 'chunks' koleksiyonuna yazar.

        - replace_existing=True (varsayılan): aynı source_url'e ait eski
          chunk'ları siler, yerine yenilerini yazar. (Tam yenileme)
        - replace_existing=False: mevcut chunk'ları silmeden ekler.

        Returns:
            Yazılan chunk sayısı.
        """
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
        """Tüm koleksiyonların belge sayısını terminale yazdırır."""
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
# BÖLÜM 4 │ Bağımsız test (python db_manager.py ile çalıştır)
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # ── Bağlantı testi ──────────────────────────────────────────
    print(f"\n  {C.CYAN}{C.BOLD}── db_manager.py · Bağlantı & Chunk Testi ──{C.RESET}\n")

    sample_text = (
        "Öğrenci işleri birimi kayıt yenileme, mezuniyet, burs, disiplin ve "
        "yatay geçiş işlemlerini yürütmektedir.\n\n"
        "Kayıt yenileme işlemleri her yarıyıl başında yapılır. "
        "Öğrenciler belirlenen tarihler arasında harçlarını yatırıp sisteme giriş yapmalıdır.\n\n"
        "Mezuniyet başvuruları son sınıf öğrencileri tarafından Mayıs ayında yapılır. "
        "Burs başvuruları ise Ekim ayında alınmaktadır. "
        "Yatay geçiş başvuruları için önce kayıtlı olduğunuz üniversiteden transkript almanız gerekmektedir."
    )

    # 1. chunkify testi (DB bağlantısı gerekmez)
    print(f"  {C.BOLD}[1] chunkify() testi:{C.RESET}")
    chunks = chunkify(sample_text, source_url="https://ornek.inonu.edu.tr/test", source_collection="static_contents", doc_id=42)
    for i, c in enumerate(chunks):
        print(f"    Chunk {i+1}/{len(chunks)} ({c['char_count']} karakter): {C.DIM}{c['text'][:80]}…{C.RESET}")

    # 2. MongoDB bağlantı + upsert testi
    print(f"\n  {C.BOLD}[2] MongoDB upsert testi:{C.RESET}")
    try:
        with DBManager() as db:
            # Test belgesi upsert
            db.upsert(COL_ANNOUNCEMENTS, {"id": 99999, "title": "Test Duyurusu", "content": "Test içerik."})
            db.upsert(COL_ANNOUNCEMENTS, {"id": 99999, "title": "Test Duyurusu (Güncellendi)", "content": "Güncellenmiş içerik."})

            # Chunk yazma testi
            db.upsert_chunks(
                text=sample_text,
                source_url="https://ornek.inonu.edu.tr/test",
                source_collection="static_contents",
                doc_id=42,
            )

            # İstatistik
            db.stats()

    except Exception as e:
        print(f"\n  {C.RED}[✘] MongoDB bağlantı hatası: {e}{C.RESET}")
        print(f"  {C.YELLOW}[⚠] MongoDB'nin çalışır durumda olduğundan emin olun: mongod --dbpath /data/db{C.RESET}\n")
