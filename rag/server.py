"""
FastAPI Server for İnönü AI RAG Engine
Tüm asenkron endpointler ve API yönetimi burada yapılır.
"""

from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import time

from engine import RAGEngine, log
import config as cfg

app = FastAPI(
    title="İnönü AI RAG API",
    description="Campus Assistant RAG Engine REST API",
    version="6.0"
)

# Global engine instance
engine = RAGEngine()

class QueryRequest(BaseModel):
    question: str
    use_hyde: bool = True

class QueryResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]]
    confidence: float
    attempt: int
    shield_triggered: bool
    cached: bool
    latency_sec: float

@app.on_event("startup")
async def startup_event():
    """Server başladığında modeli bir kez belleğe yükle."""
    log("INFO", "FastAPI Server başlatılıyor, RAG Engine yükleniyor...")
    # startup is synchronous, we run it in thread just in case it blocks hard
    import asyncio
    await asyncio.to_thread(engine.startup)
    log("OK", "FastAPI sunucusu istek kabul etmeye hazır.")

@app.post("/api/chat", response_model=QueryResponse)
async def chat_endpoint(req: QueryRequest):
    """
    Ana sohbet uç noktası (endpoint).
    Agentic loop ile asenkron cevap üretir.
    """
    if not engine.ready:
        raise HTTPException(status_code=503, detail="Motor henüz hazır değil, modeller yükleniyor...")

    t0 = time.time()
    try:
        # Asenkron agentic_query çağrısı
        result = await engine.agentic_query(req.question)
        
        return QueryResponse(
            answer=result["answer"],
            sources=result["sources"],
            confidence=result.get("confidence", 0.0),
            attempt=result.get("attempt", 1),
            shield_triggered=result.get("shield_triggered", False),
            cached=result.get("cached", False),
            latency_sec=time.time() - t0
        )
    except Exception as e:
        log("ERR", f"API Hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "engine_ready": engine.ready,
        "cache_stats": engine.cache_stats()
    }

if __name__ == "__main__":
    import uvicorn
    # Doğrudan server.py çalıştırıldığında:
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
