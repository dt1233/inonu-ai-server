# Takım 4: RAG, Optimizasyon ve Canlıya Alma (Production)

**Ekip:** Bilal, Ferhat
**Ana Görev:** Sistemin mimarisini kurmak, API güvenliklerini yazmak, Qdrant'ı doldurmak ve en son modeli sisteme takarak canlı yayına (Production) almak.
**Bağımlılık Durumu:** Altyapı ve güvenlik kodları için kimseyi beklemez. Vektörizasyon için Takım 1'i, canlıya alma için Takım 3'ü bekler.

## 📌 Görev Adımları (Step-by-Step)

- [ ] **1. Güvenlik ve API Altyapısı (Hemen Başlanacak)**
  - Kötü niyetli saldırıları önlemek için sisteme IP tabanlı Rate Limit (Hız Sınırı) kuralı eklemek.
  - Sadece üniversite alan adlarına izin verecek CORS ayarlarını yapılandırmak.
- [ ] **2. Önbellek (Cache) Kurulumu (Hemen Başlanacak)**
  - Sık sorulan sorulara saniyeler içinde yanıt vermek için Redis (Semantic Cache) altyapısını kodlamak.
- [ ] **3. Qdrant Vektörizasyonu (Takım 1 Bekleniyor)**
  - Takım 1'den ham metinler geldiğinde, bunları Embedding modellerinden geçirerek Qdrant vektör veritabanına indekslemek.
- [ ] **4. LangGraph RAG Güncellemesi**
  - Model artık çoğu şeyi kendi ağırlıklarından bildiği için, Qdrant'ı sadece Rakam/Tarih doğrulaması (halüsinasyon önleme) için kullanacak şekilde RAG promptlarını revize etmek.
- [ ] **5. Sistemin Canlıya Alınması (Takım 3 Bekleniyor)**
  - Takım 3'ün eğittiği yeni `Inonu-Qwen3-8B` modelini SGLang sunucusuna bağlayıp test etmek.
  - SGLang ve FastAPI sunucularını Linux üzerinde arka planda kalıcı çalışacak `systemd` servisleri olarak ayarlayıp **projeyi tam sürüme (V1.0) geçirmek.**
