# 🎓 İnönü AI — Öğrenci İşleri Yapay Zeka Asistanı

İnönü Üniversitesi Öğrenci İşleri Daire Başkanlığı için geliştirilmiş **RAG (Retrieval-Augmented Generation)** tabanlı yapay zeka soru-cevap sistemi.

## 🏗️ Mimari

```
Kullanıcı → FastAPI (JWT) → LangGraph Ajan Akışı
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
                 Router       Rewriter      Generator
                    │             │             ▲
                    ▼             ▼             │
               Direct/RAG    HyDE Query    Qdrant Search
                                              + Re-Rank
```

**Ajan Akışı:** `Router → Query Rewriter → HyDE Retriever → Generator → CRAG Grader`

## 🛠️ Teknoloji Yığını

| Katman | Teknoloji |
|--------|-----------|
| **LLM** | Qwen3-8B (SGLang üzerinden) |
| **Embedding** | BAAI/bge-m3 (dense + sparse) |
| **Re-Ranker** | bge-reranker-v2-m3 (GPU FP16) |
| **Vektör DB** | Qdrant (Hybrid Search) |
| **Ajan Çatısı** | LangGraph (StateGraph) |
| **API** | FastAPI + JWT Authentication |
| **Oturum** | Redis (TTL tabanlı) |
| **Kazıma** | Crawl4AI + BeautifulSoup |
| **İzleme** | Prometheus + Grafana |

## 📁 Dizin Yapısı

```
inonu_ai/
├── config.py                    # Merkezi konfigürasyon (.env okur)
├── .env.example                 # Ortam değişkenleri şablonu
├── requirements.txt             # Python bağımlılıkları
│
├── api/                         # REST API Katmanı
│   ├── main.py                  # FastAPI uygulaması & endpoint'ler
│   ├── auth.py                  # JWT token üretme & doğrulama
│   └── models.py                # Pydantic request/response modelleri
│
├── agents/                      # LangGraph Ajan Modülleri
│   ├── state.py                 # AgentState tanımı
│   ├── graph.py                 # StateGraph akış tanımı
│   ├── nodes.py                 # Router, Rewriter, Retriever, Generator, Grader
│   ├── router_agent.py          # Sorgu sınıflandırma
│   ├── rag_agent.py             # RAG bilgi erişimi
│   ├── web_agent.py             # Canlı web kazıma (opsiyonel)
│   └── grader_agent.py          # CRAG kalite denetimi
│
├── tools/                       # Yardımcı Araçlar
│   ├── reranker.py              # bge-reranker GPU wrapper
│   ├── qdrant_search.py         # Hybrid search aracı
│   └── live_scraper.py          # Crawl4AI anlık kazıma
│
├── data_pipeline/               # Veri İşleme Pipeline'ı
│   ├── batch_crawler.py         # Toplu site tarama
│   ├── chunker.py               # Akıllı metin parçalama
│   ├── indexer.py               # Vektör DB'ye yazma
│   ├── url_config.py            # Hedef URL tanımları
│   └── scheduler.py             # APScheduler cron görevleri
│
├── engine/                      # Motor Modülleri
│   ├── sglang_client.py         # SGLang OpenAI-uyumlu LLM istemcisi
│   ├── embedding.py             # GPU embedding servisi
│   └── memory.py                # Bellek yönetim facade'ı
│
├── memory/                      # Bellek Yönetimi
│   ├── session_manager.py       # Redis oturum geçmişi
│   └── semantic_cache.py        # Vektör benzerlik önbelleği
│
└── monitoring/                  # İzleme
    └── metrics.py               # Prometheus metrikleri
```

## 🚀 Kurulum

### 1. Gereksinimler

- **Python 3.11+**
- **CUDA destekli GPU** (embedding ve re-ranker için)
- **Qdrant** (vektör veritabanı)
- **Redis** (oturum yönetimi & önbellek)
- **SGLang** (LLM sunucusu)

### 2. Qdrant Kurulumu

```bash
# Ubuntu/Debian
curl -s https://install.qdrant.tech | bash
sudo systemctl enable qdrant
sudo systemctl start qdrant

# Kontrol
curl http://localhost:6333/healthz
```

### 3. Redis Kurulumu

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install redis-server -y
sudo systemctl enable redis-server
sudo systemctl start redis-server

# Kontrol
redis-cli ping   # PONG dönmeli
```

### 4. Python Ortamı

```bash
cd inonu_ai/

# Sanal ortam oluştur
python3 -m venv venv
source venv/bin/activate

# Bağımlılıkları kur
pip install -r requirements.txt

# Playwright tarayıcısını kur (web kazıma için)
playwright install chromium
```

### 5. Ortam Değişkenleri

```bash
# .env dosyasını oluştur
cp .env.example .env

# .env dosyasını düzenle — özellikle şunları ayarla:
#   JWT_SECRET_KEY    → Güçlü bir anahtar
#   ADMIN_PASSWORD    → Güvenli bir şifre
#   SGLANG_MODEL      → Model yolu
#   RERANKER_MODEL_PATH → Re-ranker model yolu
nano .env
```

### 6. SGLang Model Sunucusu

```bash
# Qwen3-8B modelini SGLang ile başlat
python -m sglang.launch_server \
    --model-path /home/yapayzeka/models/Qwen3-8B \
    --port 30000 \
    --tp 1
```

### 7. İlk Veri Kazıma

```bash
# Tüm kaynakları sıfırdan kazı ve vektör DB'ye yaz
python -m data_pipeline.scheduler --full
```

### 8. API'yi Başlat

```bash
# Geliştirme modu
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Üretim modu
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 2
```

## 🔐 API Kullanımı

### 1. Giriş Yapma (Token Alma)

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "inonu_ai_2025"}'
```

**Yanıt:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### 2. Soru Sorma

```bash
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
  -d '{"question": "Yatay geçiş şartları nelerdir?"}'
```

**Yanıt:**
```json
{
  "answer": "İnönü Üniversitesi'nde yatay geçiş için...",
  "session_id": "abc-123-def",
  "route": "rag",
  "cached": false,
  "response_time": 2.45
}
```

### 3. Python ile Kullanım

```python
import requests

BASE = "http://localhost:8000"

# Login
resp = requests.post(f"{BASE}/api/auth/login", json={
    "username": "admin",
    "password": "inonu_ai_2025",
})
token = resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Soru sor
resp = requests.post(f"{BASE}/api/ask", json={
    "question": "Erasmus programına nasıl başvurulur?",
}, headers=headers)

print(resp.json()["answer"])
```

## 📊 API Endpoint'leri

| Method | Endpoint | Açıklama | Auth |
|--------|----------|----------|------|
| `GET` | `/api/health` | Sağlık kontrolü | ❌ |
| `POST` | `/api/auth/login` | JWT token al | ❌ |
| `POST` | `/api/ask` | Soru sor | ✅ JWT |
| `POST` | `/api/session/new` | Yeni oturum | ✅ JWT |
| `GET` | `/api/session/{id}` | Oturum geçmişi | ✅ JWT |
| `GET` | `/api/stats` | Sistem istatistikleri | ✅ JWT |
| `GET` | `/docs` | Swagger UI | ❌ |
| `GET` | `/metrics` | Prometheus metrikleri | ❌ |

## 🔄 Otomatik Veri Güncelleme

Scheduler, üniversite web sitesini düzenli olarak tarar:

| Zamanlama | Hedef | Saat |
|-----------|-------|------|
| **Günlük** | Duyurular (delta fetch) | 02:00 |
| **Haftalık** | Personel, dersler, oryantasyon | Pzt 03:00 |
| **Aylık** | Tarihçe, misyon, SSS, iç kontrol | 1. gün 04:00 |

```bash
# Scheduler'ı başlat (arka planda)
python -m data_pipeline.scheduler
```

## 🖥️ Systemd ile Arka Plan Çalıştırma

```bash
# /etc/systemd/system/inonu-ai.service
[Unit]
Description=İnönü AI API Servisi
After=network.target redis.service

[Service]
Type=simple
User=yapayzeka
WorkingDirectory=/home/yapayzeka/inonu-proje/inonu_ai
Environment=PATH=/home/yapayzeka/inonu-proje/inonu_ai/venv/bin
ExecStart=/home/yapayzeka/inonu-proje/inonu_ai/venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable inonu-ai
sudo systemctl start inonu-ai
sudo systemctl status inonu-ai
```

## 📝 Lisans

Bu proje İnönü Üniversitesi için geliştirilmiştir.
