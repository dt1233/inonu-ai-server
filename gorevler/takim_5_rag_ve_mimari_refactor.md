# Takım 5: RAG ve Veri Hattı (Data Pipeline) Mimari Refactoring

**Durum:** 🚧 BEKLİYOR
**Öncelik:** P0 (Kritik)
**Amaç:** RAG motorunun yanlış fakülte/kaynak getirme sorununu çözmek, PDF içeriklerini sayfa ve sahiplik bazında ayırmak, Qdrant veritabanını temiz ve doğrulanabilir hale getirmek, fine-tuning öncesi güvenilir bilgi hattı kurmak.

Bu doküman, detaylı kod denetimi ve **SOLID prensipleri (Clean Architecture)** gözetilerek çıkarılmış kusursuzlaştırılmış **Uygulama Planı ve Görev Listesi**'dir.

---

## 🎯 Fine-Tuning Stratejisi
Qwen3B modeline fine-tuning ile tarih, duyuru, büt, akademik takvim gibi değişken bilgileri ezberletmek **yanlıştır**.
- **RAG’ın işi:** Tarih, duyuru, akademik takvim, personel, PDF, büt tarihleri.
- **Fine-tuning’in işi:** İnönü Asistan kimliği, Türkçe kurum dili, kaynaklara sadakat, “bilgi yoksa uydurmama (bilmiyorum deme)” davranışı.
*Fine-tuning ancak RAG testleri yeşile döndükten sonra yapılacaktır.*

---

## 🚀 Uygulama (Execution) Sırası ve Mimari Standartlar

### 1. Ortak Yardımcı Modül (DRY Prensibi)
- [ ] **[NEW] `inonu_ai/data_pipeline/faculty_detector.py`**
  - **Görevi:** Tek merkezi fakülte/birim tespit modülü. Crawler, PDF extractor, chunker ve retriever aynı modülü kullanacak.
  - **Mekanizma:** Türkçe karakter normalize edecek. "müh", "muhendislik", "Mühendislik Fakültesi" gibi varyasyonları yakalayacak. Fakülte ile genel birim ayrımını destekleyecek.
  - **Ek Kural:** Dönüş formatı: `{"fakulte": "Mühendislik Fakültesi" | None, "confidence": 0.0-1.0, "matched_terms": [...]}`

### 2. Veri Şeması Sözleşmesi (Data Contract)
- [ ] **Veri Sözleşmesinin Sabitlenmesi**
  - Zorunlu metadata:
  ```json
  {
    "unit": "muhendislik",
    "unit_label": "Mühendislik Fakültesi Duyuruları",
    "fakulte": "Mühendislik Fakültesi",
    "source_fakulte": "Mühendislik Fakültesi",
    "detected_fakulte": "Diş Hekimliği Fakültesi",
    "scope": "faculty|university|unit|unknown",
    "doc_type": "announcement|pdf_page|static|avesis",
    "page_no": 3,
    "ann_id": 12345,
    "title": "...",
    "published_at": "...",
    "source_url": "...",
    "content_hash": "..."
  }
  ```
  - **Ek Kural:** `fakulte` (kaynağın ait olduğu), `source_fakulte` (duyuruyu yayınlayan), `detected_fakulte` (içerikten tespit edilen asıl sahip).
  - `scope=university`: Genel akademik takvim gibi belgeler.
  - `content_hash`: Duplicate (tekrarlı) kayıtları yakalamak için zorunlu.

### 3. Crawler Düzeltmeleri
- [ ] **[MODIFY] `batch_crawler.py`**
  - `FAKULTELE_TARGETS` gibi typo'lar temizlenecek. Çağrılmayan ölü fonksiyonlar kaldırılacak.
  - Eksik metadata kaydı quality report'a hata olarak düşecek. Sessizce geçilmeyecek.
  - **Ek Kural:** Crawler sonucu doğrudan güvenilir kabul edilmeyecek. `validate_record(record)` fonksiyonu ile her kayıt kontrol edilecek.

### 4. PDF Pipeline (Sayfa Bazlı Extraction)
- [ ] **[NEW] `pdf_extractor.py`**
  - PDF tek blok değil, sayfa sayfa ayrıştırılacak. Her sayfa ayrı record olacak ve `faculty_detector` ile `detected_fakulte` sayfa bazında yazılacak.
  - **Ek Metadata:** `{"doc_type": "pdf_page", "page_no": 4, "page_count": 12, "pdf_url": "...", "pdf_text_quality": "text|ocr_required|empty|error", "extractor": "pypdf|ocr"}`
  - **P0 Kural:** Sayfa boşsa veya bozuksa `[PDF Okunamadı]` diye indekslenmeyecek. Quality report'a düşecek. OCR yoksa `ocr_required` işaretlenecek.

### 5. Chunker ve Context Sealing
- [ ] **[MODIFY] `chunker.py` Context Sealing**
  - PDF page recordları hazır veri olarak gelecek.
  - **Bağlam Mührü:** *Kapsam: [scope] | Kaynak Birim: [unit_label] | Ana Fakülte: [fakulte] | Kaynak Fakülte: [source_fakulte] | Tespit Edilen Fakülte: [detected_fakulte] | Başlık: [title] | Belge Tipi: [doc_type] | Sayfa No: [page_no]*
  - **Ek Kural:** `source_key` dinamik olacak. Örn: `announcement:muhendislik`, `pdf_page:muhendislik:19316:7`.

### 6. Indexer ve Qdrant
- [ ] **[MODIFY] `indexer.py` (Payload Indexes)**
  - `unit`, `fakulte`, `source_fakulte`, `detected_fakulte`, `scope`, `kategori`, `doc_type`, `ann_id`, `content_hash` için otomatik index oluşturulacak.
  - **P0 Kural:** `ensure_collection(reset=True)` sonrası payload indexler de yeniden kurulacak. Aynı `content_hash` (PDF sayfası vs) iki kez indekslenmeyecek.

### 7. Merkezi Retriever (Strict/Fallback)
- [ ] **[MODIFY] `engine/retriever.py`**
  - Retriever dönüş formatı: `{"text": "...", "score": 0.82, "source_url": "...", "metadata": {...}}`.
  - **Strict/Fallback Kuralı:** 
    1. Soru fakülte içeriyorsa `requested_fakulte` çıkarılır.
    2. `detected_fakulte` doluysa asıl sahiplik odur. `detected_fakulte != requested_fakulte` ise chunk elenir.
    3. `detected_fakulte` boşsa `fakulte` veya `source_fakulte` kullanılır.
    4. Strict sonuç **< 2** ise `scope=university` kaynaklara fallback yapılır. (Fallback'te rakip fakülteler yasaktır).
  - **P0 Kural:** "Genel üniversite" dokümanları fakülte sorularında kullanılabilir ama içinde açıkça başka fakülte adı geçen doküman kullanılamaz.
  - **Debug Raporu:** Retriever her sorguda konsola: "kaç aday geldi, kaçı strict geçti, kaçı owner mismatch elendi, fallback çalıştı mı" raporu basmalı.

### 8. Agent/API Adaptasyonu
- [ ] **[MODIFY] `agents/nodes.py`**
  - Doğrudan Qdrant araması tamamen kaldırılacak. Sadece `Retriever.search()` çağrılacak. `_indexer = None` hatası düzeltilecek.
  - **Ek Kural:** API response'una `sources` listesi eklenecek: `{"answer": "...", "sources": [{"source_url": "...", "title": "...", "fakulte": "...", "detected_fakulte": "...", "score": 0.82}]}`.

### 9. Reranker
- [ ] **[MODIFY] `tools/reranker.py`**
  - `device = "cuda" if torch.cuda.is_available() else "cpu"` (Hardcode kaldırılacak).
  - **Ek Kural:** Reranker skoru metadataya yazılacak. `retrieval_score` ve `rerank_score` ayrı tutulacak.

### 10. Scheduler ve Safe Merge
- [ ] **[MODIFY] `scheduler.py` Safe Merge**
  - `ann_id + unit + source_url + page_no` bazlı upsert yapılacak. Eski veri ezilmeyecek. Günlük crawl boş dönerse veri silinmeyecek.
  - **P0 Kural:** Günlük pipeline (Daily update) asla full dataset'i bozmayacak. Full rebuild ayrı komut olacak. Merge sonrası quality report otomatik çalışacak.

### 11. Encoding Standardı ve Güvenlik
- [ ] **Encoding Standardı:** Tüm JSON I/O işlemleri `encoding="utf-8"`.
- **Ek Kural:** Quality report, `, Ä, Å, Ã, Â` karakter anomalilerini yakalayacak. Eşik aşılırsa kirli metin Qdrant'a yazılmayacak, reindex durdurulacak.

### 12. Quality Report (Kritik Gözlemlenebilirlik)
- [ ] **[NEW] `quality_report.py`**
  - Raporlanacak metrikler: Toplam crawl/chunk sayısı, boş `fakulte`/`unit` sayısı, PDF page sayısı, `detected_fakulte` bulunan PDF sayısı, Owner mismatch sayısı, Duplicate `content_hash` sayısı, Encoding anomaly sayısı, Müh+büt/Hukuk+büt oranları.
  - **P0 Kural:** `max_empty_fakulte_for_faculty_scope: 0`, `max_encoding_anomaly_ratio: 0.01`, `max_duplicate_hash_ratio: 0.05` gibi kritik eşikler aşılırsa **reindex yapılmayacak**.

### 13. Eski Kirli Verinin Temizlenmesi
- [ ] Eski `chunks_output.json` yeniden üretilecek. Eski `crawl_results.json` baştan crawl edilecek (veya migrate edilecek). Qdrant `--reset` edilecek. Kirli vektörler kesinlikle korunmayacak.
- **Ek Kural:** Reset öncesi `data/archive/` dizinine tarihli yedek alınacak.

### 14. Regression Testleri ve Test Runner
- [ ] **[NEW] `tests/rag_cases.yaml` & Test Runner**
  - Test senaryosu formatı:
  ```yaml
  - query: "Mühendislik Fakültesi bütleri ne zaman?"
    expected_any: ["Mühendislik Fakültesi", "genel akademik takvim", "15-26 Haziran"]
    forbidden: ["Hukuk Fakültesi", "Tıp Fakültesi", "Diş Hekimliği"]
    required_source_scope: ["faculty", "university"]
  ```
  - **Test Runner Kontrolleri:** Sadece cevabı değil, "retrieved docs içinde yasak fakülte var mı?", "metadata doğru mu?", "fallback çalıştı mı?", "bilgi yoksa uyduruyor mu?" kontrol edecek.
