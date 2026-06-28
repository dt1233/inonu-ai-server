import os
import re
import json
from datetime import datetime
from loguru import logger
from qdrant_client import QdrantClient
from engine.embedding import encode_batch
from tools.reranker import rerank

# ── Zaman duyarlı sorgu zenginleştirme ──────────────────────
_TIME_KEYWORDS = [
    'sınav', 'büt', 'final', 'vize', 'kayıt', 'mezun', 'takvim',
    'dönem', 'yaz okulu', 'staj', 'başvuru', 'tarih', 'ne zaman',
    'açılacak', 'kapanacak', 'son gün', 'süre', 'başla', 'bitir',
    'bütünleme', 'ders seçim', 'not giriş', 'mazeret',
]

# ─── Fakülte Tanıma Sistemi ───
# Her tuple: (sorgu_anahtarı, başlık_deseni)
# - sorgu_anahtarı: Kullanıcının sorusunda bu geçerse filtre aktifleşir
#   (Kısa ve belirsiz kelimeler tam yazılır: "eğitim" değil "eğitim fakültesi")
# - başlık_deseni: Belge başlığında (ilk 300 kar) sahiplik tespiti için kullanılır
#   ("eğitim öğretim yılı" gibi genel ifadeler yanlış eşleşme yapmasın diye tam isim)
_FACULTY_MAP = [
    ("mühendislik",        "mühendislik fakültesi"),
    ("hukuk",              "hukuk fakültesi"),
    ("tıp fakültesi",      "tıp fakültesi"),
    ("diş hekimliği",      "diş hekimliği"),
    ("eğitim fakültesi",   "eğitim fakültesi"),
    ("fen edebiyat",       "fen edebiyat"),
    ("edebiyat fakültesi", "edebiyat fakültesi"),
    ("iktisadi",           "iktisadi ve idari"),
    ("ilahiyat",           "ilahiyat fakültesi"),
    ("iletişim fakültesi", "iletişim fakültesi"),
    ("sağlık bilimleri",   "sağlık bilimleri"),
    ("spor bilimleri",     "spor bilimleri"),
    ("ziraat",             "ziraat fakültesi"),
    ("eczacılık",          "eczacılık fakültesi"),
    ("güzel sanatlar",     "güzel sanatlar"),
    ("hemşirelik",         "hemşirelik fakültesi"),
    ("meslek yüksekokulu", "meslek yüksekokulu"),
    ("konservatuvar",      "konservatuvar"),
]

def _extract_faculties(query: str) -> list[str]:
    """Sorgudaki fakülte/birim isimlerini yakalar."""
    q = query.lower()
    return [qk for qk, _ in _FACULTY_MAP if qk in q]

def _get_current_academic_year() -> str:
    """Güncel akademik yılı döndür (Eylül→Ağustos döngüsü)."""
    now = datetime.now()
    if now.month >= 9:
        return f"{now.year}-{now.year + 1}"
    return f"{now.year - 1}-{now.year}"

def _augment_query(query: str) -> str:
    """
    Zaman duyarlı sorulara otomatik olarak güncel akademik yılı ekler.
    Soruda zaten bir yıl varsa dokunmaz.
    """
    q = query.lower()
    # Soruda zaten 4 haneli yıl varsa dokunma
    if re.search(r'20\d{2}', query):
        return query
    # Zaman duyarlı anahtar kelime var mı?
    if any(kw in q for kw in _TIME_KEYWORDS):
        year = _get_current_academic_year()
        augmented = f"{query} {year} eğitim öğretim yılı güncel"
        logger.info(f"Sorgu zenginleştirildi: '{query}' → '{augmented}'")
        return augmented
    return query

class Retriever:
    def __init__(self):
        db_path = os.path.join(os.getcwd(), "qdrant_storage")
        if not os.path.exists(db_path):
            logger.warning("qdrant_storage bulunamadı! Lütfen önce indexer'ı çalıştırın.")
            
        self.client = QdrantClient(path=db_path)
        self.collection_name = os.getenv("QDRANT_COLLECTION", "inonu_docs")

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        logger.info(f"Soru aranıyor: {query}")
        
        # 1. Soruyu vektöre çevir (zaman duyarlı sorgular zenginleştirilir)
        search_query = _augment_query(query)
        embeddings = encode_batch([search_query])
        dense_vec = embeddings["dense"][0]
        
        from qdrant_client import models
        
        try:
            # 2. Qdrant'ta Hybrid (Dense + Sparse) arama yap
            sparse_dict = embeddings["sparse"][0]
            indices = [int(k) for k in sparse_dict.keys()]
            values = [float(v) for v in sparse_dict.values()]
            
            response = self.client.query_points(
                collection_name=self.collection_name,
                prefetch=[
                    models.Prefetch(
                        query=dense_vec,
                        using="dense",
                        limit=60,
                    ),
                    models.Prefetch(
                        query=models.SparseVector(
                            indices=indices,
                            values=values,
                        ),
                        using="sparse",
                        limit=60,
                    )
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=60,
                with_payload=True
            )
            
            # --- FAKÜLTE KESİN FİLTRESİ (HARD FILTER) ---
            req_facs = _extract_faculties(query)
            valid_points = []
            
            if req_facs:
                logger.info(f"🔎 Fakülte filtresi aktif: aranan = {req_facs}")
                logger.info(f"🔎 Qdrant'tan gelen toplam belge: {len(response.points)}")
                
                # Rakip fakültelerin BAŞLIK desenlerini belirle (tam isimler kullanılır)
                competing_headers = [hp for qk, hp in _FACULTY_MAP if qk not in req_facs]
                
                for i, p in enumerate(response.points):
                    text_lower = p.payload.get("text", "").lower()
                    source_url = p.payload.get("source_url", "?")
                    fakulte_meta = p.payload.get("fakulte", "")
                    
                    # 1) İstenen fakülte metinde veya metaveride geçmeli
                    has_requested = any(fac in text_lower or fac in fakulte_meta.lower() for fac in req_facs)
                    
                    if not has_requested:
                        logger.debug(f"  ❌ [{i}] ELENDİ (fakülte yok) → {source_url[:80]}")
                        continue
                    
                    # 2) Belgenin başlık/üst kısmında (ilk 300 kar) rakip fakülte geçiyorsa
                    #    bu belge o fakülteye aittir, reddet!
                    header = text_lower[:300]
                    competing_in_header = [h for h in competing_headers if h in header]
                    
                    if competing_in_header:
                        logger.debug(f"  ❌ [{i}] ELENDİ (başlıkta rakip: {competing_in_header}) → {source_url[:80]}")
                        continue
                    
                    valid_points.append(p)
                    logger.debug(f"  ✅ [{i}] GEÇTİ  → {source_url[:80]}")
                        
                logger.info(f"🔎 Filtre sonucu: {len(response.points)} → {len(valid_points)} belge kaldı")
                
                if not valid_points:
                    logger.warning(f"Fakülte filtresine takıldı! '{req_facs}' içeren belge bulunamadı.")
            else:
                # Kullanıcı spesifik fakülte sormamışsa hepsini al
                valid_points = response.points
            
            # Re-Ranker ile en iyi top_k belgeyi seç
            reranked_points = rerank(search_query, valid_points, top_n=top_k)
            
            docs = []
            for hit in reranked_points:
                # Eger hit objesi qdrant'tan gelen bir obje ise score'u olabilir,
                # ama degilse (fallback vs), hasattr ile korumaya alalim.
                score_val = hit.score if hasattr(hit, 'score') else 0.0
                docs.append({
                    "score": score_val,
                    "text": hit.payload.get("text", ""),
                    "source_url": hit.payload.get("source_url", ""),
                    "source_key": hit.payload.get("source_key", "")
                })
            
            logger.info(f"{len(docs)} adet ilgili metin bulundu.")
            return docs
            
        except Exception as e:
            logger.error(f"Arama sırasında hata: {e}")
            return []

if __name__ == "__main__":
    retriever = Retriever()
    res = retriever.search("Yemekhane ücretleri ne kadar?")
    for r in res:
        print(f"\n[Score: {r['score']}] - {r['source_url']}\n{r['text']}")
