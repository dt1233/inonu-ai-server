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

## 3. Çalıştırma Talimatları (Adım Adım)

Tüm komutları sunucuya bağlandıktan sonra, **sadece `(lf_egitim)` ortamında** çalıştırmalısınız. (Eski `venv` klasörünü kullanmayın!)

### Adım 1: Doğru Ortama Geçiş
```bash
conda activate lf_egitim
cd ~/inonu-proje/inonuasilproje/inonu_ai
```

### Adım 2: Çöp Ortamların Temizliği (Sadece İlk Kurulumda)
Sunucudaki karışıklığı önlemek için eski ve çalışmayan ortam klasörleri silinmelidir:
```bash
# SADECE lf_egitim kullanılacağı için, eski manuel venv'yi siliyoruz:
rm -rf ~/inonu-proje/inonu_ai/venv
```

### Adım 3: Qdrant Vektör Veritabanını Sıfırlama ve İndeksleme
Eski bozuk indeksler yerine temizlenmiş chunks dosyasından yepyeni bir Qdrant indeksi yaratmak için:
```bash
HF_HUB_OFFLINE=1 python run_indexer.py --reset
```

### Adım 4: Yapay Zeka Motorunu (SGLang) Başlatma
Sistemin beyni olan modeli 30000 portunda arka planda çalıştırın:
```bash
HF_HUB_OFFLINE=1 nohup python -m sglang.launch_server \
  --model-path /home/yapayzeka/models/Qwen3-8B-inonu \
  --port 30000 \
  --host 0.0.0.0 \
  --tp 1 \
  --mem-fraction-static 0.85 \
  > ~/sglang.log 2>&1 &
```
*(Bu komut SGLang'ı başlatır. Yaklaşık 2 dakika sonra `curl http://localhost:30000/v1/models` ile test edilebilir).*

### Adım 5: Sistemi Test Etme (RAG Sohbeti)
Motor çalıştıktan sonra, komut satırından RAG tabanlı soruları test etmek için:
```bash
python inonu_ai/rag_chat.py
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
