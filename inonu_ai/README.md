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





