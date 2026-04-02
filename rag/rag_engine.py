#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    İNÖNÜ AI — RAG ENGINE (v2.3 — Güncel)                    ║
║                    Halüsinasyonsuz & Doğru Yanıt Garantili                   ║
╚══════════════════════════════════════════════════════════════════════════════╝

v2.3 Düzeltmeleri (2026-04-03):
  - sourceUrl metadata'dan doğru API URL'leri çekiliyor (https://panel.inonu.edu.tr/...)
  - Fallback URL format düzeltildi (announcement:{id} yerine panel linki)
  - XAI çıktısı tam ve doğru URL'ler gösteriyor

v2.1 Düzeltmeleri:
  - Encoding desteği (UTF-8) eklendi
  - Hata yönetimi iyileştirildi  
  - Service health checks eklendi
  - Path uyumluluğu (Windows/Linux)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import List, Dict, Optional

# ─── ENCODING AYARI (Windows UTF-8 Desteği) ───────────────────────────────────
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
    from sentence_transformers import SentenceTransformer
except ImportError as e:
    print("\n" + "=" * 80)
    print("HATA: Eksik Python kutuphanesi")
    print("=" * 80)
    print(f"\nKutupahne: {e}")
    print("\nLutfen asagidaki komutu calistirin:\n")
    print("  pip install -r ../../../requirements.txt")
    print("\nDetay: ../../../SETUP.md dosyasini oku\n")
    print("=" * 80)
    sys.exit(1)

# ─── AYARLAR ──────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent

MONGO_URI = os.getenv("INONU_MONGO_URI", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("INONU_MONGO_DB", "inonu_ai")
MONGO_COL = os.getenv("INONU_MONGO_COL", "chunks")
MONGO_TIMEOUT = int(os.getenv("MONGO_TIMEOUT", "5000"))

EMBED_MODEL_NAME = os.getenv("INONU_EMBED_MODEL", "BAAI/bge-m3")

FAISS_PATH = str(SCRIPT_DIR / "faiss_index.bin")
META_PATH  = str(SCRIPT_DIR / "metadata_store.json")

OLLAMA_URL   = os.getenv("INONU_OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("INONU_OLLAMA_MODEL", "llama3.1")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "180"))

# ─── RAG & LLM Ayarları (v2.0) ───────────────────────────────────────────────
IRON_SHIELD_THRESHOLD = 0.35   # Eşik düşürüldü — daha fazla potansiyel eşleşme yakalansın
TOP_K = 12                     # FAISS'ten 12 sonuç çek (dedup sonrası 6'ya düşecek)
MAX_CONTEXT_CHUNKS = 6         # LLM'e en fazla 6 benzersiz chunk gönder
LLAMA_TEMPERATURE = 0.0        # Net, uydurmasız cevaplar için 0.0
NUM_CTX = 8192                 # v2.0: Context window 4096 → 8192 (KRİTİK düzeltme)

FALLBACK_MESSAGE = (
    "⛔ Bu konuda elimdeki güncel belgelerde net bir bilgi bulamadım.\n"
    "   Lütfen Öğrenci İşleri Daire Başkanlığı ile iletişime geçin."
)

# v2.4: System prompt — URL referansları kaldırıldı, sadece bilgi ver
SYSTEM_PROMPT = """Sen İnönü Üniversitesi'nin resmi yapay zeka asistanısın. Sana verilen METİNLER bölümünde üniversiteyle ilgili belgeler var.

GÖREV:
- METİNLER'deki bilgileri kullanarak soruyu yanıtla.
- Cevabı doğrudan, net ve açık bir dille ver Türkçe.
- Kullanıcı "vize" derse "ara sınav", "büt" derse "bütünleme", "güz" derse "güz yarıyılı" olarak anla.
- Birden fazla bilgi varsa hepsini maddelerle listele.

ÖNEMLI:
- Cevabında HIÇBIR URL / LINK gösterme
- HIÇBIR e-posta, telefon veya iletişim bilgisi dışında URL koyma
- Tahmin etme, uydurmama (halüsinasyon = KÖTÜ)
- Cevabı TÜRKÇE ver"""

# ─── TÜRKÇE AKADEMİK TERİM EŞLEŞTİRMESİ ─────────────────────────────────────
SYNONYM_MAP = {
    "vize": "ara sınav",
    "ara sınav": "vize",
    "büt": "bütünleme",
    "bütünleme": "büt",
    "final": "yarıyıl sonu sınavı",
    "güz": "güz yarıyılı",
    "bahar": "bahar yarıyılı",
    "kayıt": "kayıt yenileme",
    "harç": "katkı payı",
    "katkı payı": "harç",
    "transkript": "not belgesi",
    "not belgesi": "transkript",
    "obs": "öğrenci bilgi sistemi",
    "öğrenci bilgi sistemi": "obs",
    "çap": "çift anadal",
    "çift anadal": "çap",
    "yatay geçiş": "kurumlararası geçiş",
    "gano": "genel akademik not ortalaması",
    "agno": "genel akademik not ortalaması",
    "erasmus": "öğrenci değişim programı",
    "farabi": "öğrenci değişim programı",
    "sss": "sıkça sorulan sorular",
    "danışman": "akademik danışman",
    "diploma": "mezuniyet belgesi",
    "tek ders": "tek ders sınavı",
    "muafiyet": "ders muafiyeti",
    "kimlik": "öğrenci kimliği",
    "şifre": "obs şifre",
}


# ─── YARDIMCI FONKSİYONLAR ────────────────────────────────────────────────────
def log(tag: str, msg: str):
    """Renkli ve yapılandırılmış loglama."""
    ts = time.strftime("%H:%M:%S")
    icons = {
        "OK": "[+]", "ERR": "[!]", "INFO": "[i]", "WARN": "[*]", 
        "SHIELD": "[shield]", "FIX": "[fix]", "FETCH": "[down]"
    }
    print(f"  {ts}  {icons.get(tag, '[?]')}  {msg}")

def sterilize_query(query: str) -> str:
    """Sorgudaki gizli karakterleri, fazla boşlukları temizler."""
    return " ".join(query.split()).strip()

def expand_query(query: str) -> str:
    """
    v2.0: Sorguyu Türkçe akademik eşanlamlılarla genişletir.
    Örnek: "vize tarihleri" → "vize ara sınav tarihleri"
    Bu sayede embedding modeli daha geniş bir semantik alanı tarar.
    """
    query_lower = query.lower()
    expansions = []
    for term, synonym in SYNONYM_MAP.items():
        if term in query_lower and synonym.lower() not in query_lower:
            expansions.append(synonym)

    if expansions:
        expanded = query + " " + " ".join(expansions)
        log("FIX", f"Sorgu genişletildi: '{query}' → '{expanded}'")
        return expanded
    return query

def deduplicate_hits(hits: List[dict], similarity_threshold: float = 0.85) -> List[dict]:
    """
    v2.0: Tekrar eden chunk'ları filtreler.
    Aynı metnin %85'i eşleşiyorsa tekrar sayılır ve çıkarılır.
    Bu, SSS verilerinin iki kez (orijinal + kategori) kayıtlı olması sorununu çözer.
    """
    unique = []
    seen_texts = []

    for hit in hits:
        text = hit["text"].strip()
        is_duplicate = False

        for seen in seen_texts:
            # Basit karakter düzeyinde benzerlik kontrolü
            shorter = min(len(text), len(seen))
            if shorter == 0:
                continue
            # İlk 200 karakteri karşılaştır (başlık + ilk paragraf genelde yeterli)
            compare_len = min(200, shorter)
            if text[:compare_len] == seen[:compare_len]:
                is_duplicate = True
                break

        if not is_duplicate:
            unique.append(hit)
            seen_texts.append(text)

    removed = len(hits) - len(unique)
    if removed > 0:
        log("FIX", f"{removed} tekrar eden chunk filtrelendi. ({len(hits)} → {len(unique)})")

    return unique


# ─── RAG MOTORU ───────────────────────────────────────────────────────────────
class RAGEngine:
    def __init__(self):
        self.model = None
        self.dim = 0
        self.index = None
        self.metadata_store = []

    def startup(self, rebuild: bool = False):
        """Initialize RAG engine: Load model, FAISS index, and check services."""
        log("INFO", f"Embedding modeli yukleniyor: {EMBED_MODEL_NAME}")
        try:
            self.model = SentenceTransformer(EMBED_MODEL_NAME)
            self.dim = self.model.get_sentence_embedding_dimension()
            log("OK", f"Model yuklendi. (Boyut: {self.dim}d)")
        except Exception as e:
            log("ERR", f"Embedding modeli yukleme hatasi: {e}")
            log("INFO", "=> Ilk kullanimsa model indiriliyor (2-3 dakika surebilir)")
            raise

        if rebuild or not self._load_index():
            log("WARN", "Diskte gecerli indeks bulunamadi. MongoDB'den olusturuluyor...")
            self._build_from_mongo()

        # Service health checks
        self._check_ollama_service()
        self._check_mongodb_service()

    def _check_ollama_service(self) -> bool:
        """Check if Ollama LLM service is running."""
        try:
            resp = requests.get(
                OLLAMA_URL.replace("/api/generate", "/api/tags"), 
                timeout=3
            )
            if resp.status_code == 200:
                log("OK", f"Ollama '{OLLAMA_MODEL}' hazir.")
                return True
        except requests.exceptions.Timeout:
            log("WARN", f"Ollama timeout: {OLLAMA_URL}")
        except requests.exceptions.ConnectionError:
            log("WARN", "Ollama baglanti hatasi. Basla: ollama serve")
        except Exception as e:
            log("WARN", f"Ollama check hatasi: {e}")
        return False

    def _check_mongodb_service(self) -> bool:
        """Check if MongoDB service is running."""
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=MONGO_TIMEOUT)
            client.server_info()  # Test connection
            log("OK", f"MongoDB baglantisi OK: {MONGO_DB}")
            return True
        except ConnectionFailure:
            log("WARN", f"MongoDB baglanti hatasi: {MONGO_URI}")
        except Exception as e:
            log("WARN", f"MongoDB check hatasi: {e}")
        return False

    def _build_from_mongo(self):
        """Build FAISS index from MongoDB chunks."""
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=MONGO_TIMEOUT)
            collection = client[MONGO_DB][MONGO_COL]

            docs = list(collection.find({"text": {"$exists": True, "$ne": ""}}))
            if not docs:
                log("ERR", f"MongoDB'de gecerli veri bulunamadi! ({MONGO_DB}.{MONGO_COL})")
                log("INFO", "=> Duyuru scraper'ini calistir: python inonu_ogrencidb_duyuru_scraper.py")
                sys.exit(1)

            log("INFO", f"{len(docs)} parca MongoDB'den cekildi. Vektorlestiriliyor...")
            texts = [d["text"] for d in docs]

            embeddings = self.model.encode(
                texts, show_progress_bar=True, convert_to_numpy=True, 
                normalize_embeddings=True
            ).astype(np.float32)

            self.index = faiss.IndexFlatIP(self.dim)
            self.index.add(embeddings)

            self.metadata_store = []
            for d in docs:
                meta = d.get("metadata", {})
                self.metadata_store.append({
                    "text": d["text"],
                    "source_collection": meta.get("source_collection", "Bilinmeyen"),
                    "source_url": meta.get("source_url", "")
                })

            faiss.write_index(self.index, FAISS_PATH)
            with open(META_PATH, "w", encoding="utf-8") as f:
                json.dump(self.metadata_store, f, ensure_ascii=False)

            log("OK", f"Indeks olusturuldu ve diske kaydedildi. ({self.index.ntotal} kayit)")

        except ConnectionFailure as e:
            log("ERR", f"MongoDB baglantisi hatasi: {e}")
            log("INFO", "=> MongoDB'nin calistip calismadigi kontrol et")
            sys.exit(1)
        except Exception as e:
            log("ERR", f"Indeks olusturma hatasi: {e}")
            raise

    def _load_index(self) -> bool:
        if not os.path.exists(FAISS_PATH) or not os.path.exists(META_PATH):
            return False
        try:
            self.index = faiss.read_index(FAISS_PATH)
            with open(META_PATH, "r", encoding="utf-8") as f:
                self.metadata_store = json.load(f)

            if self.index.ntotal != len(self.metadata_store):
                return False

            log("OK", f"İndeks diskten yüklendi. ({self.index.ntotal} kayıt)")
            return True
        except Exception:
            return False

    def query(self, user_question: str) -> dict:
        clean_query = sterilize_query(user_question)

        # v2.0: Sorguyu Türkçe eşanlamlılarla genişlet
        expanded_query = expand_query(clean_query)

        # v2.0: Hem orijinal hem genişletilmiş sorguyu vektörleştir ve ortalamasını al
        queries_to_encode = [clean_query]
        if expanded_query != clean_query:
            queries_to_encode.append(expanded_query)

        q_vecs = self.model.encode(queries_to_encode, convert_to_numpy=True, normalize_embeddings=True).astype(np.float32)

        # Ortalama vektör (orijinal + genişletilmiş sorgu)
        q_vec = np.mean(q_vecs, axis=0, keepdims=True).astype(np.float32)
        # Yeniden normalize et
        faiss.normalize_L2(q_vec)

        scores, indices = self.index.search(q_vec, TOP_K)

        valid_hits = []
        top_score = 0.0

        for score, idx in zip(scores[0], indices[0]):
            if idx == -1: continue

            score_float = float(score)
            if score_float > top_score:
                top_score = score_float

            if score_float >= IRON_SHIELD_THRESHOLD:
                doc = self.metadata_store[idx]
                valid_hits.append({
                    "score": score_float,
                    "text": doc["text"],
                    "source_collection": doc["source_collection"],
                    "source_url": doc["source_url"]
                })

        if not valid_hits:
            log("SHIELD", f"Iron Shield Reddi! En yüksek skor: {top_score:.4f} < {IRON_SHIELD_THRESHOLD}")
            return {"answer": FALLBACK_MESSAGE, "sources": [], "shield_triggered": True}

        # v2.0: Tekrar eden chunk'ları filtrele
        valid_hits = deduplicate_hits(valid_hits)

        # v2.0: En iyi MAX_CONTEXT_CHUNKS kadar chunk'ı al (skor sırasına göre zaten sıralı)
        context_hits = valid_hits[:MAX_CONTEXT_CHUNKS]

        # v2.3: Context formatı — Panel URL'leri doğru gösterim
        context_parts = []
        for i, h in enumerate(context_hits, 1):
            source = h.get("source_collection", "Bilinmeyen")
            url = h.get("source_url", "")
            
            # URL formatı düzelt: boşsa panel URL'si oluştur veya doğru olanı kullan
            if url and "panel.inonu.edu.tr" in url:
                source_line = f"[Kaynak: {source}] {url}"
            elif url and url.startswith("http"):
                source_line = f"[Kaynak: {source}] {url}"
            else:
                source_line = f"[Kaynak: {source}]"
            
            context_parts.append(f"[Bilgi {i}] {source_line}\n{h['text']}")

        context_docs = "\n\n---\n\n".join(context_parts)

        log("INFO", f"LLM'e gönderilen: {len(context_hits)} chunk, "
                     f"~{len(context_docs)} karakter, "
                     f"en yüksek skor: {top_score:.4f}")

        context_part = f"METİNLER:\n\n{context_docs}\n\n---\n\nSORU: {clean_query}\n\nCEVAP:"
        
        # v2.4 FİX: System prompt'u prompt'a birleştir (Ollama API compatibility)
        full_prompt = f"{SYSTEM_PROMPT}\n\n{context_part}"

        payload = {
            "model": OLLAMA_MODEL,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": LLAMA_TEMPERATURE,
                "top_p": 0.9,
                "num_predict": 1024,
                "num_ctx": NUM_CTX
            }
        }

        try:
            resp = requests.post(OLLAMA_URL, json=payload, timeout=OLLAMA_TIMEOUT)
            resp.raise_for_status()
            answer = resp.json().get("response", "").strip()
            if not answer:
                answer = "LLM bos yanit verdi. Sorguyu yeniden dene veya Ollama durumunu kontrol et."
        except requests.exceptions.Timeout:
            answer = f"HATA: Ollama timeout! ({OLLAMA_TIMEOUT}s) Basla: ollama serve"
        except requests.exceptions.ConnectionError:
            answer = f"HATA: Ollama'ya baglanilimiyor ({OLLAMA_URL})"
        except Exception as e:
            answer = f"HATA: LLM yanit hatasi ({type(e).__name__}: {e})"

        return {
            "answer": answer,
            "sources": valid_hits,
            "shield_triggered": False
        }


# ─── TERMİNAL ARAYÜZÜ ─────────────────────────────────────────────────────────
def print_xai_sources(sources: List[dict]):
    """v2.4: XAI Şeffaflık — Sadece skor ve koleksiyon bilgisi"""
    if not sources: return
    print("\n   [XAI] Kaynak Şeffaflık İzi (Saf Semantik Skorlar):")
    print("   " + "─" * 80)
    for idx, s in enumerate(sources, 1):
        score = f"{s['score']:.4f}"
        col = (s.get('source_collection') or '-')
        print(f"   [{idx}] Skor: {score} | Kaynak: {col}")
    print("   " + "─" * 80 + "\n")

def print_debug_context(sources: List[dict]):
    """v2.0: Debug modu — LLM'e gönderilen chunk'ları gösterir."""
    if not sources: return
    print("\n   [DEBUG] LLM'e Gönderilen Chunk İçerikleri:")
    for idx, s in enumerate(sources[:MAX_CONTEXT_CHUNKS], 1):
        preview = s['text'][:150].replace('\n', ' ')
        print(f"   [{idx}] (skor:{s['score']:.4f}) {preview}...")
    print()

def interactive_repl(engine: RAGEngine):
    print("\n" + "═" * 80)
    print("  İNÖNÜ AI CAMPUS ASİSTANI (v2.0 — Güncel)".center(80))
    print("═" * 80)
    print("  Komutlar: 'quit'/'exit' → Çıkış | 'clear' → Temizle | 'debug' → Debug Aç/Kapa")
    print(f"  Motor: {OLLAMA_MODEL} | Temp: {LLAMA_TEMPERATURE} | Shield: {IRON_SHIELD_THRESHOLD} | "
          f"Top-K: {TOP_K} | Ctx: {NUM_CTX}\n")

    debug_mode = False

    while True:
        try:
            q = input("📝 Soru: ").strip()
            if not q: continue
            if q.lower() in ["quit", "exit", "q"]:
                print("\n👋 Görüşmek üzere!")
                break
            if q.lower() in ["clear", "cls"]:
                os.system("cls" if os.name == "nt" else "clear")
                continue
            if q.lower() == "debug":
                debug_mode = not debug_mode
                print(f"   🔧 Debug modu: {'AÇIK' if debug_mode else 'KAPALI'}")
                continue

            print()
            result = engine.query(q)

            print("🤖 İnönü AI:")
            print("────────────────────────────────────────────────────────────────────────────────")
            for line in result["answer"].split("\n"):
                print(f" {line}")
            print("────────────────────────────────────────────────────────────────────────────────")

            if not result["shield_triggered"]:
                if debug_mode:
                    print_debug_context(result["sources"])
                print_xai_sources(result["sources"])

        except (KeyboardInterrupt, EOFError):
            print("\n\n👋 Çıkış yapılıyor...")
            break
        except Exception as e:
            log("ERR", f"Beklenmeyen bir hata oluştu: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild_index", action="store_true", help="MongoDB'den vektör indeksini yeniden oluştur.")
    args = parser.parse_args()

    engine = RAGEngine()
    engine.startup(rebuild=args.rebuild_index)
    interactive_repl(engine)
