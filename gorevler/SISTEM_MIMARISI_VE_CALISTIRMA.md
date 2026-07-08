# İNÖNÜ AI - SİSTEM MİMARİSİ VE ÇALIŞTIRMA KILAVUZU

Bu belge, projenin baştan sona nasıl çalıştığını, hangi portların kullanıldığını ve sistemin tek bir merkezden nasıl yönetileceğini açıklar. Tüm eski karmaşalar giderilmiş, proje yapısı temizlenmiş ve sistem tek bir temiz Conda ortamına (`lf_egitim`) bağlanmıştır.

## 1. Proje Özeti
İnönü AI, üniversitenin tüm verilerini (AVESİS, statik sayfalar, duyurular) tarayan (Crawling), bunları Qdrant vektör veritabanına indeksleyen (RAG) ve üniversite verileriyle özel olarak eğitilmiş (Fine-tuned) Qwen3-8B modelini kullanarak kullanıcılara doğru ve halüsinasyonsuz cevap veren bir Yapay Zeka Asistanıdır.

## 2. Kullanılan Portlar ve Servisler

Sistemin tam kalbinde ana servisler arka planda sürekli çalışmalıdır:

| Servis Adı | Port | Görevi | Çalıştırma Dosyası/Aracı |
|---|---|---|---|
| **SGLang (LLM API)** | `30000` | Yapay Zekanın Beyni. Eğitilmiş Qwen modelini OpenAI API formatında sunar. | `sglang.launch_server` |
| **Qdrant (Vektör DB)** | `6333` | Tüm üniversite verilerinin (48.000 chunk) vektör olarak tutulduğu veritabanı. | `qdrant_storage` (Lokal disk tabanlı çalışır) |
| **FastAPI / REST API** | `8000` | Sistem ile dış dünyayı bağlayan asıl Web API katmanı. | `inonu_ai/api/main.py` |

## 3. İki İzole Sanal Ortam Mimarisi (Kritik Mimari Karar)

Sistem profesyonel standartlara (Clean Architecture & Isolation) çekilmiş olup, **iki farklı izole Conda ortamında** çalışacak şekilde ayrılmıştır:

1. **`sglang_env` Ortamı:** **SADECE** SGLang yapay zeka inference (çıkarım) sunucusunu barındırır.
2. **`lf_egitim` Ortamı:** RAG arama motorunu, Crawler'ı, Qdrant vektör indekslemeyi ve FastAPI'yi barındırır.

**Neden İki Ayrı Ortam Kullanıyoruz?**
Yapay Zeka (LLM Inference) motorları (SGLang, vLLM) çok spesifik ve ağır CUDA/PyTorch bağımlılıklarına sahiptir. Uygulama tarafındaki (RAG) kütüphaneler (örneğin LangChain, FastAPI veya PDF ayrıştırıcılar) güncellendiğinde LLM motorunun çökmemesi için, sunucu ile uygulama katmanının bağımlılıkları birbirinden fiziksel olarak yalıtılmıştır.

## 4. Çalıştırma Talimatları (Adım Adım)

### Adım 1: Yapay Zeka Sunucusunu Başlatma (SGLang)
Sistemin beynini **`sglang_env`** ortamında, 30000 portunda arka planda başlatın:
```bash
conda activate sglang_env
cd ~/inonu-proje/inonuasilproje/inonu_ai

HF_HUB_OFFLINE=1 nohup python -m sglang.launch_server \
  --model-path /home/yapayzeka/models/Qwen3-8B-inonu \
  --port 30000 \
  --host 0.0.0.0 \
  --tp 1 \
  --mem-fraction-static 0.85 \
  > ~/sglang.log 2>&1 &
```
*(Logları `tail -f ~/sglang.log` ile izleyin. "Uvicorn running on http://0.0.0.0:30000" veya "Ready" mesajını görünce çıkın).*

### Adım 2: RAG ve API Uygulamasına Geçiş
Model çalıştıktan sonra, tüm RAG testleri ve API işlemleri için asıl geliştirme ortamına dönün:
```bash
conda activate lf_egitim
cd ~/inonu-proje/inonuasilproje/inonu_ai
```

### Adım 3: Qdrant Vektör Veritabanını İndeksleme (Gerekliyse)
Veri tabanını sıfırdan oluşturmak için:
```bash
# SADECE lf_egitim içindeyken!
HF_HUB_OFFLINE=1 python run_indexer.py --reset
```

### Adım 4: Sistemi Test Etme (İnteraktif RAG Sohbeti)
LLM hazır, RAG hazır. Terminal üzerinden ajanımızla konuşmak için:
```bash
# SADECE lf_egitim içindeyken!
export QDRANT_COLLECTION=inonu_docs_staging
python ../tests/interactive_rag.py
```

## 4. Dosyaların Görevleri (Dosya Haritası)

- **`inonu_ai/config.py`**: Sistemin TÜM ayarlarının, URL'lerin ve model yollarının yönetildiği merkezi nokta (DRY ve SOLID).
- **`inonu_ai/data_pipeline/chunker.py`**: Webden çekilen devasa metinleri parçalara böler. (Kısa duyuruların da kaçırılmaması için limit 40 karaktere düşürülmüştür).
- **`run_indexer.py` & `inonu_ai/data_pipeline/indexer.py`**: Parçalanan bu metinleri `bge-m3` modeliyle vektörlere çevirip Qdrant veritabanına yazar.
- **`inonu_ai/engine/sglang_client.py`**: SGLang ile haberleşmeyi tek merkezden yöneten API istemcisi.
- **`inonu_ai/engine/embedding.py`**: Metinleri matematiksel sayılara (vektörlere) çeviren kod.
- **`inonu_ai/engine/retriever.py`**: Qdrant'tan en alakalı ilk 20 belgeyi getirir ve **Re-Ranker** ile bunları en doğru 3 belgeye indirger.
- **`inonu_ai/rag_chat.py`**: Kullanıcının girdiği soruyu alır, `retriever` üzerinden arama yapar ve LLM motoruna gönderip ekrana yazdırır.
- **`inonu_ai/agents/nodes.py` & `inonu_ai/test_agent.py`**: İleri seviye RAG mimarisidir (LangGraph). "Peş peşe sorulan soruları (Memory)" hatırlama, gereksiz arama yapmama, yönlendirme (Router) ve notlandırma (Grader) işlemlerini yapar.
