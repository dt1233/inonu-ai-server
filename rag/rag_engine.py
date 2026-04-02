#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    İNÖNÜ AI — RAG ENGINE v3.2 (Stateful)                     ║
║                    Senior AI Chief Architect Edition                         ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ v3.2 Güncellemeleri (Hafıza ve Bağlam Desteği):                              ║
║ 1. Sohbet Geçmişi (Chat History) eklendi.                                    ║
║ 2. Query Rewriting: Eksik sorular geçmişe bakılarak tam soruya çevrildi.     ║
║ 3. Terminal REPL "clear" komutuna hafıza sıfırlama özelliği eklendi.         ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

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

IRON_SHIELD_THRESHOLD = 0.45
TOP_K_FETCH  = 15
TOP_K_RETURN = 8
LLAMA_TEMPERATURE = 0.0

FALLBACK_MESSAGE = (
    "⛔ Bu konuda veritabanında yeterli bilgi bulunamadı.\n"
    "   Lütfen öğrenci işleri ile iletişime geçin: 0 422 377 30 41"
)

SYSTEM_PROMPT = """Sen İnönü Üniversitesi'nin resmi yapay zeka kampüs asistanı "İnönü AI"sın.

KESİN VE İHLAL EDİLEMEZ KURALLAR:
1. SADECE sana verilen BELGELER kısmındaki bilgileri kullan.
2. Belgelerde OLMAYAN hiçbir bilgiyi ASLA uydurma, tahmin etme veya dış genel bilginden ekleme.
3. Eğer belgeler soruyu karşılamıyorsa, açıkça "Bu konuda bilgiye sahip değilim." de.
4. Yanıtını Türkçe, akademik ve profesyonel bir tonda doğrudan ver.
5. "Belge 1'de...", "Belge 2'ye göre..." gibi iç kaynak referansları KULLANMA. Doğrudan bilgiyi ver.
6. Tablo ve liste içerikleri (sınav tarihleri, kontenjanlar vb.) için verileri eksiksiz aktar."""


# ─────────────────────────────────────────────────────────────────────────────
# TÜRKÇE KARAKTER NORMALİZASYONU
# ─────────────────────────────────────────────────────────────────────────────
_TR_CHAR_MAP = str.maketrans("ÇçĞğİıÖöŞşÜü", "CcGgIiOoSsUu")

def normalize_text(text: str) -> str:
    return text.translate(_TR_CHAR_MAP).lower().strip()

def log(tag: str, msg: str):
    ts = time.strftime("%H:%M:%S")
    icons = {"OK": "[+]", "ERR": "[!]", "INFO": "[i]", "WARN": "[*]", "SHIELD": "[🛡]"}
    icon = icons.get(tag, "[?]")
    print(f"  {ts}  {icon}  {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# KURAL 1: DATALAYER
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Document:
    text: str
    source_url: str
    source_collection: str
    mongo_id: str

class DataLayer:
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
                if not text: continue
                meta = d.get("metadata", {})
                docs.append(Document(
                    text=text,
                    source_url=meta.get("source_url", ""),
                    source_collection=meta.get("source_collection", ""),
                    mongo_id=str(d.get("_id", ""))
                ))

            client.close()
            log("OK", f"{len(docs)} belge başarıyla çekildi.")
            return docs
        except ConnectionFailure as e:
            log("ERR", f"MongoDB Bağlantı Hatası: {e}")
            return []


# ─────────────────────────────────────────────────────────────────────────────
# KATMAN 2: EMBEDDING LAYER
# ─────────────────────────────────────────────────────────────────────────────
class EmbeddingLayer:
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
# KURAL 2: INDEX LAYER
# ─────────────────────────────────────────────────────────────────────────────
class IndexLayer:
    def __init__(self):
        self.index = None
        self.metadata_store: List[Document] = []

    def build_index(self, vectors: np.ndarray, documents: List[Document]):
        import faiss
        if len(vectors) != len(documents): raise ValueError("Vektör eşleşmiyor!")
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
        if not os.path.exists(FAISS_PATH) or not os.path.exists(META_PATH): return False
        try:
            self.index = faiss.read_index(FAISS_PATH)
            with open(META_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.metadata_store = [Document(**d) for d in data]
            if self.index.ntotal != len(self.metadata_store): return False
            log("OK", f"İndeks diskten yüklendi. Kayıt Sayısı: {self.index.ntotal}")
            return True
        except Exception as e:
            log("ERR", f"İndeks yüklenirken hata: {e}")
            return False

    def search(self, query_vec: np.ndarray, top_k: int = TOP_K_FETCH) -> List[dict]:
        scores, indices = self.index.search(query_vec, top_k)
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1: continue
            doc = self.metadata_store[idx]
            results.append({
                "score": float(score),
                "text": doc.text,
                "source_collection": doc.source_collection,
                "source_url": doc.source_url
            })
        return results


# ─────────────────────────────────────────────────────────────────────────────
# LEXICAL ARAMA
# ─────────────────────────────────────────────────────────────────────────────
def _lexical_search(query: str, documents: List[Document], top_k: int = 5) -> List[dict]:
    import string
    stop_words = {"bir", "ve", "ile", "de", "da", "bu", "su", "o", "nedir", "nasil", "kim", "ne", "icin", "gore", "ver", "hakkinda", "hangi", "olan", "icinde", "uzerinde", "sonra", "once", "hem", "ise"}
    
    norm_query = normalize_text(query)
    words = [w.strip(string.punctuation) for w in norm_query.split()]
    keywords = [w for w in words if len(w) > 2 and w not in stop_words]

    if not keywords: return []

    scored_docs = []
    for doc in documents:
        text_norm = normalize_text(doc.text)
        unique_matches = 0
        freq_score = 0
        for kw in keywords:
            count = text_norm.count(kw)
            if count > 0:
                unique_matches += 1
                freq_score += count
        if unique_matches > 0:
            scored_docs.append({
                "score": float((unique_matches * 100) + freq_score),
                "text": doc.text,
                "source_collection": doc.source_collection,
                "source_url": doc.source_url,
                "type": "Lexical Match"
            })
    scored_docs.sort(key=lambda x: x["score"], reverse=True)
    return scored_docs[:top_k]


# ─────────────────────────────────────────────────────────────────────────────
# RAG ENGINE CORE (STATEFUL YAPI)
# ─────────────────────────────────────────────────────────────────────────────
class RAGEngine:
    def __init__(self):
        self.data_layer = DataLayer()
        self.embedding_layer = EmbeddingLayer()
        self.index_layer = IndexLayer()
        self.chat_history = []  # YENİ: Sohbet geçmişi hafızası

    def rebuild(self):
        docs = self.data_layer.fetch_all_documents()
        if not docs: sys.exit(1)
        self.embedding_layer.load()
        vectors = self.embedding_layer.embed_corpus([d.text for d in docs])
        self.index_layer.build_index(vectors, docs)
        self.index_layer.save_index()

    def startup(self):
        if not self.index_layer.load_index(): self.rebuild()
        else: self.embedding_layer.load()
        try:
            requests.get(OLLAMA_URL.replace("/api/generate", "/api/tags"), timeout=3)
            log("OK", f"Ollama '{OLLAMA_MODEL}' hazır.")
        except: log("WARN", "Ollama servisine şu anda erişilemiyor.")

    def rewrite_query(self, current_question: str) -> str:
        """Eksik soruyu sohbet geçmişine bakarak vektör araması için tam soruya çevirir."""
        if not self.chat_history:
            return current_question

        recent_history = self.chat_history[-2:]
        history_text = "\n".join([f"Soru: {h['user']}\nCevap: {h['ai'][:100]}..." for h in recent_history])
        
        rewrite_prompt = (
            f"Aşağıdaki sohbet geçmişine bakarak, kullanıcının son sorusunu kendi başına "
            f"anlaşılır, tam bir arama cümlesine dönüştür. Asla soruya cevap verme, "
            f"sadece soruyu yeniden yaz.\n\n"
            f"Geçmiş:\n{history_text}\n\n"
            f"Son Soru: {current_question}\n\n"
            f"Yeniden Yazılmış Soru:"
        )

        payload = {
            "model": OLLAMA_MODEL,
            "prompt": rewrite_prompt,
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": 50}
        }

        try:
            resp = requests.post(OLLAMA_URL, json=payload, timeout=10)
            rewritten = resp.json().get("response", "").strip()
            return rewritten if rewritten else current_question
        except Exception:
            return current_question

    def query(self, user_question: str) -> dict:
        # 1. Query Rewriting: Soru bağlamı kopuksa tam soruya çevir
        search_query = self.rewrite_query(user_question)
        log("INFO", f"Arama yapılacak asıl sorgu: '{search_query}'")

        normalized_question = normalize_text(search_query)
        q_vec = self.embedding_layer.embed_query(search_query)
        semantic_hits = self.index_layer.search(q_vec, TOP_K_FETCH)

        if not semantic_hits:
            return {"answer": FALLBACK_MESSAGE, "sources": [], "shield_triggered": True, "top_score": 0}

        top_score = semantic_hits[0]["score"]
        valid_hits = []

        if top_score < IRON_SHIELD_THRESHOLD:
            log("WARN", f"Semantik Iron Shield Reddi (Skor: {top_score:.4f} < {IRON_SHIELD_THRESHOLD}).")
            lexical_hits = _lexical_search(normalized_question, self.index_layer.metadata_store, 7)
            if not lexical_hits:
                return {"answer": FALLBACK_MESSAGE, "sources": [], "shield_triggered": True, "top_score": top_score}
            else:
                log("OK", f"Lexical Shield tetiklendi!")
                valid_hits = lexical_hits
        else:
            valid_hits = [h for h in semantic_hits if h["score"] >= IRON_SHIELD_THRESHOLD][:TOP_K_RETURN]
            lexical_hits = _lexical_search(normalized_question, self.index_layer.metadata_store, 5)
            unique_texts = {h["text"] for h in valid_hits}
            for lh in lexical_hits:
                if lh["text"] not in unique_texts:
                    valid_hits.append(lh)
                    unique_texts.add(lh["text"])

        # 2. Üretim (Generation) Aşaması ve Bağlamın Prompt'a Eklenmesi
        context_docs = ""
        for i, h in enumerate(valid_hits, 1):
            context_docs += f"\n[Belge {i}]\n{h['text']}\n"

        history_context = ""
        if self.chat_history:
            history_context = "SOHBET GEÇMİŞİ:\n"
            for h in self.chat_history[-2:]:
                history_context += f"Kullanıcı: {h['user']}\nSen: {h['ai']}\n"

        prompt = (
            f"{history_context}\n"
            f"BELGELER:{context_docs}\n"
            f"GÜNCEL SORU: {user_question}\n"
            f"Yukarıdaki BELGELER'deki bilgilere ve gerekirse SOHBET GEÇMİŞİ'ne dayanarak güncel soruyu yanıtla. "
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

        answer = re.sub(r'Belge\s+\d+[\'\'de\s](\'de|\'da|\'ye|\'ya|\'a|\'e|\'nde|\'nda|\'e\s+göre|\'a\s+göre)?[,\s]', '', answer)

        # 3. Güncel etkileşimi hafızaya kaydet
        self.chat_history.append({
            "user": user_question,
            "ai": answer
        })

        return {
            "answer": answer,
            "sources": valid_hits,
            "shield_triggered": False,
            "top_score": top_score
        }


# ─────────────────────────────────────────────────────────────────────────────
# XAI KARAR İZİ & TERMINAL REPL
# ─────────────────────────────────────────────────────────────────────────────
def print_xai_sources(sources: List[dict]):
    if not sources: return
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
    print("  İNÖNÜ AI CAMPUS ASİSTANI (v3.2 Stateful Production)".center(80))
    print("═" * 80)
    print("  Komutlar: 'quit', 'exit' -> Çıkış | 'clear' -> Terminali ve Hafızayı Temizle")
    print(f"  Motor: {OLLAMA_MODEL} | Eşik: {IRON_SHIELD_THRESHOLD}\n")

    while True:
        try:
            q = input("📝 Soru: ").strip()
            if not q: continue
            if q.lower() in ["quit", "exit", "q"]:
                print("\n👋 Görüşmek üzere!")
                break
            if q.lower() == "clear":
                os.system("cls" if os.name == "nt" else "clear")
                engine.chat_history.clear() # HAFIZAYI SIFIRLA
                print("✨ Sohbet geçmişi ve ekran temizlendi!\n")
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
    parser = argparse.ArgumentParser(description="İnönü AI RAG Motoru v3.2")
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
