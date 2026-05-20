# 🎓 İnönü AI — Solo Geliştirici Yol Haritası

> **Son güncelleme:** 2026-05-17
> **Mimari:** RAG (Qdrant) + LangGraph Ajan + FastAPI + Qwen3-8B (SGLang)

---

## ✅ TAMAMLANAN İŞLER

- [x] **url_config.py genişletildi** — 15 fakülte, 4 enstitü, 10 MYO, SKS, Kütüphane, UZEM, BAPK, Kariyer, TOTM
- [x] **batch_crawler.py güncellendi** — run_daily/run_weekly/run_all/run_html_static/run_avesis metotları
- [x] **avesis_crawler.py yazıldı** — Playwright tabanlı AVESİS akademik personel çekici
- [x] **chunker.py güncellendi** — chunk_avesis_staff + _avesis_staff_to_text eklendi
- [x] **scheduler.py güncellendi** — Yeni batch_crawler mimarisine uyumlu

---

## 🔴 ACİL DÜZELTME GEREKLİ

### H1 — Dosyalar diske kaydedilmemiş
- avesis_crawler.py → 0 byte (boş!)
- batch_crawler.py → eski 540 satırlık versiyon
- chunker.py → eski versiyon
- **Çözüm:** VS Code'da Ctrl+K, S ile tüm dosyaları kaydet

### H2 — batch_crawler.py typo
- `run_fakulte_announcements` içinde `FAKULTELE_TARGETS` yazılmış
- Doğrusu: `FAKULTE_TARGETS`

### H3 — httpx bağımlılığı eksik
- `_crawl_html_static` httpx kullanıyor ama requirements.txt'de yok
- **Çözüm:** `pip install httpx` veya requirements.txt'e ekle

---

## 🟡 inonu.edu.tr KAPSAM ANALİZİ

### Kapsanan:
| Kaynak | Sayı | Yöntem |
|---|---|---|
| Panel API Duyuru | ~35 birim | API_JSON paginated |
| Panel API Personel | ~35 birim | API_STAFF |
| Panel API Statik | ~12 sayfa | API_JSON |
| AVESİS Kadro | ~19 birim | Playwright |
| Fakülte Sayfaları | ~15 | HTML_STATIC |

### Kapsanmayan:
- [ ] Panel unit key doğrulaması (bazıları 404 dönebilir)
- [ ] Fakülte bölüm alt sayfaları
- [ ] obs.inonu.edu.tr (login gerekli)
- [ ] Yemekhane menüsü, taban puanları, yönetmelik PDF'leri

---

## 🗺️ AŞAMA 1 — ORTAM KURULUMU

- [ ] 1.1 — `.env` dosyası oluştur
- [ ] 1.2 — `pip install -r requirements.txt && playwright install chromium`
- [ ] 1.3 — Qdrant kur (sunucu)
- [ ] 1.4 — Redis kur (sunucu)
- [ ] 1.5 — SGLang başlat (Qwen3-8B)
- [ ] 1.6 — `pip install httpx`

## 🗺️ AŞAMA 2 — VERİ TOPLAMA (✅ BÜYÜK ÖLÇÜDE TAMAM)

- [x] 2.1 — URL haritası genişletildi
- [x] 2.2 — HTML_STATIC crawler yazıldı
- [x] 2.3 — AVESİS crawler yazıldı
- [x] 2.4 — PDF desteği mevcut
- [ ] 2.5 — Panel unit key doğrulaması
- [ ] 2.6 — Tam tarama: `python -m data_pipeline.scheduler --full`

## 🗺️ AŞAMA 3 — QDRANT VE TEST

- [ ] 3.1 — İndeksleme (scheduler --full otomatik yapar)
- [ ] 3.2 — Kalite testi (test_sor.py) — Hedef: 5000+ chunk

## 🗺️ AŞAMA 4-5 — MODEL EĞİTİMİ (Sonra)

- [ ] QA veri seti üret → QLoRA fine-tuning → merge → SGLang

## 🗺️ AŞAMA 6 — GÜVENLİK

- [ ] CORS düzelt, Rate limiting, Input validasyonu

## 🗺️ AŞAMA 7 — CANLIYA ALMA

- [ ] Systemd + Nginx + SSL + Cron

---

## ⚡ KRİTİK YOL

```
1. Dosyaları diske kaydet (Ctrl+K, S)  ← ŞU AN BURADASIN
2. Ortam kur (Qdrant + Redis + SGLang)
3. Unit key doğrula + tam tarama
4. Qdrant'a yükle + test
5. Güvenlik → Canlıya al → Fine-tuning
```
