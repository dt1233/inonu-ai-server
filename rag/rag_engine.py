#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    İNÖNÜ AI — RAG ENGINE v3.1 (Production)                   ║
║                    Senior AI Chief Architect Edition                         ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ v3.1 Düzeltmeleri:                                                           ║
║ 1. Sorgu Normalizasyonu: Büyük/küçük harf, Türkçe karakter duyarsız arama    ║
║ 2. Genişletilmiş Bağlam Penceresi: num_ctx 4096 → 8192                       ║
║ 3. Lexical Arama İyileştirmesi: Türkçe karakter normalize desteği            ║
║ 4. Iron Shield Eşiği düzeltildi: 0.48 → 0.45 (daha geniş kapsam)             ║
║ 5. Top-K artırıldı: 10 → 15 (tablo/liste içerikler için)                     ║
║ 6. Sistem Promptu güncellendi: İç referans (Belge N) sızıntısı engellendi    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict

try:
    import numpy as np
    import requests
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure
except ImportError as e:
    sys.exit(f"\n[FATAL] Eksik kütüphane: {e}\nLütfen çalıştırın: pip install pymongo sentence-transformers faiss-cpu numpy requests\n")

# ─────────────────────────────────────────────────────────────────────────────
# SABİTLER VE ORTAM DEĞİŞKENLERİ
# ─────────────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent

MONGO_URI = os.getenv("INONU_MONGO_URI", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("INONU_MONGO_DB", "inonu_ai")
MONGO_COL = os.getenv("INONU_MONGO_COL", "chunks")

EMBED_MODEL_NAME = "emrecan/bert-base-turkish-cased-mean-nli-stsb-tr"
EMBED_DIM        = 768

FAISS_PATH = str(SCRIPT_DIR / "faiss_index.bin")
META_PATH  = str(SCRIPT_DIR / "metadata_store.json")

OLLAMA_URL   = os.getenv("INONU_OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("INONU_OLLAMA_MODEL", "llama3.1")

# v3.1: Eşik düşürüldü (0.48 → 0.45), daha geniş kapsam
IRON_SHIELD_THRESHOLD = 0.45
# v3.1: Top-K artırıldı (10 → 15), tablo/liste içerikler için daha fazla aday
TOP_K_FETCH  = 15
TOP_K_RETURN = 8
LLAMA_TEMPERATURE = 0.0

FALLBACK_MESSAGE = (
    "⛔ Bu konuda veritabanında yeterli bilgi bulunamadı.\n"
    "   Lütfen öğrenci işleri ile iletişime geçin: 0 422 377 30 41"
)

# v3.1: "Belge N'de..." gibi iç referans sızıntısı engellendi
SYSTEM_PROMPT = """Sen İnönü Üniversitesi'nin resmi yapay zeka kampüs asistanı "İnönü AI"sın.

KESİN VE İHLAL EDİLEMEZ KURALLAR:
1. SADECE sana verilen BELGELER kısmındaki bilgileri kullan.
2. Belgelerde OLMAYAN hiçbir bilgiyi ASLA uydurma, tahmin etme veya dış genel bilginden ekleme.
3. Eğer belgeler soruyu karşılamıyorsa, açıkça "Bu konuda bilgiye sahip değilim." de.
4. Yanıtını Türkçe, akademik ve profesyonel bir tonda doğrudan ver.
5. "Belge 1'de...", "Belge 2'ye göre..." gibi iç kaynak referansları KULLANMA. Doğrudan bilgiyi ver.
6. Tablo ve liste içerikleri (sınav tarihleri, kontenjanlar vb.) için verileri eksiksiz aktar."""


# ─────────────────────────────────────────────────────────────────────────────
# v3.1 YENİ: TÜRKÇE KARAKTER NORMALİZASYONU
# ─────────────────────────────────────────────────────────────────────────────

# Türkçe → ASCII dönüşüm tablosu (büyük/küçük harf farkı ve karakter sorunu için)
_TR_CHAR_MAP = str.maketrans(
    "ÇçĞğİıÖöŞşÜü",
    "CcGgIiOoSsUu"
)

def normalize_text(text: str) -> str:
    """
    Türkçe karakterleri ASCII'ye çevirir ve küçük harfe dönüştürür.
    Böylece 'ÖĞRENCİ' ile 'öğrenci' aynı token olarak eşleşir.
    """
    return text.translate(_TR_CHAR_MAP).lower().strip()


# ─────────────────────────────────────────────────────────────────────────────
# YARDIMCI / LOGLAMA
# ─────────────────────────────────────────────────────────────────────────────

def log(tag: str, msg: str):
    ts = time.strftime("%H:%M:%S")
    icons = {"OK": "[+]", "ERR": "[!]", "INFO": "[i]", "WARN": "[*]", "SHIELD": "[🛡]"}
    icon = icons.get(tag, "[?]")
    print(f"  {ts}  {icon}  {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# KURAL 1: SIFIR CHUNKING - DATALAYER
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Document:
    text: str
    source_url: str
    source_collection: str
    mongo_id: str

class DataLayer:
    """MongoDB'deki hazır (chunklanmış) veriyi PyMongo ile çeker."""
    def __init__(self, uri: str = MONGO_URI, db: str = MONGO_DB, col: str = MONGO_COL):
        self.uri = uri
        self.db = db
        self.col = col

    def fetch_all_documents(self) -> List[Document]:
        try:
            client = MongoClient(self.uri, serverSelectionTimeoutMS=5000)
            client.admin.command('ping')
            log("INFO", f"MongoDB bağlandı: {self.db}/{self.col}")

            db = client[self.db]
            collection = db[self.col]
            docs = []

            for d in collection.find({}):
                text = str(d.get("text", "")).strip()
                if not text:
                    continue
                meta = d.get("metadata", {})
                docs.append(Document(
                    text=text,
                    source_url=meta.get("source_url", ""),
                    source_collection=meta.get("source_collection", ""),
                    mongo_id=str(d.get("_id", ""))
                ))

            client.close()
            log("OK", f"{len(docs)} belge başarıyla MongoDB'den çekildi.")
            return docs

        except ConnectionFailure as e:
            log("ERR", f"MongoDB Bağlantı Hatası: {e}")
            return []


# ─────────────────────────────────────────────────────────────────────────────
# KATMAN 2: EMBEDDING LAYER
# ─────────────────────────────────────────────────────────────────────────────

class EmbeddingLayer:
    """Türkçe BERT tabanlı L2 Normalize Edilmiş Vektör Üreticisi"""
    def __init__(self):
        self.model = None

    def load(self):
        from sentence_transformers import SentenceTransformer
        log("INFO", f"Embedding modeli yükleniyor: {EMBED_MODEL_NAME}")
        start = time.time()
        self.model = SentenceTransformer(EMBED_MODEL_NAME)
        log("OK", f"Model yüklendi ({time.time()-start:.1f}s) | Cihaz: {self.model.device}")

    def embed_corpus(self, texts: List[str]) -> np.ndarray:
        log("INFO", f"{len(texts)} metin vektörleştiriliyor...")
        vecs = self.model.encode(texts, show_progress_bar=True, convert_to_numpy=True, normalize_embeddings=True)
        return vecs.astype(np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        vec = self.model.encode([query], convert_to_numpy=True, normalize_embeddings=True)
        return vec.astype(np.float32)


# ─────────────────────────────────────────────────────────────────────────────
# KURAL 2: VEKTÖR/METADATA EŞLEŞMESİ - INDEX LAYER
# ─────────────────────────────────────────────────────────────────────────────

class IndexLayer:
    """FAISS (IndexFlatIP) üzerinden semantik arama."""
    def __init__(self):
        self.index = None
        self.metadata_store: List[Document] = []

    def build_index(self, vectors: np.ndarray, documents: List[Document]):
        import faiss
        if len(vectors) != len(documents):
            raise ValueError("Vektör ve metin sayısı eşleşmiyor!")

        log("INFO", f"FAISS IndexFlatIP oluşturuluyor ({EMBED_DIM} boyutlu)...")
        self.index = faiss.IndexFlatIP(EMBED_DIM)
        self.index.add(vectors)
        self.metadata_store = documents

        log("OK", f"İndeks oluşturuldu: {self.index.ntotal} kayıt.")

    def save_index(self):
        import faiss
        faiss.write_index(self.index, FAISS_PATH)
        docs_dicts = [d.__dict__ for d in self.metadata_store]
        with open(META_PATH, "w", encoding="utf-8") as f:
            json.dump(docs_dicts, f, ensure_ascii=False)
        log("OK", f"İndeks diskte kayıtlı ({FAISS_PATH})")

    def load_index(self) -> bool:
        import faiss
        if not os.path.exists(FAISS_PATH) or not os.path.exists(META_PATH):
            return False

        try:
            self.index = faiss.read_index(FAISS_PATH)
            with open(META_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.metadata_store = [Document(**d) for d in data]

            if self.index.ntotal != len(self.metadata_store):
                log("WARN", "FAISS ve Meta veri senkronizasyonu bozuk. Rebuild gerekiyor.")
                return False

            log("OK", f"İndeks diskten yüklendi. Kayıt Sayısı: {self.index.ntotal}")
            return True
        except Exception as e:
            log("ERR", f"İndeks yüklenirken hata oluştu: {e}")
            return False

    def search(self, query_vec: np.ndarray, top_k: int = TOP_K_FETCH) -> List[dict]:
        scores, indices = self.index.search(query_vec, top_k)
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            doc = self.metadata_store[idx]
            results.append({
                "score": float(score),
                "text": doc.text,
                "source_collection": doc.source_collection,
                "source_url": doc.source_url
            })
        return results


# ─────────────────────────────────────────────────────────────────────────────
# v3.1 GÜNCELLENDİ: LEXICAL ARAMA — Türkçe karakter normalize desteği
# ─────────────────────────────────────────────────────────────────────────────

def _lexical_search(query: str, documents: List[Document], top_k: int = 5) -> List[dict]:
    """
    Türkçe karakter normalize edilmiş Lexical (anahtar kelime) arama.
    Büyük/küçük harf ve Türkçe karakter farkını ortadan kaldırır.
    Örn: 'ÖĞRENCİ DAİRE BAŞKANLIĞI' ile 'öğrenci daire başkanlığı' aynı sonuçları verir.
    """
    import string
    stop_words = {
        "bir", "ve", "ile", "de", "da", "bu", "su", "o", "nedir", "nasil",
        "kim", "ne", "icin", "gore", "ver", "hakkinda", "hangi", "olan",
        "olan", "icinde", "uzerinde", "sonra", "once", "hem", "ise"
    }

    # v3.1: Sorguyu normalize et (Türkçe → ASCII, küçük harf)
    norm_query = normalize_text(query)
    words = [w.strip(string.punctuation) for w in norm_query.split()]
    keywords = [w for w in words if len(w) > 2 and w not in stop_words]

    if not keywords:
        return []

    scored_docs = []
    for doc in documents:
        # v3.1: Belge metnini de normalize et
        text_norm = normalize_text(doc.text)
        unique_matches = 0
        freq_score = 0

        for kw in keywords:
            count = text_norm.count(kw)
            if count > 0:
                unique_matches += 1
                freq_score += count

        if unique_matches > 0:
            final_score = (unique_matches * 100) + freq_score
            scored_docs.append({
                "score": float(final_score),
                "text": doc.text,
                "source_collection": doc.source_collection,
                "source_url": doc.source_url,
                "type": "Lexical Match"
            })

    scored_docs.sort(key=lambda x: x["score"], reverse=True)
    return scored_docs[:top_k]


# ─────────────────────────────────────────────────────────────────────────────
# KURAL 3 & 4: HYBRID IRON SHIELD VE DETERMINISTIK OLLAMA - RAG ENGINE CORE
# ─────────────────────────────────────────────────────────────────────────────

class RAGEngine:
    """Ana RAG Orkestratörü (Hybrid Iron Shield Threshold ve Ollama Generation)"""
    def __init__(self):
        self.data_layer = DataLayer()
        self.embedding_layer = EmbeddingLayer()
        self.index_layer = IndexLayer()

    def rebuild(self):
        docs = self.data_layer.fetch_all_documents()
        if not docs:
            log("ERR", "Veritabanından hiçbir döküman çekilemedi. İşlem iptal.")
            sys.exit(1)

        self.embedding_layer.load()
        vectors = self.embedding_layer.embed_corpus([d.text for d in docs])

        self.index_layer.build_index(vectors, docs)
        self.index_layer.save_index()

    def startup(self):
        if not self.index_layer.load_index():
            log("WARN", "Diskte geçerli indeks bulunamadı, yeniden inşa ediliyor...")
            self.rebuild()
        else:
            self.embedding_layer.load()

        try:
            requests.get(OLLAMA_URL.replace("/api/generate", "/api/tags"), timeout=3)
            log("OK", f"Ollama '{OLLAMA_MODEL}' hazır, ping başarılı.")
        except Exception:
            log("WARN", "Ollama servisine şu anda erişilemiyor.")

        log("OK", "RAG Pipeline Hazır.")

    def query(self, user_question: str) -> dict:
        # v3.1: Sorguyu önce normalize et (Türkçe karakter + büyük/küçük harf)
        normalized_question = normalize_text(user_question)
        log("INFO", f"Normalize sorgu: '{normalized_question}'")

        # 1. FAISS (Dense) Semantik Arama — orijinal sorgu ile (model zaten bunu bekler)
        q_vec = self.embedding_layer.embed_query(user_question)
        # v3.1: TOP_K_FETCH artırıldı (10 → 15)
        semantic_hits = self.index_layer.search(q_vec, TOP_K_FETCH)

        if not semantic_hits:
            return {"answer": FALLBACK_MESSAGE, "sources": [], "shield_triggered": True, "top_score": 0}

        top_score = semantic_hits[0]["score"]
        valid_hits = []

        # 2. Hybrid Iron Shield Mantığı
        if top_score < IRON_SHIELD_THRESHOLD:
            log("WARN", f"Semantik Iron Shield Reddi (Skor: {top_score:.4f} < {IRON_SHIELD_THRESHOLD}). Lexical Shield devreye giriyor.")

            # v3.1: Normalize sorgu ile lexical arama
            lexical_hits = _lexical_search(normalized_question, self.index_layer.metadata_store, 7)

            if not lexical_hits:
                log("SHIELD", "Lexical Shield de reddetti. Sistem halüsinasyonu bloke etti.")
                return {"answer": FALLBACK_MESSAGE, "sources": [], "shield_triggered": True, "top_score": top_score}
            else:
                log("OK", f"Lexical Shield tetiklendi! Spesifik anahtar kelimeler ile döküman kurtarıldı.")
                valid_hits = lexical_hits
        else:
            valid_hits = [h for h in semantic_hits if h["score"] >= IRON_SHIELD_THRESHOLD][:TOP_K_RETURN]
            # FAISS başarılı olsa bile lexical'i destek olarak ekle
            # v3.1: Normalize sorgu ile
            lexical_hits = _lexical_search(normalized_question, self.index_layer.metadata_store, 5)

            unique_texts = {h["text"] for h in valid_hits}
            for lh in lexical_hits:
                if lh["text"] not in unique_texts:
                    valid_hits.append(lh)
                    unique_texts.add(lh["text"])

        # 3. Prompt Mühendisliği & LLM'e İletim
        context_docs = ""
        for i, h in enumerate(valid_hits, 1):
            context_docs += f"\n[Belge {i}]\n{h['text']}\n"

        prompt = (
            f"BELGELER:{context_docs}\n"
            f"SORU: {user_question}\n"
            f"Yukarıdaki BELGELER'deki bilgilere dayanarak soruyu yanıtla. "
            f"'Belge 1', 'Belge 2' gibi iç referans ifadeleri kullanma; doğrudan bilgiyi ver."
        )

        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "system": SYSTEM_PROMPT,
            "stream": False,
            "options": {
                "temperature": LLAMA_TEMPERATURE,
                "top_p": 0.9,
                "num_predict": 1024,
                # v3.1: Bağlam penceresi genişletildi (4096 → 8192)
                # Tablo/liste içerikleri artık pencereye sığıyor
                "num_ctx": 8192
            }
        }

        start = time.time()
        try:
            resp = requests.post(OLLAMA_URL, json=payload, timeout=180)
            resp.raise_for_status()
            answer = resp.json().get("response", "").strip()
            log("INFO", f"Ollama LLM yanıtı geldi ({time.time()-start:.1f}s)")
        except Exception as e:
            answer = f"Hata: Yapay zeka motoru yanıt veremedi ({e})"

        import re
        answer = re.sub(r'Belge\s+\d+[\'\'de\s](\'de|\'da|\'ye|\'ya|\'a|\'e|\'nde|\'nda|\'e\s+göre|\'a\s+göre)?[,\s]', '', answer)

        return {
            "answer": answer,
            "sources": valid_hits,
            "shield_triggered": False,
            "top_score": top_score
        }


# ─────────────────────────────────────────────────────────────────────────────
# KURAL 5: XAI KARAR İZİ - TERMINAL REPL
# ─────────────────────────────────────────────────────────────────────────────

def print_xai_sources(sources: List[dict]):
    if not sources:
        return
    print("\n   [XAI] Kaynak Şeffaflık İzi:")
    print("   ┌───────┬────────────┬──────────────────────┬──────────────────────────────────────────┐")
    print("   │ No    │ Skor       │ Koleksiyon           │ Kaynak URL                               │")
    print("   ├───────┼────────────┼──────────────────────┼──────────────────────────────────────────┤")
    for idx, s in enumerate(sources, 1):
        score = f"{s['score']:.4f}"
        col = (s.get('source_collection') or '-')[:20]
        url = (s.get('source_url') or '-')
        if len(url) > 40: url = url[:37] + "..."
        print(f"   │ {idx:<5} │ {score:<10} │ {col:<20} │ {url:<40} │")
    print("   └───────┴────────────┴──────────────────────┴──────────────────────────────────────────┘\n")

def interactive_repl(engine: RAGEngine):
    print("\n" + "═" * 80)
    print("  İNÖNÜ AI CAMPUS ASİSTANI (v3.1 Production)".center(80))
    print("═" * 80)
    print("  Komutlar: 'quit', 'exit' -> Çıkış | 'clear' -> Temizle")
    print(f"  Motor: {OLLAMA_MODEL} (Temp={LLAMA_TEMPERATURE}) | Iron Shield Eşik: {IRON_SHIELD_THRESHOLD}\n")

    while True:
        try:
            q = input("📝 Soru: ").strip()
            if not q:
                continue
            if q.lower() in ["quit", "exit", "q"]:
                print("\n👋 Görüşmek üzere!")
                break
            if q.lower() == "clear":
                os.system("cls" if os.name == "nt" else "clear")
                continue

            print()
            result = engine.query(q)

            print("🤖 İnönü AI:")
            print("────────────────────────────────────────────────────────────────────────────────")
            for line in result["answer"].split("\n"):
                print(f" {line}")
            print("────────────────────────────────────────────────────────────────────────────────")

            if not result["shield_triggered"]:
                print_xai_sources(result["sources"])

        except (KeyboardInterrupt, EOFError):
            print("\n\n👋 Opsiyonel çıkış yakalandı. Görüşmek üzere!")
            break
        except Exception as e:
            log("ERR", f"Beklenmeyen bir hata oluştu: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# GİRİŞ NOKTASI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="İnönü AI RAG Motoru v3.1")
    parser.add_argument("--rebuild_index", action="store_true", help="MongoDB'den vektör indeksini yeniden oluştur.")
    args = parser.parse_args()

    engine = RAGEngine()

    if args.rebuild_index:
        engine.rebuild()
        print("\nİndeks başarıyla sil baştan kuruldu.")

    engine.startup()
    interactive_repl(engine)

if __name__ == "__main__":
    main()