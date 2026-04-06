#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║              İNÖNÜ AI — RAG ENGINE v4.2 (Drop-in Fix)                        ║
║              Mevcut v4.0/v4.1 engine üzerine minimal değişiklik              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Tespit edilen 5 sorun ve fix'leri:                                          ║
║                                                                              ║
║  [FIX-1] LLM PROMPT — Tarih bilinci + Referans yasağı                        ║
║    Sorun: LLM "Bilgi 10'da belirtildiğine göre 2023..." diyor                ║
║    → Prompt'ta "Bilgi X" referansı yasak, doğrudan yaz direktifi eklendi     ║
║    → "En güncel tarihi tercih et, çakışırsa en son tarihi yaz" eklendi       ║
║                                                                              ║
║  [FIX-2] CONTEXT SIRALAMASINDA TARİH AĞIRLIĞI                                ║
║    Sorun: 2023 tarihli ve 2025 tarihli chunk aynı sıraya düşüyor             ║
║    → Re-rank sonrası chunk'lar tarih damgasına göre de sıralanıyor           ║
║    → Daha yeni chunk → +0.15 bonus (source_label içindeki yıl bilgisi)       ║
║                                                                              ║
║  [FIX-3] DÜRÜST FALLBACK — Veri yoksa uydurma                                ║
║    Sorun: Erasmus verisi yok ama LLM genel bilgisiyle cevap üretiyor         ║
║    → Re-rank top skoru < 0.15 ise LLM yerine doğrudan fallback mesajı        ║
║    → "Bu konuda güncel belge bulunamadı + iletişim" mesajı                   ║
║                                                                              ║
║  [FIX-4] AGENTIC REFORMÜLASYON YASAĞI                                        ║
║    Sorun: LLM reformülasyonu "NATO'nun Erasmus programı..." gibi             ║
║    halüsinasyon üretiyor ve arama daha da kötüleşiyor                        ║
║    → LLM reformülasyonu tamamen kaldırıldı                                   ║
║    → Retry sadece synonym_map + kısaltma açma ile yapılıyor                  ║
║                                                                              ║
║  [FIX-5] XAI'DA CHUNK İÇERİĞİ GÖRÜNTÜLENMESİ                                 ║
║    Sorun: Hangi chunk'ın seçildiği görünmüyor, debugging kör                 ║
║    → Her kaynak satırının altında 120 karakter önizleme eklendi              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import List, Dict, Optional, Set

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

try:
    import numpy as np
    import requests
    import faiss
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
    from sentence_transformers import SentenceTransformer, CrossEncoder
    from rank_bm25 import BM25Okapi
except ImportError as e:
    print(f"\n[HATA] Eksik kütüphane: {e}\npip install -r requirements.txt\n")
    sys.exit(1)

# ─── AYARLAR ──────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent

MONGO_URI     = os.getenv("INONU_MONGO_URI", "mongodb://localhost:27017")
MONGO_DB      = os.getenv("INONU_MONGO_DB",  "inonu_ai")
MONGO_COL     = os.getenv("INONU_MONGO_COL", "chunks")
MONGO_TIMEOUT = int(os.getenv("MONGO_TIMEOUT", "5000"))

EMBED_MODEL_NAME  = os.getenv("INONU_EMBED_MODEL",  "BAAI/bge-m3")
RERANK_MODEL_NAME = os.getenv("INONU_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")

FAISS_PATH = str(SCRIPT_DIR / "faiss_index.bin")
META_PATH  = str(SCRIPT_DIR / "metadata_store.json")

OLLAMA_URL     = os.getenv("INONU_OLLAMA_URL",   "http://localhost:11434/api/generate")
OLLAMA_MODEL   = os.getenv("INONU_OLLAMA_MODEL", "llama3.1")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "180"))

# RAG parametreleri
IRON_SHIELD_THRESHOLD = 0.30   # v4.1'den düşürüldü (0.35 → 0.30)
BM25_MIN_SCORE        = 0.8    # BM25 minimum

TOP_K       = int(os.getenv("FAISS_TOP_K", "60"))
BM25_TOP_K  = int(os.getenv("BM25_TOP_K",  "60"))
RRF_K       = int(os.getenv("RRF_K",       "20"))  # 60→20: yüksek ranklara gerçek ağırlık

RERAN_TOP_K            = int(os.getenv("RERANK_TOP_K",   "20"))
RERAN_SCORE_THRESHOLD  = float(os.getenv("RERANK_THRESH", "-3.0"))
MAX_CONTEXT_CHUNKS     = int(os.getenv("MAX_CTX_CHUNKS",  "10"))

# [FIX-3] Güven eşiği — bu altında LLM yerine doğrudan fallback
LLM_CONFIDENCE_MIN = float(os.getenv("LLM_CONFIDENCE_MIN", "0.12"))

NUM_CTX     = int(os.getenv("INONU_NUM_CTX",     "8192"))
NUM_PREDICT = int(os.getenv("INONU_NUM_PREDICT",  "800"))

LLAMA_TEMPERATURE = 0.0
STREAMING_ENABLED = True

FAISS_RRF_WEIGHT = 1.2
BM25_RRF_WEIGHT  = 1.0

FALLBACK_MESSAGE = (
    "⛔ Bu konuda elimdeki güncel belgelerde net bir bilgi bulunamadı.\n"
    "   Lütfen Öğrenci İşleri Daire Başkanlığı ile iletişime geçin:\n"
    "   📞 0422 377 30 67  |  📧 ogrenciisleri@inonu.edu.tr"
)

# ─── [FIX-1] YENİ SYSTEM PROMPT ───────────────────────────────────────────────
# Kritik eklemeler:
# - "Bilgi X" referansı yasak → doğrudan yaz
# - Tarih çakışmasında en güncel olanı tercih et
# - Veritabanında yoksa kesinlikle uydurma
SYSTEM_PROMPT = """Sen İnönü Üniversitesi'nin resmi yapay zeka kampüs asistanısın.

GÖREV:
- YALNIZCA sana verilen METİNLER bölümündeki bilgileri kullanarak cevap ver.
- Cevabı net, doğrudan ve kaliteli Türkçe ile yaz. Birden fazla bilgi varsa madde madde listele.
- Tarih ve rakamları mutlaka yaz.

KRİTİK KURALLAR:
1. METİNLERDE YOKSA UYDURMA — Genel bilgin olsa bile, belgede yoksa söyleme.
2. "Bilgi 1", "Bilgi 2" gibi referansları ASLA kullanma. Bilgiyi doğrudan yaz.
3. Birden fazla tarih varsa EN GÜNCEL olanı öne çıkar, tarih yılına dikkat et.
4. Belgede bilgi yoksa şunu söyle: "Bu konuda elimdeki güncel belgelerde bilgi bulunamadı. Öğrenci İşleri ile iletişime geçin."
5. URL ve link gösterme (telefon/e-posta hariç).
6. Terim eşdeğerleri: "vize"=ara sınav, "büt"=bütünleme, "güz"=güz yarıyılı, "bahar yılı"=bahar yarıyılı."""

# ─── AKADEMİK TAKVİM NORMALİZASYON ───────────────────────────────────────────
ACADEMIC_CALENDAR_RULES = [
    (r"\bbahar\s+yılı\b",        "bahar yarıyılı"),
    (r"\bbahar\s+dönem[i]?\b",   "bahar yarıyılı"),
    (r"\bgüz\s+yılı\b",          "güz yarıyılı"),
    (r"\bgüz\s+dönem[i]?\b",     "güz yarıyılı"),
    (r"\bii[.\s]+dönem\b",       "bahar yarıyılı"),
    (r"\bi[.\s]+dönem\b",        "güz yarıyılı"),
    (r"\bvize\s+sınav[ı]?\b",    "ara sınav"),
    (r"\bmidterm\b",              "ara sınav"),
    (r"\bfinal\s+sınav[ı]?\b",   "yarıyıl sonu sınavı"),
    (r"\bne\s+zaman\b",          "tarih tarihleri ne zaman"),
]

ABBREVIATION_MAP = {
    r"\böğr[\.\s]+gör[\.\s]*\b":      "öğretim görevlisi",
    r"\barş[\.\s]+gör[\.\s]*\b":      "araştırma görevlisi",
    r"\bdr[\.\s]+öğr[\.\s]+üyesi\b":  "doktor öğretim üyesi",
    r"\bdoç[\.\s]+dr[\.\s]*\b":       "doçent doktor",
    r"\bprof[\.\s]+dr[\.\s]*\b":      "profesör doktor",
    r"\bobs\b":                        "öğrenci bilgi sistemi",
    r"\bgano\b":                       "genel akademik not ortalaması",
    r"\bagno\b":                       "genel akademik not ortalaması",
}

# [FIX-4] Sadece kural tabanlı synonym (LLM reformülasyonu kaldırıldı)
SYNONYM_MAP: Dict[str, List[str]] = {
    "vize":          ["ara sınav", "midterm", "ara sınav tarihleri"],
    "ara sınav":     ["vize", "midterm"],
    "büt":           ["bütünleme", "bütünleme sınavı"],
    "bütünleme":     ["büt", "bütünleme sınavı"],
    "final":         ["yarıyıl sonu sınavı", "dönem sonu sınavı"],
    "güz":           ["güz yarıyılı", "güz dönemi"],
    "bahar":         ["bahar yarıyılı", "bahar dönemi"],
    "kayıt":         ["kayıt yenileme", "ders kaydı"],
    "harç":          ["katkı payı", "öğrenim ücreti"],
    "katkı payı":    ["harç", "öğrenim ücreti"],
    "transkript":    ["not belgesi", "not dökümü"],
    "diploma":       ["mezuniyet belgesi"],
    "mezuniyet":     ["mezuniyet töreni"],
    "obs":           ["öğrenci bilgi sistemi"],
    "burs":          ["burs başvurusu", "burs ödemeleri"],
    "staj":          ["staj başvurusu", "zorunlu staj"],
    "erasmus":       ["öğrenci değişim programı", "uluslararası değişim", "yurt dışı değişim"],
    "farabi":        ["öğrenci değişim programı", "yurt içi değişim"],
    "yatay geçiş":   ["kurumlararası geçiş", "transfer"],
    "çap":           ["çift anadal"],
    "çift anadal":   ["çap", "çap programı"],
    "yandal":        ["yan dal", "yan dal programı"],
    "gano":          ["genel akademik not ortalaması"],
    "muafiyet":      ["ders muafiyeti", "intibak"],
    "danışman":      ["akademik danışman"],
    "hoca":          ["öğretim üyesi", "öğretim görevlisi"],
    "akademisyen":   ["öğretim üyesi", "öğretim görevlisi"],
    "ders programı": ["müfredat", "ders içerikleri"],
    "seçmeli ders":  ["seçmeli", "ÜSD", "üniversite seçmeli"],
}

TURKISH_STOPWORDS: Set[str] = {
    "bir", "ve", "bu", "da", "de", "ile", "için", "mi", "mı", "mu", "mü",
    "ne", "ya", "ki", "ama", "hem", "o", "şu", "ben", "sen", "biz", "siz",
    "olan", "olarak", "gibi", "daha", "en", "çok", "var", "yok", "her",
    "tüm", "bütün", "kadar", "sonra", "önce", "üzere", "göre", "ise",
    "ancak", "fakat", "veya", "den", "dan", "nin", "dir", "dır", "dur",
    "dür", "tir", "tır", "tur", "tür", "olup", "olduğu", "olması",
    "ayrıca", "arasında", "tarafından", "hakkında", "dolayı",
}


# ─── YARDIMCI FONKSİYONLAR ────────────────────────────────────────────────────

def log(tag: str, msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    icons = {"OK":"[+]","ERR":"[!]","INFO":"[i]","WARN":"[*]",
             "SHIELD":"[⛔]","FIX":"[fix]","BYPASS":"[✓]"}
    print(f"  {ts}  {icons.get(tag,'[?]')}  {msg}")


def normalize_academic_calendar(text: str) -> str:
    """[FIX-1] Akademik takvim varyantlarını kanonik forma çevir."""
    result = text
    for pattern, replacement in ACADEMIC_CALENDAR_RULES:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def normalize_abbreviations(text: str) -> str:
    result = text.lower()
    for pattern, replacement in ABBREVIATION_MAP.items():
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def turkish_tokenize(text: str) -> List[str]:
    t = re.sub(r"[^a-zçğıöşü0-9\s]", " ", text.lower())
    return [w for w in t.split() if w not in TURKISH_STOPWORDS and len(w) >= 2]


def expand_query(query: str) -> str:
    """[FIX-4] Sadece kural tabanlı genişletme — LLM reformülasyonu yok."""
    ql = query.lower()
    exps: List[str] = []
    for term in sorted(SYNONYM_MAP.keys(), key=len, reverse=True):
        if term in ql:
            for syn in SYNONYM_MAP[term]:
                if syn.lower() not in ql and syn not in exps:
                    exps.append(syn)
    if exps:
        expanded = query + " " + " ".join(exps)
        log("FIX", f"Sorgu genişletildi: +{len(exps)} terim")
        return expanded
    return query


def deduplicate_hits(hits: List[dict]) -> List[dict]:
    unique, seen = [], []
    for h in hits:
        prefix = h["text"].strip()[:200]
        if not any(prefix == s for s in seen):
            unique.append(h)
            seen.append(prefix)
    removed = len(hits) - len(unique)
    if removed:
        log("FIX", f"{removed} tekrar eden chunk temizlendi ({len(hits)} → {len(unique)})")
    return unique


def extract_year_from_label(label: str) -> int:
    """
    [FIX-2] Chunk label'ından yıl çıkar.
    "[DUYURU: 2025-2026 Bahar Dönemi...]" → 2026
    """
    years = re.findall(r"202[0-9]", label)
    if years:
        return max(int(y) for y in years)
    return 2020  # Bilinmeyen → en eski


def apply_recency_bonus(hits: List[dict]) -> List[dict]:
    """
    [FIX-2] Daha güncel chunk'lara rerank_score bonusu ver.
    Aynı konuda 2023 ve 2025 tarihleri varsa 2025 öne çıkar.
    """
    if not hits:
        return hits

    years = [extract_year_from_label(h.get("source_label", "") + " " + h.get("text", "")[:200]) for h in hits]
    max_year = max(years) if years else 2025

    for h, year in zip(hits, years):
        current_score = h.get("rerank_score", h.get("score", 0))
        if year == max_year and year >= 2025:
            h["rerank_score"] = current_score + 0.15
            h["score"] = h["rerank_score"]
        elif year < 2024:
            h["rerank_score"] = current_score - 0.05
            h["score"] = h["rerank_score"]

    hits.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
    return hits


# ─── RAG ENGINE ───────────────────────────────────────────────────────────────

class RAGEngine:
    """
    v4.2 Drop-in: Mevcut v4.0/4.1 engine üzerine 5 kritik fix.
    MongoDB/FAISS altyapısı değişmedi — sadece pipeline mantığı güncellendi.
    """

    def __init__(self):
        self.model:          Optional[SentenceTransformer] = None
        self.reranker:       Optional[CrossEncoder]        = None
        self.bm25:           Optional[BM25Okapi]           = None
        self.dim:            int                           = 0
        self.index:          Optional[faiss.Index]         = None
        self.metadata_store: List[dict]                    = []

    def startup(self, rebuild: bool = False) -> None:
        log("INFO", f"Embedding: {EMBED_MODEL_NAME}")
        self.model = SentenceTransformer(EMBED_MODEL_NAME)
        self.dim   = self.model.get_sentence_embedding_dimension()
        log("OK", f"dim={self.dim}")

        log("INFO", f"Re-Ranker: {RERANK_MODEL_NAME}")
        try:
            self.reranker = CrossEncoder(RERANK_MODEL_NAME)
            log("OK", "Re-Ranker hazır.")
        except Exception as e:
            log("WARN", f"Re-Ranker yüklenemedi: {e}")
            self.reranker = None

        if rebuild or not self._load_index():
            self._build_from_mongo()

        self._build_bm25()
        self._check_services()

    def _load_index(self) -> bool:
        if not os.path.exists(FAISS_PATH) or not os.path.exists(META_PATH):
            return False
        try:
            self.index = faiss.read_index(FAISS_PATH)
            with open(META_PATH, "r", encoding="utf-8") as f:
                self.metadata_store = json.load(f)
            if self.index.ntotal != len(self.metadata_store):
                return False
            log("OK", f"İndeks yüklendi: {self.index.ntotal} kayıt")

            # Tip dağılımı
            dist: Dict[str, int] = {}
            for d in self.metadata_store:
                t = d.get("source_type") or d.get("source_collection", "bilinmeyen")
                dist[t] = dist.get(t, 0) + 1
            log("INFO", f"Dağılım: {dist}")
            return True
        except Exception as e:
            log("WARN", f"İndeks yükleme hatası: {e}")
            return False

    def _build_from_mongo(self) -> None:
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=MONGO_TIMEOUT)
            col    = client[MONGO_DB][MONGO_COL]
            docs   = list(col.find({"text": {"$exists": True, "$ne": ""}}))

            if not docs:
                log("ERR", "MongoDB boş!")
                sys.exit(1)

            log("INFO", f"{len(docs)} chunk embed ediliyor...")
            # embed_text varsa onu kullan (ingestion v2.0 uyumlu)
            texts = [d.get("embed_text") or d.get("text") for d in docs]

            embeddings = self.model.encode(
                texts, show_progress_bar=True,
                convert_to_numpy=True, normalize_embeddings=True
            ).astype(np.float32)

            self.index = faiss.IndexFlatIP(self.dim)
            self.index.add(embeddings)

            self.metadata_store = []
            for d in docs:
                meta = d.get("metadata") or {}
                self.metadata_store.append({
                    "text":              d.get("raw_text") or d.get("text") or "",
                    "embed_text":        d.get("embed_text") or d.get("text") or "",
                    "source_collection": d.get("source_collection") or meta.get("source_collection", ""),
                    "source_url":        d.get("source_url") or meta.get("source_url", ""),
                    "source_label":      d.get("source_label") or "",
                    "source_type":       d.get("source_type") or meta.get("source_type", "statik"),
                })

            faiss.write_index(self.index, FAISS_PATH)
            with open(META_PATH, "w", encoding="utf-8") as f:
                json.dump(self.metadata_store, f, ensure_ascii=False)

            log("OK", f"FAISS oluşturuldu: {self.index.ntotal} vektör")

        except ConnectionFailure as e:
            log("ERR", f"MongoDB hatası: {e}")
            sys.exit(1)

    def _build_bm25(self) -> None:
        if not self.metadata_store:
            return
        try:
            corpus = [
                turkish_tokenize(d.get("embed_text") or d.get("text") or "")
                for d in self.metadata_store
            ]
            self.bm25 = BM25Okapi(corpus)
            log("OK", f"BM25 hazır: {len(corpus)} doküman")
        except Exception as e:
            log("WARN", f"BM25 hatası: {e}")

    def _check_services(self) -> None:
        try:
            r = requests.get(OLLAMA_URL.replace("/api/generate", "/api/tags"), timeout=3)
            if r.status_code == 200:
                log("OK", f"Ollama: {OLLAMA_MODEL}")
        except Exception:
            log("WARN", "Ollama bağlanamıyor → ollama serve")
        try:
            MongoClient(MONGO_URI, serverSelectionTimeoutMS=MONGO_TIMEOUT).server_info()
            log("OK", f"MongoDB: {MONGO_DB}")
        except Exception:
            log("WARN", "MongoDB bağlanamıyor")

    # ── Ana Sorgu Pipeline'ı ──────────────────────────────────────────────────

    def query(self, user_question: str) -> dict:
        t0 = time.time()

        # ── 1. Sorgu Hazırlama ────────────────────────────────────────────────
        clean_q = " ".join(user_question.split()).strip()
        norm_q  = normalize_abbreviations(clean_q)
        norm_q  = normalize_academic_calendar(norm_q)

        # [FIX-4] Sadece kural tabanlı genişletme
        expanded_q = expand_query(norm_q)

        # ── 2. FAISS Dense Search ─────────────────────────────────────────────
        q_vecs = self.model.encode(
            [norm_q, expanded_q] if expanded_q != norm_q else [norm_q],
            convert_to_numpy=True, normalize_embeddings=True
        ).astype(np.float32)
        q_vec = np.mean(q_vecs, axis=0, keepdims=True).astype(np.float32)
        faiss.normalize_L2(q_vec)

        faiss_scores_raw, faiss_indices = self.index.search(q_vec, TOP_K)

        faiss_results: Dict[int, float] = {}
        top_faiss = 0.0
        for s, idx in zip(faiss_scores_raw[0], faiss_indices[0]):
            if idx == -1:
                continue
            faiss_results[int(idx)] = float(s)
            if float(s) > top_faiss:
                top_faiss = float(s)

        # ── 3. BM25 Sparse Search ─────────────────────────────────────────────
        bm25_results: Dict[int, float] = {}
        top_bm25 = 0.0
        if self.bm25:
            tokens = turkish_tokenize(expanded_q)
            if tokens:
                all_scores  = self.bm25.get_scores(tokens)
                top_indices = np.argsort(all_scores)[::-1][:BM25_TOP_K]
                for idx in top_indices:
                    s = float(all_scores[idx])
                    if s > 0:
                        bm25_results[int(idx)] = s
                        if s > top_bm25:
                            top_bm25 = s

        log("INFO",
            f"FAISS={len(faiss_results)} BM25={len(bm25_results)} | "
            f"top_faiss={top_faiss:.3f} top_bm25={top_bm25:.1f}")

        # ── 4. Weighted RRF (k=20) ────────────────────────────────────────────
        all_idx  = set(faiss_results) | set(bm25_results)
        f_ranked = sorted(faiss_results, key=faiss_results.get, reverse=True)
        b_ranked = sorted(bm25_results,  key=bm25_results.get,  reverse=True)
        f_rank   = {idx: r for r, idx in enumerate(f_ranked)}
        b_rank   = {idx: r for r, idx in enumerate(b_ranked)}

        rrf: Dict[int, float] = {}
        for doc_idx in all_idx:
            score = 0.0
            if doc_idx in f_rank:
                score += FAISS_RRF_WEIGHT / (RRF_K + f_rank[doc_idx])
            if doc_idx in b_rank:
                score += BM25_RRF_WEIGHT  / (RRF_K + b_rank[doc_idx])
            rrf[doc_idx] = score

        sorted_cands = sorted(rrf.items(), key=lambda x: x[1], reverse=True)

        # ── 5. Iron Shield ────────────────────────────────────────────────────
        valid_hits: List[dict] = []
        for doc_idx, rrf_score in sorted_cands[:TOP_K]:
            f_s = faiss_results.get(doc_idx, 0.0)
            b_s = bm25_results.get(doc_idx, 0.0)

            passes = (f_s >= IRON_SHIELD_THRESHOLD or b_s >= BM25_MIN_SCORE)
            bypass = (b_s >= 3.0)

            if not passes and not bypass:
                continue

            doc = self.metadata_store[doc_idx]
            valid_hits.append({
                "text":              doc.get("text") or "",
                "embed_text":        doc.get("embed_text") or "",
                "source_collection": doc.get("source_collection", ""),
                "source_url":        doc.get("source_url", ""),
                "source_label":      doc.get("source_label", ""),
                "source_type":       doc.get("source_type", "statik"),
                "faiss_score":       f_s,
                "bm25_score":        b_s,
                "rrf_score":         rrf_score,
                "score":             rrf_score,
                "bypassed":          bypass and not passes,
            })

        if not valid_hits:
            log("SHIELD", f"Iron Shield! faiss_top={top_faiss:.4f}")
            return {"answer": FALLBACK_MESSAGE, "sources": [],
                    "shield_triggered": True, "confidence": 0.0,
                    "elapsed_ms": int((time.time() - t0) * 1000)}

        # ── 6. Deduplication ─────────────────────────────────────────────────
        valid_hits = deduplicate_hits(valid_hits)

        # ── 7. CrossEncoder Re-Ranking ────────────────────────────────────────
        rerank_top = 0.0
        if self.reranker and valid_hits:
            valid_hits, rerank_top = self._rerank(norm_q, valid_hits)
        else:
            valid_hits = valid_hits[:MAX_CONTEXT_CHUNKS]

        # [FIX-2] Tarih güncelliği bonusu uygula
        valid_hits = apply_recency_bonus(valid_hits)
        rerank_top = valid_hits[0].get("rerank_score", rerank_top) if valid_hits else rerank_top

        # [FIX-3] Güven yeterli değilse doğrudan fallback — LLM'e gitme
        if rerank_top < LLM_CONFIDENCE_MIN:
            log("SHIELD",
                f"Güven çok düşük ({rerank_top:.4f} < {LLM_CONFIDENCE_MIN}) → Fallback")
            return {"answer": FALLBACK_MESSAGE, "sources": valid_hits,
                    "shield_triggered": True, "confidence": rerank_top,
                    "elapsed_ms": int((time.time() - t0) * 1000)}

        # ── 8. Context Hazırlama ──────────────────────────────────────────────
        ctx_chunks = valid_hits[:MAX_CONTEXT_CHUNKS]
        ctx_parts  = []
        for i, h in enumerate(ctx_chunks, 1):
            label = h.get("source_label") or h.get("source_collection") or "Bilinmeyen"
            url   = h.get("source_url") or ""
            src   = f"[Kaynak: {label}]" + (f" {url}" if url else "")
            ctx_parts.append(f"[Bilgi {i}] {src}\n{h['text']}")

        ctx_str    = "\n\n---\n\n".join(ctx_parts)
        full_prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"METİNLER:\n\n{ctx_str}\n\n"
            f"---\n\nSORU: {clean_q}\n\nCEVAP:"
        )

        log("INFO",
            f"LLM: {len(ctx_chunks)} chunk | "
            f"faiss_top={top_faiss:.3f} | rerank_top={rerank_top:.3f}")

        # ── 9. Ollama LLM ─────────────────────────────────────────────────────
        answer = self._call_ollama(full_prompt)

        return {
            "answer":           answer,
            "sources":          ctx_chunks,
            "shield_triggered": False,
            "confidence":       rerank_top,
            "elapsed_ms":       int((time.time() - t0) * 1000),
        }

    def _rerank(self, query: str, hits: List[dict]) -> tuple:
        """CrossEncoder re-ranking."""
        candidates = hits[:RERAN_TOP_K]
        rest       = hits[RERAN_TOP_K:]
        try:
            pairs  = [[query, h["text"]] for h in candidates]
            scores = self.reranker.predict(pairs)

            for h, s in zip(candidates, scores):
                h["rerank_score"] = float(s)

            candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
            filtered = [h for h in candidates if h["rerank_score"] >= RERAN_SCORE_THRESHOLD]

            # Dinamik eşik: en az 2 chunk döndür
            if len(filtered) < 2:
                filtered = candidates[:max(2, len(candidates))]

            top = filtered[0]["rerank_score"] if filtered else 0.0
            log("INFO", f"Re-rank: {len(candidates)} → {len(filtered)} | top={top:.4f}")

            for h in filtered:
                h["score"] = h["rerank_score"]

            return filtered + rest, top

        except Exception as e:
            log("WARN", f"Re-ranking hatası: {e}")
            return hits[:MAX_CONTEXT_CHUNKS], 0.0

    def _call_ollama(self, prompt: str) -> str:
        payload = {
            "model":  OLLAMA_MODEL,
            "prompt": prompt,
            "stream": STREAMING_ENABLED,
            "options": {
                "temperature":    LLAMA_TEMPERATURE,
                "repeat_penalty": 1.1,
                "top_p":          0.9,
                "num_predict":    NUM_PREDICT,
                "num_ctx":        NUM_CTX,
            },
        }
        try:
            resp = requests.post(OLLAMA_URL, json=payload,
                                 timeout=OLLAMA_TIMEOUT, stream=STREAMING_ENABLED)
            resp.raise_for_status()
            if STREAMING_ENABLED:
                answer = ""
                print("\n  İnönü AI: ", end="", flush=True)
                for line in resp.iter_lines():
                    if line:
                        tok = json.loads(line).get("response", "")
                        print(tok, end="", flush=True)
                        answer += tok
                print("\n")
                return answer.strip()
            return resp.json().get("response", "").strip()
        except requests.exceptions.Timeout:
            return f"HATA: Ollama timeout ({OLLAMA_TIMEOUT}s). → ollama serve"
        except requests.exceptions.ConnectionError:
            return f"HATA: Ollama bağlanamıyor ({OLLAMA_URL})"
        except Exception as e:
            return f"HATA: {type(e).__name__}: {e}"


# ─── [FIX-5] GELİŞTİRİLMİŞ XAI ÇIKTISI ──────────────────────────────────────

def print_xai_report(result: dict) -> None:
    sources = result.get("sources", [])
    if not sources:
        return

    conf    = result.get("confidence", 0)
    elapsed = result.get("elapsed_ms", 0)

    print(f"\n  [XAI] v4.2 | FAISS({TOP_K})+BM25({BM25_TOP_K}) → RRF(k={RRF_K}) → ReRank → RecencyBonus → LLM")
    print(f"  [XAI] Güven:{conf:.4f} | Süre:{elapsed}ms | Kaynaklar:{len(sources)}")
    if result.get("shield_triggered"):
        print(f"  [XAI] ⛔ FALLBACK TETİKLENDİ (güven < {LLM_CONFIDENCE_MIN})")
    print("  " + "─" * 105)

    for i, s in enumerate(sources, 1):
        faiss_s  = f"{s.get('faiss_score',  0):.4f}"
        bm25_s   = f"{s.get('bm25_score',   0):.2f}"
        rrf_s    = f"{s.get('rrf_score',    0):.5f}"
        rerank_s = f"{s.get('rerank_score', 0):.4f}" if "rerank_score" in s else "  N/A "
        label    = (s.get("source_label") or s.get("source_collection") or "-")[:45]
        bypassed = " [BYPASS]" if s.get("bypassed") else ""

        print(f"  [{i:02d}] FAISS:{faiss_s} | BM25:{bm25_s} | "
              f"RRF:{rrf_s} | ReRank:{rerank_s} | {label}{bypassed}")

        # [FIX-5] Chunk içeriği önizleme
        preview = s.get("text", "")[:120].replace("\n", " ").strip()
        if preview:
            print(f"        ↳ {preview}...")

    print("  " + "─" * 105 + "\n")


# ─── TERMİNAL ARAYÜZÜ ─────────────────────────────────────────────────────────

def interactive_repl(engine: RAGEngine) -> None:
    print("\n" + "═" * 105)
    print("  İNÖNÜ AI v4.2 — 5 Kritik Fix · Dürüst Fallback · Tarih Bilinci".center(105))
    print("═" * 105)
    print(f"  Model:{OLLAMA_MODEL} | Re-Ranker:{'AÇIK' if engine.reranker else 'KAPALI'}"
          f" | BM25:{'AÇIK' if engine.bm25 else 'KAPALI'}")
    print(f"  FAISS_K:{TOP_K} BM25_K:{BM25_TOP_K} RRF_k:{RRF_K} Ctx:{MAX_CONTEXT_CHUNKS}")
    print(f"  [FIX-3] LLM güven eşiği: {LLM_CONFIDENCE_MIN} (altında fallback)")
    print(f"  [FIX-4] LLM reformülasyonu KAPALI (sadece kural tabanlı expansion)")
    print("  Komutlar: quit / xai / debug\n")

    show_xai = True
    debug    = False

    while True:
        try:
            q = input("Soru: ").strip()
            if not q:
                continue
            if q.lower() in ("quit", "exit", "q"):
                print("\nGörüşürüz!")
                break
            if q.lower() == "xai":
                show_xai = not show_xai
                print(f"  XAI: {'AÇIK' if show_xai else 'KAPALI'}")
                continue
            if q.lower() == "debug":
                debug = not debug
                print(f"  Debug: {'AÇIK' if debug else 'KAPALI'}")
                continue

            print()
            result = engine.query(q)

            if not STREAMING_ENABLED:
                print(f"İnönü AI:\n{'─'*80}")
                for line in result["answer"].split("\n"):
                    print(f" {line}")
                print("─" * 80)

            if show_xai:
                print_xai_report(result)

            if debug and result.get("sources"):
                print("  [DEBUG] Re-Rank sonrası tam sıralama:")
                for i, s in enumerate(result["sources"][:8], 1):
                    yr = extract_year_from_label(s.get("source_label","") + s.get("text","")[:100])
                    bp = " [BYPASS]" if s.get("bypassed") else ""
                    print(f"  [{i}]{bp} [{yr}] "
                          f"ReRank:{s.get('rerank_score',0):.4f} | "
                          f"{s.get('text','')[:100].replace(chr(10),' ')}...")
                print()

        except (KeyboardInterrupt, EOFError):
            print("\n\nÇıkılıyor...")
            break
        except Exception as e:
            log("ERR", f"Beklenmeyen hata: {e}")


# ─── GİRİŞ NOKTASI ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="İnönü AI RAG Engine v4.2")
    parser.add_argument("--rebuild", action="store_true",
                        help="FAISS indeksini MongoDB'den yeniden oluştur.")
    args = parser.parse_args()

    engine = RAGEngine()
    engine.startup(rebuild=args.rebuild)
    interactive_repl(engine)