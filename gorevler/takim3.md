# Takım 3: Model Eğitmenleri (Fine-Tuning)

**Ekip Sayısı:** 1 Kişi
**Ana Görev:** L40S (50 GB) GPU gücünü kullanarak ana modeli (Qwen3-8B) üniversite verisiyle eğitmek ve üniversiteye özgü yeni bir model ağırlığı yaratmak.
**Bağımlılık Durumu:** Kurulumlar için kimseyi beklemez hemen başlar. Asıl eğitim için Takım 2'nin JSON dosyasını teslim etmesini bekler.

## 📌 Görev Adımları (Step-by-Step)

- [ ] **1. Eğitim Ortamının Kurulması (Hemen Başlanacak)**
  - Sunucuya Unsloth veya LLaMA-Factory araçlarını kurmak, NVIDIA/CUDA sürücü ve kütüphane testlerini gerçekleştirmek.
- [ ] **2. Veri Setinin Yüklenmesi**
  - Takım 2'den gelen `egitim_verisi.json` dosyasını sunucuya çekmek ve eğitim aracına tanımlamak.
- [ ] **3. Model Eğitimi (QLoRA)**
  - Hyperparameter (Öğrenme oranı, Epoch sayısı, Batch size vb.) ayarlarını yaparak Qwen3-8B modelinin eğitimini başlatmak.
- [ ] **4. Adaptörlerin Birleştirilmesi (Merge)**
  - Eğitim tamamlandığında ortaya çıkan LoRA adaptör ağırlıklarını ana modelin ağırlıklarıyla birleştirip tek ve bağımsız bir model haline getirmek.
- [ ] **5. Teslimat**
  - Yeni oluşturulan `Inonu-Qwen3-8B` model klasörünü sunucuda ilgili dizine taşıyarak projeyi canlıya alacak olan **Takım 4'e teslim etmek.**
