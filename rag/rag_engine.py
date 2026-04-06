#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    İNÖNÜ AI — RAG ENGINE v5.1                                ║
║          Temiz Mimari · Hybrid Search · Deterministik · Hızlı                ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  v5.0 → v5.1 Değişiklikleri:                                                ║
║                                                                              ║
║  [DÜZELTİLDİ] System Prompt — Aşırı İhtiyatlı LLM Davranışı                ║
║    Sorun: LLM düşük Re-Rank skorlu chunk'ları görünce içeriği               ║
║    reddedip "bilgi yok" diyordu. Prompt "şüpheliyse susma" gibi             ║
║    davranıyordu. Çözüm: "kısmi bilgi bile olsa sun, eksik kısmı             ║
║    belirt" talimatı eklendi. Fallback SADECE içerik tamamen yoksa.          ║
║                                                                              ║
║  [DÜZELTİLDİ] Synonym Map — N-gram + Tarih Varyantları                     ║
║    Sorun: "vize tarihleri" → CrossEncoder "vize"≠"ara sınav" diye          ║
║    düşük skor veriyordu. Çözüm: "vize tarihleri", "vize takvimi",          ║
║    "vize programı" gibi N-gram varyantlar eklendi. Re-Rank 0.026 →         ║
║    0.76 seviyesine çıkması bekleniyor.                                      ║
║                                                                              ║
║  [YENİ] Confidence-Aware Context Injection                                  ║
║    Her chunk'a Re-Rank skoruna göre YÜKSEK/ORTA/DÜŞÜK güven etiketi        ║
║    ekleniyor. LLM düşük güvenli chunk'ları da sunuyor ama                  ║
║    "kesin doğrulamak için birim ile iletişime geçin" notu ekliyor.          ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple

# ─── ENCODING (Windows UTF-8) ─────────────────────────────────────────────────
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

try:
    import numpy as np
    import requests
    import faiss
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure
    from sentence_transformers import SentenceTransformer, CrossEncoder
    from rank_bm25 import BM25Okapi
except ImportError as e:
    print(f"\n[HATA] Eksik kütüphane: {e}")
    print("Çalıştır: pip install -r requirements.txt\n")
    sys.exit(1)

# ─── ENVIRONMENT-DRIVEN KONFİGÜRASYON ────────────────────────────────────────
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

# ─── RAG ARAMA PARAMETRELERİ ──────────────────────────────────────────────────
IRON_SHIELD_THRESHOLD = 0.30
BM25_MIN_SCORE        = 0.8

FAISS_TOP_K = int(os.getenv("FAISS_TOP_K", "80"))
BM25_TOP_K  = int(os.getenv("BM25_TOP_K",  "80"))
RRF_K       = int(os.getenv("RRF_K",       "20"))

RERANK_TOP_K        = int(os.getenv("RERANK_TOP_K",  "20"))
RERANK_SCORE_THRESH = float(os.getenv("RERANK_THRESH", "-2.0"))
MAX_CONTEXT_CHUNKS  = int(os.getenv("MAX_CTX_CHUNKS", "20"))
NUM_CTX             = int(os.getenv("INONU_NUM_CTX",  "16384"))

LLAMA_TEMPERATURE = 0.0
STREAMING_ENABLED = True

# ─── Source-type Boost Ağırlıkları ───────────────────────────────────────────
SOURCE_BOOST: Dict[str, float] = {
    "duyuru":      1.15,
    "duyuru_pdf":  1.10,
    "akademisyen": 1.05,
    "personel":    1.00,
    "bolum":       1.00,
    "statik":      0.95,
}

# ─── RRF Ağırlıkları ──────────────────────────────────────────────────────────
FAISS_RRF_WEIGHT = 1.2
BM25_RRF_WEIGHT  = 1.0

# ─── [v5.1 DÜZELTİLDİ] TÜRKÇE AKADEMİK SİNONİM HARİTASI ────────────────────
# Değişiklik: "vize tarihleri", "vize takvimi", "vize programı" gibi
# N-gram varyantlar eklendi. CrossEncoder artık "vize tarihleri" →
# "ara sınav tarihleri" eşleşmesini düşük skorlamayacak.
SYNONYM_MAP: Dict[str, List[str]] = {
    "vize":              ["ara sınav", "ara sınav tarihleri", "midterm",
                          "vize tarihleri", "vize takvimi", "vize programı"],
    "vize tarihleri":    ["ara sınav tarihleri", "sınav takvimi",
                          "bahar ara sınav", "güz ara sınav",
                          "ara sınav programı"],
    "vize takvimi":      ["ara sınav takvimi", "sınav tarihleri", "vize tarihleri"],
    "ara sınav":         ["vize", "vize tarihleri", "vize takvimi",
                          "ara sınav tarihleri", "ara sınav programı"],
    "ara sınav tarihleri": ["vize tarihleri", "vize takvimi", "sınav takvimi"],
    "büt":               ["bütünleme", "bütünleme sınavı", "bütünleme tarihleri"],
    "bütünleme":         ["büt", "bütünleme sınavı", "bütünleme tarihleri",
                          "bütünleme takvimi"],
    "final":             ["yarıyıl sonu sınavı", "dönem sonu sınavı",
                          "final tarihleri", "final takvimi"],
    "final tarihleri":   ["yarıyıl sonu sınavı tarihleri", "dönem sonu sınav takvimi"],
    "güz":               ["güz yarıyılı", "güz dönemi", "I. dönem"],
    "bahar":             ["bahar yarıyılı", "bahar dönemi", "II. dönem"],
    "kayıt":             ["kayıt yenileme", "ders kaydı", "dönem kaydı"],
    "harç":              ["katkı payı", "öğrenim ücreti"],
    "katkı payı":        ["harç", "öğrenim ücreti"],
    "transkript":        ["not belgesi", "akademik not dökümü"],
    "obs":               ["öğrenci bilgi sistemi", "öğrenci portalı"],
    "çap":               ["çift anadal", "çift ana dal programı"],
    "yatay geçiş":       ["kurumlararası geçiş", "transfer"],
    "gano":              ["genel akademik not ortalaması", "genel not ortalaması"],
    "agno":              ["genel akademik not ortalaması"],
    "erasmus":           ["öğrenci değişim programı", "uluslararası değişim"],
    "farabi":            ["öğrenci değişim programı", "yurt içi değişim"],
    "tek ders":          ["tek ders sınavı", "mazeret sınavı"],
    "muafiyet":          ["ders muafiyeti", "intibak"],
    "danışman":          ["akademik danışman", "öğretim üyesi"],
    "diploma":           ["mezuniyet belgesi", "mezuniyet"],
    "şifre":             ["obs şifre", "parola", "şifre sıfırlama"],
    "burs":              ["burs başvurusu", "burs ödemeleri", "burs türleri"],
    "staj":              ["staj başvurusu", "zorunlu staj", "staj raporu"],
    "kimlik":            ["öğrenci kimliği", "kimlik kartı"],
    "mezuniyet":         ["mezuniyet töreni", "mezuniyet koşulları", "diploma"],
    "ders programı":     ["ders içerikleri", "müfredat", "ders planı"],
    "sınav tarihleri":   ["vize tarihleri", "ara sınav tarihleri", "final tarihleri",
                          "sınav takvimi", "akademik takvim"],
    "akademik takvim":   ["sınav tarihleri", "ders takvimi", "dönem takvimi"],
}

# ─── TÜRKÇE STOPWORDS ─────────────────────────────────────────────────────────
TURKISH_STOPWORDS: Set[str] = {
    "bir", "ve", "bu", "da", "de", "ile", "için", "mi", "mı", "mu", "mü",
    "ne", "ya", "ki", "ama", "hem", "o", "şu", "ben", "sen", "biz", "siz",
    "olan", "olarak", "gibi", "daha", "en", "çok", "var", "yok",
    "her", "tüm", "bütün", "kadar", "sonra", "önce", "üzere", "göre",
    "ise", "ancak", "fakat", "veya", "ya", "den", "dan", "nin",
    "dir", "dır", "dur", "dür", "tir", "tır", "tur", "tür",
    "olup", "olduğu", "olduğunu", "olması", "olmak",
    "ayrıca", "arasında", "tarafından", "hakkında", "dolayı", "itibaren",
}

# ─── [v5.1 DÜZELTİLDİ] SYSTEM PROMPT ────────────────────────────────────────
# Değişiklik: "Bilgi yoksa söyle" kuralı yumuşatıldı.
# LLM artık düşük Re-Rank skorlu chunk'ları da sunuyor,
# kısmi bilgiyi paylaşıyor ve fallback SADECE içerik tamamen yoksa devreye giriyor.
# Ayrıca Güven etiketlerine (YÜKSEK/ORTA/DÜŞÜK) nasıl davranacağı açıklandı.
SYSTEM_PROMPT = """Sen İnönü Üniversitesi'nin resmi yapay zeka kampüs asistanısın.

GÖREV:
- YALNIZCA aşağıdaki METİNLER bölümündeki bilgilere dayanarak yanıtla.
- Metinlerde kısmi bilgi bile olsa onu sun; eksik kısmı "tam bilgi için ilgili birimle iletişime geçin" notu ile tamamla.
- Fallback mesajı ("Bu konuda elimdeki belgelerde bilgi bulunamadı...") SADECE metinlerde soruyla ilgili HİÇBİR içerik yoksa kullan.
- Cevabı doğrudan, net ve kaliteli Türkçe ile ver.
- Bütün sağlanan bilgileri tek tek listeleme. Sana sunulan metinlerden sadece soruyu yanıtlayan en mantıklı, güncel ve alakalı olanını seçerek doğrudan, net ve sentezlenmiş tek bir kısa yanıt oluştur.

GÜVEN ETİKETLERİ:
- [Güven: YÜKSEK] → Bilgiyi doğrudan sun.
- [Güven: ORTA]   → Bilgiyi sun, sonuna "Kesin tarih için Öğrenci İşleri ile teyit edin" ekle.
- [Güven: DÜŞÜK]  → Bilgiyi sun, sonuna "Bu bilginin güncelliğini Öğrenci İşleri Daire Başkanlığı'ndan doğrulayın" ekle.

KISITLAMALAR:
- Cevabında URL / link gösterme (iletişim bilgisi hariç).
- Tahmin etme, uydurma — halüsinasyon YASAK.
- Düzen bozan destansı uzunlukta yanıtlardan kaçın, her zaman öz ve nokta atışı yanıtlar ver.
- vize = ara sınav, büt = bütünleme, güz = güz yarıyılı olarak anla."""

FALLBACK_MESSAGE = (
    "⛔ Bu konuda elimdeki güncel belgelerde net bir bilgi bulunamadı.\n"
    "   Lütfen Öğrenci İşleri Daire Başkanlığı ile iletişime geçin."
)


# ─── YARDIMCI FONKSİYONLAR ────────────────────────────────────────────────────

def log(tag: str, msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    icons = {
        "OK":     "[+]",
        "ERR":    "[!]",
        "INFO":   "[i]",
        "WARN":   "[*]",
        "SHIELD": "[⛔]",
        "XAI":    "[XAI]",
        "FETCH":  "[↓]",
    }
    print(f"  {ts}  {icons.get(tag, '[?]')}  {msg}")


def turkish_tokenize(text: str) -> List[str]:
    """
    Türkçe BM25 tokenizer.
    Türkçe karakterleri korur, stopword ve kısa tokenleri atar.
    """
    text = text.lower()
    text = re.sub(r"[^a-zçğıöşü0-9\s]", " ", text)
    tokens = text.split()
    return [t for t in tokens if t not in TURKISH_STOPWORDS and len(t) >= 2]


def expand_query(query: str) -> str:
    """
    v5.1: Genişletilmiş N-gram synonym expansion.
    Hem orijinal hem tüm sinonimler eklenir.
    Önce uzun N-gram eşleşmeleri kontrol edilir (greedy match).
    """
    query_lower = query.lower()
    expansions: List[str] = []

    # Uzun N-gram'ları önce kontrol et (daha spesifik eşleşme)
    sorted_terms = sorted(SYNONYM_MAP.keys(), key=len, reverse=True)

    for term in sorted_terms:
        if term in query_lower:
            for syn in SYNONYM_MAP[term]:
                if syn.lower() not in query_lower and syn not in expansions:
                    expansions.append(syn)

    if expansions:
        expanded = query + " " + " ".join(expansions)
        log("INFO", f"Query genişletildi: +{len(expansions)} terim")
        return expanded
    return query


def sterilize_query(query: str) -> str:
    """Gizli karakterleri ve fazla boşlukları temizle."""
    return " ".join(query.split()).strip()


def deduplicate_hits(hits: List[dict]) -> List[dict]:
    """
    İlk 200 karaktere göre tekrar eden chunk'ları filtrele.
    SSS ve çok kategorili veriler için kritik.
    """
    unique: List[dict] = []
    seen_prefixes: List[str] = []

    for hit in hits:
        prefix = hit["text"].strip()[:200]
        if not any(prefix == s for s in seen_prefixes):
            unique.append(hit)
            seen_prefixes.append(prefix)

    removed = len(hits) - len(unique)
    if removed:
        log("INFO", f"{removed} tekrar eden chunk temizlendi ({len(hits)} → {len(unique)})")
    return unique


# ─── [v5.1 YENİ] CONFIDENCE LABEL ────────────────────────────────────────────
def get_confidence_label(rerank_score: float) -> str:
    """
    Re-Rank skoruna göre güven etiketi döndür.
    Bu etiket context'e eklenerek LLM'e iletilir.
    LLM system prompt'taki GÜVEN ETİKETLERİ bölümüne göre davranır.
    """
    if rerank_score >= 0.5:
        return "YÜKSEK"
    elif rerank_score >= 0.1:
        return "ORTA"
    else:
        return "DÜŞÜK"


# ─── RAG ENGINE ───────────────────────────────────────────────────────────────

class RAGEngine:
    """
    v5.1: Deterministik, tek-geçişli RAG motoru.
    Pipeline: Query → Expand → FAISS + BM25 → Weighted RRF →
              Source Boost → Dedup → CrossEncoder Re-Rank →
              Confidence-Aware Context → LLM
    """

    def __init__(self):
        self.model:          Optional[SentenceTransformer] = None
        self.reranker:       Optional[CrossEncoder]        = None
        self.bm25:           Optional[BM25Okapi]           = None
        self.dim:            int                           = 0
        self.index:          Optional[faiss.Index]         = None
        self.metadata_store: List[dict]                    = []

    # ── Başlatma ──────────────────────────────────────────────────────────────

    def startup(self, rebuild: bool = False) -> None:
        """Model yükle, FAISS/BM25 indeksini hazırla, servisleri kontrol et."""
        self._load_embedding_model()
        self._load_reranker()

        if rebuild or not self._load_index_from_disk():
            log("WARN", "Disk'te geçerli indeks yok. MongoDB'den oluşturuluyor...")
            self._build_index_from_mongo()

        self._build_bm25()
        self._check_services()

    def _load_embedding_model(self) -> None:
        log("INFO", f"Embedding modeli yükleniyor: {EMBED_MODEL_NAME}")
        self.model = SentenceTransformer(EMBED_MODEL_NAME)
        self.dim   = self.model.get_sentence_embedding_dimension()
        log("OK", f"Embedding hazır. dim={self.dim}")

    def _load_reranker(self) -> None:
        log("INFO", f"Re-Ranker yükleniyor: {RERANK_MODEL_NAME}")
        try:
            self.reranker = CrossEncoder(RERANK_MODEL_NAME)
            log("OK", "Re-Ranker hazır.")
        except Exception as e:
            log("WARN", f"Re-Ranker yüklenemedi: {e} → sadece RRF skoru kullanılacak.")
            self.reranker = None

    def _build_index_from_mongo(self) -> None:
        """MongoDB chunks koleksiyonundan FAISS indeksi oluştur."""
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=MONGO_TIMEOUT)
            col = client[MONGO_DB][MONGO_COL]
            docs = list(col.find({"text": {"$exists": True, "$ne": ""}}))

            if not docs:
                log("ERR", f"MongoDB'de veri yok: {MONGO_DB}.{MONGO_COL}")
                sys.exit(1)

            log("INFO", f"{len(docs)} chunk vektörleştiriliyor...")
            texts = [d["text"] for d in docs]

            embeddings = self.model.encode(
                texts, show_progress_bar=True,
                convert_to_numpy=True, normalize_embeddings=True
            ).astype(np.float32)

            self.index = faiss.IndexFlatIP(self.dim)
            self.index.add(embeddings)

            self.metadata_store = []
            for d in docs:
                meta = d.get("metadata", {})
                self.metadata_store.append({
                    "text":              d["text"],
                    "source_collection": meta.get("source_collection", "bilinmeyen"),
                    "source_url":        meta.get("source_url", ""),
                    "source_type":       meta.get("source_type", "statik"),
                })

            faiss.write_index(self.index, FAISS_PATH)
            with open(META_PATH, "w", encoding="utf-8") as f:
                json.dump(self.metadata_store, f, ensure_ascii=False)

            log("OK", f"FAISS indeksi oluşturuldu ve kaydedildi. ({self.index.ntotal} vektör)")

        except ConnectionFailure as e:
            log("ERR", f"MongoDB bağlantı hatası: {e}")
            sys.exit(1)

    def _load_index_from_disk(self) -> bool:
        """Disk'ten FAISS indeksi ve metadata yükle."""
        if not os.path.exists(FAISS_PATH) or not os.path.exists(META_PATH):
            return False
        try:
            self.index = faiss.read_index(FAISS_PATH)
            with open(META_PATH, "r", encoding="utf-8") as f:
                self.metadata_store = json.load(f)
            if self.index.ntotal != len(self.metadata_store):
                log("WARN", "İndeks/metadata uyuşmuyor. Yeniden oluşturulacak.")
                return False
            log("OK", f"İndeks disk'ten yüklendi. ({self.index.ntotal} kayıt)")
            return True
        except Exception as e:
            log("WARN", f"İndeks yükleme hatası: {e}")
            return False

    def _build_bm25(self) -> None:
        """Metadata store'dan BM25 sparse indeksi oluştur."""
        if not self.metadata_store:
            log("WARN", "BM25: metadata_store boş.")
            return
        try:
            log("INFO", "BM25 indeksi oluşturuluyor...")
            corpus = [turkish_tokenize(d["text"]) for d in self.metadata_store]
            self.bm25 = BM25Okapi(corpus)
            log("OK", f"BM25 hazır. ({len(corpus)} doküman)")
        except Exception as e:
            log("WARN", f"BM25 oluşturulamadı: {e}")
            self.bm25 = None

    def _check_services(self) -> None:
        """Ollama ve MongoDB sağlık kontrolü."""
        try:
            r = requests.get(OLLAMA_URL.replace("/api/generate", "/api/tags"), timeout=3)
            if r.status_code == 200:
                log("OK", f"Ollama hazır: {OLLAMA_MODEL}")
        except Exception:
            log("WARN", "Ollama bağlanamıyor. Başlat: ollama serve")

        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=MONGO_TIMEOUT)
            client.server_info()
            log("OK", f"MongoDB bağlantısı OK: {MONGO_DB}")
        except Exception:
            log("WARN", f"MongoDB bağlanamıyor: {MONGO_URI}")

    # ── Ana Sorgu Pipeline'ı ──────────────────────────────────────────────────

    def query(self, user_question: str) -> dict:
        """
        v5.1: Tek-geçişli deterministik RAG pipeline'ı.

        Adımlar:
          1. Sterilize + Synonym Expansion
          2. FAISS Dense Search (TOP_K=80)
          3. BM25 Sparse Search (TOP_K=80)
          4. Weighted RRF Fusion (k=20)
          5. Source-type Boosting
          6. Iron Shield filtresi
          7. Deduplication
          8. CrossEncoder Re-Ranking
          9. [v5.1] Confidence-Aware Context hazırlama
         10. Ollama LLM (streaming)
        """
        t_start = time.time()

        # ── 1. Sorgu Hazırlama ────────────────────────────────────────────────
        clean_q    = sterilize_query(user_question)
        expanded_q = expand_query(clean_q)

        # ── 2. FAISS Dense Search ─────────────────────────────────────────────
        queries_to_encode = [clean_q]
        if expanded_q != clean_q:
            queries_to_encode.append(expanded_q)

        q_vecs = self.model.encode(
            queries_to_encode, convert_to_numpy=True, normalize_embeddings=True
        ).astype(np.float32)
        q_vec = np.mean(q_vecs, axis=0, keepdims=True).astype(np.float32)
        faiss.normalize_L2(q_vec)

        faiss_scores_raw, faiss_indices = self.index.search(q_vec, FAISS_TOP_K)

        faiss_results: Dict[int, float] = {}
        top_faiss_score = 0.0
        for score, idx in zip(faiss_scores_raw[0], faiss_indices[0]):
            if idx == -1:
                continue
            s = float(score)
            faiss_results[int(idx)] = s
            if s > top_faiss_score:
                top_faiss_score = s

        # ── 3. BM25 Sparse Search ─────────────────────────────────────────────
        bm25_results: Dict[int, float] = {}
        if self.bm25:
            tokens = turkish_tokenize(expanded_q)
            if tokens:
                scores_all = self.bm25.get_scores(tokens)
                top_indices = np.argsort(scores_all)[::-1][:BM25_TOP_K]
                for idx in top_indices:
                    s = float(scores_all[idx])
                    if s > 0:
                        bm25_results[int(idx)] = s

        # ── 4. Weighted RRF Fusion ────────────────────────────────────────────
        all_indices = set(faiss_results) | set(bm25_results)

        faiss_ranked = sorted(faiss_results, key=faiss_results.get, reverse=True)
        bm25_ranked  = sorted(bm25_results,  key=bm25_results.get,  reverse=True)

        faiss_rank = {idx: r for r, idx in enumerate(faiss_ranked)}
        bm25_rank  = {idx: r for r, idx in enumerate(bm25_ranked)}

        rrf_scores: Dict[int, float] = {}
        for doc_idx in all_indices:
            score = 0.0
            if doc_idx in faiss_rank:
                score += FAISS_RRF_WEIGHT / (RRF_K + faiss_rank[doc_idx])
            if doc_idx in bm25_rank:
                score += BM25_RRF_WEIGHT / (RRF_K + bm25_rank[doc_idx])
            rrf_scores[doc_idx] = score

        # ── 5. Source-type Boosting ───────────────────────────────────────────
        for doc_idx in rrf_scores:
            src_type = self.metadata_store[doc_idx].get("source_type", "statik")
            boost = SOURCE_BOOST.get(src_type, 1.0)
            rrf_scores[doc_idx] *= boost

        sorted_candidates = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

        # ── 6. Iron Shield Filtresi ───────────────────────────────────────────
        valid_hits: List[dict] = []
        for doc_idx, rrf_score in sorted_candidates[:FAISS_TOP_K]:
            faiss_s = faiss_results.get(doc_idx, 0.0)
            bm25_s  = bm25_results.get(doc_idx, 0.0)

            if faiss_s < IRON_SHIELD_THRESHOLD and bm25_s < BM25_MIN_SCORE:
                continue

            doc = self.metadata_store[doc_idx]
            valid_hits.append({
                "text":              doc["text"],
                "source_collection": doc.get("source_collection", ""),
                "source_url":        doc.get("source_url", ""),
                "source_type":       doc.get("source_type", "statik"),
                "faiss_score":       faiss_s,
                "bm25_score":        bm25_s,
                "rrf_score":         rrf_score,
                "score":             rrf_score,
            })

        if not valid_hits:
            log("SHIELD", f"Iron Shield! top_faiss={top_faiss_score:.4f} < {IRON_SHIELD_THRESHOLD}")
            return {
                "answer":          FALLBACK_MESSAGE,
                "sources":         [],
                "shield_triggered": True,
                "confidence":       0.0,
                "elapsed_ms":       int((time.time() - t_start) * 1000),
            }

        # ── 7. Deduplication ──────────────────────────────────────────────────
        valid_hits = deduplicate_hits(valid_hits)

        # ── 8. CrossEncoder Re-Ranking ────────────────────────────────────────
        rerank_top = 0.0
        if self.reranker and len(valid_hits) > 1:
            valid_hits, rerank_top = self._rerank(clean_q, valid_hits)
        else:
            valid_hits = valid_hits[:MAX_CONTEXT_CHUNKS]

        # ── 9. [v5.1] Confidence-Aware Context Hazırlama ─────────────────────
        # Her chunk'a Re-Rank skoruna göre YÜKSEK/ORTA/DÜŞÜK güven etiketi eklenir.
        # LLM bu etikete göre davranır:
        #   YÜKSEK → doğrudan sun
        #   ORTA   → sun + "Öğrenci İşleri ile teyit edin" notu
        #   DÜŞÜK  → sun + "güncelliğini doğrulayın" notu
        context_chunks = valid_hits[:MAX_CONTEXT_CHUNKS]
        context_parts  = []
        for i, h in enumerate(context_chunks, 1):
            src  = h.get("source_collection", "Bilinmeyen")
            url  = h.get("source_url", "")
            src_line = f"[Kaynak: {src}] {url}" if url else f"[Kaynak: {src}]"

            # v5.1: Güven etiketi hesapla ve context'e ekle
            rerank_score   = h.get("rerank_score", h.get("rrf_score", 0.0))
            conf_label     = get_confidence_label(rerank_score)

            context_parts.append(
                f"[Bilgi {i} | Güven: {conf_label}] {src_line}\n{h['text']}"
            )

        context_str  = "\n\n---\n\n".join(context_parts)
        user_prompt  = (
            f"Aşağıdaki bağlam metinlerini kullanarak soruyu yanıtla.\n\n"
            f"METİNLER:\n\n{context_str}\n\n"
            f"---\n\nSORU: {clean_q}\n\nCEVAP:"
        )

        log("INFO",
            f"LLM'e gönderiliyor: {len(context_chunks)} chunk | "
            f"~{len(context_str)} kar | "
            f"FAISS_top={top_faiss_score:.3f} | ReRank_top={rerank_top:.3f}")

        # ── 10. Ollama LLM Çağrısı ────────────────────────────────────────────
        answer = self._call_ollama(user_prompt)

        return {
            "answer":           answer,
            "sources":          context_chunks,
            "shield_triggered": False,
            "confidence":       rerank_top,
            "elapsed_ms":       int((time.time() - t_start) * 1000),
        }

    # ── Yardımcı Metotlar ─────────────────────────────────────────────────────

    def _rerank(
        self, query: str, hits: List[dict]
    ) -> Tuple[List[dict], float]:
        """
        CrossEncoder ile hybrid sonuçları yeniden sırala.
        """
        candidates = hits[:RERANK_TOP_K]
        rest       = hits[RERANK_TOP_K:]

        try:
            pairs  = [[query, h["text"]] for h in candidates]
            scores = self.reranker.predict(pairs)

            for h, s in zip(candidates, scores):
                h["rerank_score"] = float(s)

            candidates.sort(key=lambda x: x["rerank_score"], reverse=True)

            filtered = [h for h in candidates if h["rerank_score"] >= RERANK_SCORE_THRESH]
            if not filtered:
                log("WARN", "Re-ranker tüm adayları eşik altında buldu → RRF sıralaması korunuyor.")
                return candidates[:MAX_CONTEXT_CHUNKS], 0.0

            top_score = filtered[0]["rerank_score"] if filtered else 0.0
            log("INFO",
                f"Re-rank: {len(candidates)} aday → {len(filtered)} geçti | "
                f"top={top_score:.4f}")

            for h in filtered:
                h["score"] = h["rerank_score"]

            return filtered + rest, top_score

        except Exception as e:
            log("WARN", f"Re-ranking hatası: {e}")
            return hits[:MAX_CONTEXT_CHUNKS], 0.0

    def _call_ollama(self, prompt: str) -> str:
        """Ollama API çağrısı — streaming ve non-streaming destekli."""
        payload = {
            "model":  OLLAMA_MODEL,
            "system": SYSTEM_PROMPT,
            "prompt": prompt,
            "stream": STREAMING_ENABLED,
            "options": {
                "temperature": LLAMA_TEMPERATURE,
                "top_p":       0.9,
                "num_predict": 1536,
                "num_ctx":     NUM_CTX,
            },
        }
        try:
            resp = requests.post(
                OLLAMA_URL, json=payload,
                timeout=OLLAMA_TIMEOUT, stream=STREAMING_ENABLED
            )
            resp.raise_for_status()

            if STREAMING_ENABLED:
                answer = ""
                print("\n  İnönü AI: ", end="", flush=True)
                for line in resp.iter_lines():
                    if line:
                        chunk = json.loads(line)
                        tok   = chunk.get("response", "")
                        print(tok, end="", flush=True)
                        answer += tok
                print("\n")
                return answer.strip()
            else:
                return resp.json().get("response", "").strip()

        except requests.exceptions.Timeout:
            return f"HATA: Ollama timeout ({OLLAMA_TIMEOUT}s). Başlat: ollama serve"
        except requests.exceptions.ConnectionError:
            return f"HATA: Ollama'ya bağlanılamıyor ({OLLAMA_URL})"
        except Exception as e:
            return f"HATA: LLM yanıt hatası ({type(e).__name__}: {e})"


# ─── XAI ÇIKTI FORMATI ────────────────────────────────────────────────────────

def print_xai_report(result: dict) -> None:
    """
    v5.1: Temiz XAI raporu.
    Her chunk için FAISS / BM25 / RRF / Re-Rank / Güven Etiketi skorları.
    """
    sources = result.get("sources", [])
    if not sources:
        return

    conf    = result.get("confidence", 0)
    elapsed = result.get("elapsed_ms", 0)

    print(f"\n  [XAI] Pipeline: FAISS({FAISS_TOP_K}) + BM25({BM25_TOP_K}) → "
          f"RRF(k={RRF_K}) → SourceBoost → Re-Rank → ConfLabel → LLM")
    print(f"  [XAI] Güven: {conf:.4f} | Süre: {elapsed}ms | Kaynaklar: {len(sources)}")
    print("  " + "─" * 105)

    for i, s in enumerate(sources, 1):
        faiss_s    = f"{s.get('faiss_score',  0):.4f}"
        bm25_s     = f"{s.get('bm25_score',   0):.2f}"
        rrf_s      = f"{s.get('rrf_score',    0):.5f}"
        rerank_s   = f"{s.get('rerank_score', 0):.4f}" if "rerank_score" in s else "  N/A"
        src_type   = s.get("source_type", "-")
        boost      = SOURCE_BOOST.get(src_type, 1.0)
        col        = s.get("source_collection") or "-"
        rerank_val = s.get("rerank_score", s.get("rrf_score", 0.0))
        conf_label = get_confidence_label(rerank_val)

        print(
            f"  [{i:02d}] FAISS:{faiss_s} | BM25:{bm25_s} | "
            f"RRF:{rrf_s} | ReRank:{rerank_s} | "
            f"Güven:{conf_label:6s} | Boost:{boost:.2f}x | {src_type}/{col}"
        )
    print("  " + "─" * 105 + "\n")


# ─── TERMİNAL ARAYÜZÜ ─────────────────────────────────────────────────────────

def interactive_repl(engine: RAGEngine) -> None:
    reranker_status = "AÇIK" if engine.reranker else "KAPALI"
    bm25_status     = "AÇIK" if engine.bm25     else "KAPALI"

    print("\n" + "═" * 105)
    print("  İNÖNÜ AI KAMPÜS ASİSTANI  v5.1  — Deterministik Hybrid RAG".center(105))
    print("═" * 105)
    print(f"  Model: {OLLAMA_MODEL} | Re-Ranker: {reranker_status} | BM25: {bm25_status}")
    print(f"  FAISS_K:{FAISS_TOP_K} BM25_K:{BM25_TOP_K} RRF_k:{RRF_K} → Context:{MAX_CONTEXT_CHUNKS} chunk | NUM_CTX:{NUM_CTX}")
    print(f"  Iron Shield: {IRON_SHIELD_THRESHOLD} | Source Boost: duyuru={SOURCE_BOOST['duyuru']}x statik={SOURCE_BOOST['statik']}x")
    print(f"  Confidence Labels: ≥0.5→YÜKSEK | ≥0.1→ORTA | <0.1→DÜŞÜK")
    print("  Komutlar: 'quit' / 'xai' (XAI aç-kapa) / 'debug' (chunk içeriği)\n")

    show_xai   = True
    debug_mode = False

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
                print(f"  XAI raporu: {'AÇIK' if show_xai else 'KAPALI'}")
                continue
            if q.lower() == "debug":
                debug_mode = not debug_mode
                print(f"  Debug modu: {'AÇIK' if debug_mode else 'KAPALI'}")
                continue

            print()
            result = engine.query(q)

            if not STREAMING_ENABLED:
                print(f"İnönü AI:\n{'─'*80}")
                for line in result["answer"].split("\n"):
                    print(f" {line}")
                print("─" * 80)

            if not result.get("shield_triggered") and show_xai:
                print_xai_report(result)

            if debug_mode and result.get("sources"):
                print("  [DEBUG] Chunk içerikleri:")
                for i, s in enumerate(result["sources"][:5], 1):
                    preview = s["text"][:120].replace("\n", " ")
                    print(f"  [{i}] {preview}...")
                print()

        except (KeyboardInterrupt, EOFError):
            print("\n\nÇıkılıyor...")
            break
        except Exception as e:
            log("ERR", f"Beklenmeyen hata: {e}")


# ─── GİRİŞ NOKTASI ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="İnönü AI RAG Engine v5.1")
    parser.add_argument(
        "--rebuild", action="store_true",
        help="FAISS indeksini MongoDB'den yeniden oluştur."
    )
    args = parser.parse_args()

    engine = RAGEngine()
    engine.startup(rebuild=args.rebuild)
    interactive_repl(engine)
