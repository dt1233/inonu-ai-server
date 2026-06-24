import os
import json
from loguru import logger
from qdrant_client import QdrantClient
from engine.embedding import encode_batch

class Retriever:
    def __init__(self):
        db_path = os.path.join(os.getcwd(), "qdrant_storage")
        if not os.path.exists(db_path):
            logger.warning("qdrant_storage bulunamadı! Lütfen önce indexer'ı çalıştırın.")
            
        self.client = QdrantClient(path=db_path)
        self.collection_name = os.getenv("QDRANT_COLLECTION", "inonu_docs")

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        logger.info(f"Soru aranıyor: {query}")
        
        # 1. Soruyu vektöre çevir
        embeddings = encode_batch([query])
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
                        limit=20,
                    ),
                    models.Prefetch(
                        query=models.SparseVector(
                            indices=indices,
                            values=values,
                        ),
                        using="sparse",
                        limit=20,
                    )
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=top_k,
                with_payload=True
            )
            
            docs = []
            for hit in response.points:
                docs.append({
                    "score": hit.score,
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
