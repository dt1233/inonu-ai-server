# Takım 1: Veri Toplayıcılar

**Ekip:** Türker, Burak, Arda
**Ana Görev:** Üniversitenin tüm dijital metin haritasını çıkarmak ve yapay zeka için temiz bir veri tabanı oluşturmak.
**Bağımlılık Durumu:** Kimseyi beklemez, proje başladığı an çalışmaya başlar.

## 📌 Görev Adımları (Step-by-Step)

- [ ] **1. URL Haritasının Çıkarılması**
  - Fakülte, Enstitü, SKS, Kütüphane ve Rektörlük sitelerinin kök (root) URL'lerini tespit edip `url_config.py` (veya benzeri bir dosyaya) listelemek.
- [ ] **2. Recursive Crawler (Gezgin Bot) Kodlanması**
  - Belirlenen derinliğe (depth) kadar inen, alt linkleri otomatik bulan bir bot yazmak. (Örn: `scrapy` veya `BeautifulSoup` + `requests` ile).
- [ ] **3. Metin Temizliği (Data Cleaning)**
  - Web sitelerinden çekilen HTML verilerindeki gereksiz menüleri, css/js kodlarını ve footer'ları (altbilgi) temizleyerek sadece bilgi barındıran "saf metinleri" ayıklamak.
- [ ] **4. Merkezi Veritabanı Oluşturma**
  - Temizlenen verileri `{"url": "...", "birim": "...", "baslik": "...", "icerik": "..."}` formatında JSONL dosyası olarak kaydetmek.
- [ ] **5. Teslimat**
  - Elde edilen `ham_veri.jsonl` dosyasını **Takım 2 (QA Üretimi)** ve **Takım 4 (Qdrant Yüklemesi)** ekiplerine iletmek.
