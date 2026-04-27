# İnönü AI — Docker Altyapısı

## Dizin Yapısı

```
inonu_ai/
│
├── docker-compose.yml          # Ana servis tanımları
├── Dockerfile                  # Python uygulama imajı
├── requirements.txt            # Python bağımlılıkları
├── .env.example                # Ortam değişkeni şablonu
├── .gitignore
│
├── docker/                     # Servis konfigürasyonları
│   ├── qdrant/
│   │   └── config.yaml         # Qdrant üretim ayarları
│   ├── prometheus/
│   │   └── prometheus.yml      # Metrik toplama ayarları
│   └── grafana/
│       └── provisioning/
│           └── datasources/
│               └── prometheus.yml
│
├── agents/                     # LangGraph ajan modülleri
│   ├── router_agent.py
│   ├── rag_agent.py
│   ├── web_agent.py
│   └── grader_agent.py
│
├── tools/
│   ├── live_scraper.py
│   ├── qdrant_search.py
│   └── reranker.py
│
├── data_pipeline/
│   ├── batch_crawler.py
│   ├── chunker.py
│   ├── indexer.py
│   ├── url_config.py
│   └── scheduler.py
│
├── engine/
│   ├── sglang_client.py
│   ├── embedding.py
│   └── memory.py
│
├── api/
│   └── main.py
│
└── monitoring/
    └── metrics.py
```

## Neden Bu Yapı?

**SGLang ve vLLM Docker içinde değil!**
GPU'ya doğrudan erişim için bu iki servis host üzerinde çalıştırılır.
Docker'ın GPU passthrough'u ek gecikme ve karmaşıklık yaratır.
`inonu_app` container'ı bunlara `host.docker.internal` üzerinden bağlanır.

## Aşama 0 — Başlatma

```bash
# 1. Ortam dosyasını hazırla
cp .env.example .env

# 2. Sadece altyapıyı başlat (Qdrant + Prometheus + Grafana)
docker compose up -d qdrant prometheus grafana

# 3. Servisleri kontrol et
docker compose ps
curl http://localhost:6333/healthz    # Qdrant
curl http://localhost:9090/-/ready    # Prometheus
# Grafana: http://localhost:3000  (admin / inonu_grafana_2025)
```

## Uygulama Başlatma (Aşama 1+)

```bash
# Python imajını derle ve uygulamayı başlat
docker compose --profile app up -d inonu_app

# Logları takip et
docker compose logs -f inonu_app
```

## Faydalı Komutlar

```bash
# Tüm servisleri durdur
docker compose down

# Verileri sıfırla (dikkat!)
docker compose down -v

# Tek servisi yeniden başlat
docker compose restart qdrant

# Qdrant koleksiyonlarını listele
curl http://localhost:6333/collections
```
