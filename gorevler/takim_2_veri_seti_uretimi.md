# Takım 2: Veri Seti Üreticileri

**Ekip:** Temel, Can
**Ana Görev:** Takım 1'den gelen ham metinleri yapay zekanın "Instruction-Tuning" (öğrenme) aşamasında kullanabileceği Soru-Cevap (QA) çiftlerine dönüştürmek.
**Bağımlılık Durumu:** Takım 1'in veri kazıma işlemini (kısmen veya tamamen) bitirmesini ve `ham_veri.jsonl` dosyasını teslim etmesini bekler.

## 📌 Görev Adımları (Step-by-Step)

- [ ] **1. QA Üretim Betiğinin Yazılması**
  - SGLang veya vLLM altyapısını kullanarak, 50 GB GPU gücüyle yüksek batch-size'da hızlı Soru-Cevap üretecek Python kodunu hazırlamak.
- [ ] **2. Sentetik Veri Üretimi**
  - Takım 1'den gelen ham metinleri bu betiğe verip, LLM'in her paragraf için "Soru: ... Yanıt: ..." formatında çıkarımlar yapmasını sağlamak.
- [ ] **3. Kalite Kontrol (Manuel İnceleme)**
  - Üretilen on binlerce soruyu hızla gözden geçirip, anlamsız, hatalı veya halüsinasyon içeren soru-cevap çiftlerini silmek.
- [ ] **4. Veri Formatının Dönüştürülmesi**
  - Temizlenmiş QA listesini, LLaMA-Factory/Unsloth gibi araçların anlayacağı ShareGPT veya Alpaca JSON formatına dönüştürmek.
- [ ] **5. Sistem Talimatının (System Prompt) Eklenmesi**
  - Veri setine İnönü Üniversitesinin resmi yapay zeka kişiliğini (Sen İnönü Üniversitesi asistanısın...) tanımlayan talimatları gömmek.
- [ ] **6. Teslimat**
  - Eğitim için hazır olan `egitim_verisi.json` dosyasını asıl eğitimi yapacak olan **Takım 3'e teslim etmek.**
