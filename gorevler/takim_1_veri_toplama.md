# Takım 1: Veri Toplayıcılar

**Ekip:** Türker, Burak, Arda
**Ana Görev:** Üniversitenin tüm dijital metin haritasını çıkarmak ve yapay zeka için temiz bir veri tabanı oluşturmak.
**Bağımlılık Durumu:** Kimseyi beklemez, proje başladığı an çalışmaya başlar.
**Durum:** ✅ TAMAMLANDI (19 Mayıs 2026)

## 📌 Görev Adımları (Step-by-Step)

- [x] **1. URL Haritasının Çıkarılması**
  - Fakülte, Enstitü, SKS, Kütüphane ve Rektörlük sitelerinin kök (root) URL'lerini tespit edip `url_config.py` dosyasına listelendi. Toplam 119 hedef, 19 AVESİS birimi.
- [x] **2. Recursive Crawler (Gezgin Bot) Kodlanması**
  - `batch_crawler.py`: Panel API (JSON), HTML_STATIC (BeautifulSoup), HTML_JS (Playwright), AVESİS (Searchkit arama) destekli çoklu strateji kazıyıcı.
- [x] **3. Metin Temizliği (Data Cleaning)**
  - `chunker.py`: Markdown başlık bazlı + Recursive parçalama ile saf metin üretimi. AVESİS personel ve SSS formatları özel olarak işleniyor.
- [x] **4. Merkezi Veritabanı Oluşturma**
  - `crawl_results.json` olarak arşivlendi. 3000+ duyuru, 45 statik API kaynağı, 19 fakülte/enstitü AVESİS akademik kadrosu.
- [x] **5. Teslimat**
  - Veri **Takım 2** ve **Takım 4** tarafından kullanılmaya hazır.
