# İnönü AI - Proje To-Do Listesi

---

## 🗄️ BÖLÜM A: VERİTABANI VE ETİKETLEME (Senin Sorumluluğun)

### Veri Toplama ve Sınıflandırma
- [ ] 1 -> Mevcut veri kaynaklarının (scraper çıktısı olan JSON, duyuru, akademisyen ve statik içerikler) incelenip merkezi bir veri havuzuna uygun ana hatlarıyla sınıflandırılması.
- [ ] 2 -> Sadece mevcut scraper'lara bağlı kalmaksızın senato kararları, duyuru PDF metinleri, ders kredileri, akademik takvim, yemekhane menüsü, Bologna bilgi sistemi gibi ek verilerin scrape/toplama haritasının oluşturulması.
- [ ] 3 -> Aynı verinin farklı scraper'lardan tekrar gelmesini engelleyecek bir Deduplication (tekrar önleme) mekanizmasının kurulması.

### Metadata ve Standartlaştırma
- [ ] 4 -> Veritabanı kayıtlarında her bir evrağa tarih, kaynak (fakülte/bölüm), URL, belge türü ve son güncelleme bilgisi gibi kritik meta etiketlerinin (metadata) standart bir formata oturtulması.
- [ ] 5 -> KVKK (Kişisel Verilerin Korunması Kanunu) kapsamında hangi kişisel verilerin (akademisyen telefon, e-posta vb.) saklanıp hangilerinin anonimleştirileceğinin belirlenmesi ve üniversite KVKK birimiyle görüşülmesi.

### Veri Ön İşleme (Data Preprocessing)
- [ ] 6 -> Scrape edilen verilerdeki tüm gürültüyü (gereksiz boşluk, bozuk HTML tagleri vb.) silecek ve UTF-8 string çıktılar üretecek ortak temizleme fonksiyonlarının kodlanıp aktif edilmesi.
- [ ] 7 -> Temizlenen metinleri anlam bütünlüğünü bozmayan mantıklı paragraflar/bloklar halinde (500-1000 kelimelik Chunk'lara) ayıracak metin parçalama (Chunking) sisteminin yazılması.

### Veritabanı Altyapısı
- [ ] 8 -> Hafıza sisteminin iskeleti olacak doğru Vektör Veritabanına (ChromaDB, pgvector, Qdrant vb.) karar verilip, lokalde/sunucuda altyapısının ayağa kaldırılması.
- [ ] 9 -> Türkçe dil desteği güçlü bir Embedding Modeline (BGE-m3, multilingual-e5-large, OpenAI text-embedding-3-small vb.) karar verilmesi ve benchmark testlerinin yapılması.
- [ ] 10 -> Chunk edilmiş tüm veri parçalarının seçilen Embedding modeli ile vektörlere dönüştürülüp Vektör Veritabanına aktarılması (import pipeline).
- [ ] 11 -> Chat geçmişi, sistem logları ve kullanıcı yetkilendirme için operasyonel veritabanı (PostgreSQL veya MongoDB) kurulumunun gerçekleştirilmesi.

### Etiketleme ve Veri Seti Üretimi
- [ ] 12 -> Veri kalitesini ölçmek ve manuel etiketleme süreci için bir etiketleme platformuna (Label Studio, Argilla) karar verilip kurulması. (Alternatif: JSON/Excel tabanlı form oluşturulması.)
- [ ] 13 -> Fine-Tuning veya RAG sisteminin başarısını ölçmek adına kurumun genel yapısını kapsayan "Altın Veri Seti" (Golden Dataset - örnek Soru-Cevap ikilileri) üretilmesi. (En az birkaç yüz iyi Q&A kombinasyonu.)
- [ ] 14 -> Metadata ve Niyet (Intent) sınıflandırmasına göre belge türü etiketlerinin (yönetmelik, duyuru, personel vb.) ve hedef kitle etiketlerinin (lisans, yüksek lisans, personel vb.) belirlenmesi.

### Otomasyon ve Sürdürülebilirlik
- [ ] 15 -> Scraper Python kodlarının (academic.py, inonu_ogrencidb_duyuru_scraper.py vb.) zamanlanmış görevlere (Cron Jobs) dönüştürülüp, yeni veri geldikçe Vektör DB'ye otomatik ekleyecek sürekli entegrasyon boru hattının (Pipeline) yazılması.
- [ ] 16 -> Süresi geçmiş veya güncellenen verilerin (eski duyurular, değişen akademik takvim vb.) Vektör DB'den otomatik silinmesi veya pasife alınması mekanizmasının kurulması.
- [ ] 17 -> Canlıya alındıktan sonra öğrencilerden gelen olumsuz geri dönüşleri loglayacak, doğruyu sisteme manuel etiketleyip öğretme imkânı sağlayacak RLHF (Reinforcement Learning from Human Feedback) mekanizmasının entegrasyonu.

---

## 🤖 BÖLÜM B: AI MÜHENDİSLİĞİ (Diğer Ekip Üyeleri)

### Model ve Pipeline
- [ ] 18 -> Cevap üretecek ana LLM'in (GPT-4, Gemini, Llama 3, Mistral vb.) seçilmesi. Maliyet, hız ve Türkçe performansına göre kıyaslama yapılması.
- [ ] 19 -> RAG Pipeline'ının tasarlanması: Soru → Vektör DB'den ilgili chunk'ları getir → Context olarak formatla → System Prompt + User Prompt → LLM'e gönder → Cevap üret.
- [ ] 20 -> Prompt mühendisliği: System prompt'un (İnönü AI'ın kimliği, kuralları, ton of voice) dikkatli bir şekilde yazılması.
- [ ] 21 -> Halüsinasyon (uydurma cevap) önleme mekanizmalarının kurulması. Modelin bilmediği konularda "Bu konuda kesin bilgim yok, Öğrenci İşleri'ne danışmanızı öneririm" demesinin sağlanması.
- [ ] 22 -> Çoklu tur konuşma yönetimi (Chat History): Öğrenci art arda soru sorduğunda önceki bağlamı hatırlayacak context window yönetiminin kodlanması.
- [ ] 23 -> Fallback mekanizması: AI cevap veremediğinde ilgili birimin telefon/e-posta bilgisiyle yönlendirme yapacak yapının oluşturulması.

### Test ve Kalite
- [ ] 24 -> Altın Veri Seti üzerinden sistematik test sürecinin yürütülmesi. Accuracy, Recall, Hallucination Rate gibi metriklerin ölçülmesi ve raporlanması.
- [ ] 25 -> Edge case'lerin (belirsiz sorular, çok genel sorular, kapsam dışı sorular) test edilip sonuçlarının değerlendirilmesi.

---

## 🖥️ BÖLÜM C: YAZILIM MÜHENDİSLİĞİ VE DEPLOYMENT (Diğer Ekip Üyeleri)

### Backend API
- [ ] 26 -> Frontend'in AI ile iletişim kuracağı REST API endpoint'lerinin (Spring Boot / FastAPI vb.) yazılması.
- [ ] 27 -> Kullanıcı kimlik doğrulama (Authentication) ve yetkilendirme (Authorization) sisteminin kurulması.
- [ ] 28 -> API rate limiting ve maliyet kontrol mekanizmalarının eklenmesi.

### Frontend
- [ ] 29 -> Öğrencilerin soru soracağı web/mobil chat arayüzünün tasarlanması ve geliştirilmesi.

### DevOps ve Sunucu
- [ ] 30 -> Docker containerization ile tüm servislerin (API, Vektör DB, LLM servisi) paketlenmesi.
- [ ] 31 -> CI/CD pipeline kurulumu ve production ortamına deploy edilmesi.
- [ ] 32 -> Monitoring ve observability: Sistem performansı, hata logları ve yanıt süresi takibi için izleme araçlarının (Grafana, Prometheus vb.) entegrasyonu.
