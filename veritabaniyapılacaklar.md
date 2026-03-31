# İnönü AI - NoSQL ve Chunking (Veri Parçalama) Uygulama Planı

Bu belge, üniversitenin tüm verilerinin (Duyurular, Statik İçerikler, Akademik Birimler, Personel vb.) MongoDB (NoSQL) veritabanına nasıl aktarılacağını ve RAG sistemi için en kritik aşama olan **Chunking (Anlamsal Parçalama)** işleminin kurallarını belirler.

## 📌 Dikkat Edilmesi Gerekenler ve Mimari Kararlar

Ekibin (Biloom2) de belirttiği üzere, **RAG (Yapay Zeka Destekli Arama) sisteminin cevap kalitesi, doğrudan Chunk (Parça) kalitesine bağlıdır.**
Basit karakter sayısına göre (örn: her 500 harfte bir kes) bölme işlemi, kelimeleri ve cümleleri ortadan böleceği için yapay zekanın bağlamı kaybetmesine sebep olur.

Bu nedenle, veritabanı mimarimizi **3 Katmanlı (3-Layered)** bir yapıya oturtacağız:
1. **Ham Veri Katmanı (Raw Layer):** Scraper'lardan gelen orijinal `.json` kaynaklarının tutulduğu yedek/arşiv katmanı.
2. **Temizlenmiş Katman (Processed Layer):** HTML etiketlerinden arındırılmış, gereksiz boşlukları silinmiş saf metin (Markdown/TXT) hali.
3. **Chunk Katmanı (AI/Vektör Katmanı):** Yapay zekaya yedirilecek olan, anlam bütünlüğü korunarak (`\n\n` paragraf boşluklarına veya nokta `.` ile biten cümle sınırlarına göre) mantıklı, küçük parçalara (Chunk) bölünmüş nihai katman.

### 📝 Örnek "Anlamsal Chunking" Yaklaşımı
*(Biloom2'nin tavsiyesine istinaden)*

**Orijinal Metin:**
*"Öğrenci işleri birimi kayıt yenileme, mezuniyet, burs, disiplin ve yatay geçiş işlemlerini yürütmektedir. Kayıt yenileme işlemleri her yarıyıl başında yapılır. Öğrenciler belirlenen tarihler arasında harçlarını yatırıp sisteme giriş yapmalıdır. Mezuniyet başvuruları son sınıf öğrencileri tarafından Mayıs ayında yapılır. Burs başvuruları ise Ekim ayında alınmaktadır..."*

**❌ Kötü Chunking (Karakter sayısına göre kesme):**
- *Chunk 1:* "Öğrenci işleri birimi kayıt yenileme, mezuniyet, burs, disiplin ve yatay geçiş işlemlerini yürütmektedir. Kayıt yenileme işlemleri her yarıyıl başında yapıl..." (Cümle yarım kaldı, AI anlayamaz).

**✅ İyi Chunking (Anlamsal / Cümle bazlı kesme):**
- *Chunk 1:* "Kayıt yenileme işlemleri her yarıyıl başında yapılır. Öğrenciler belirlenen tarihler arasında harçlarını yatırıp sisteme giriş yapmalıdır."
- *Chunk 2:* "Mezuniyet başvuruları son sınıf öğrencileri tarafından Mayıs ayında yapılır."
- *Chunk 3:* "Burs başvuruları Ekim ayında alınmaktadır."

---

## 🛠️ Uygulanacak Değişiklikler (Teknik Yol Haritası)

### 1. Merkezi Veritabanı Yöneticisi (`db_manager.py`)
Mevcut tüm scraper scriptlerinin (statik içerikler, duyurular, akademik personeller vb.) kopyala-yapıştır kod kullanmaması için `scrapping/db_manager.py` adında ana bir modül yazılacak. Bu dosya şu işlevlere sahip olacak:
- `MongoDB` bağlantısını asenkron/senkron yönetecek.
- **Upsert (Ekle/Güncelle) Mantığı:** Gelen belgenin ID'si "inonu_ai" veritabanında varsa o kaydı güncelleyecek, yoksa yeni kayıt olarak ekleyecek (Böylece `.json` verilerinin birden fazla kez çekilmesi durumunda veritabanı çöpe dönmeyecek).
- `chunkify()` fonksiyonunu barındıracak. Metinler önce bu fonksiyondan geçip anlamsal (paragraf/cümle) olarak parçalanacak.

### 2. MongoDB Koleksiyonları (Collections)
Bağlantı URL'miz `mongodb://localhost:27017` olacak ve `inonu_ai` veritabanı (DB) altında aşağıdaki tablolar (koleksiyonlar) yer alacak:
- `announcements` -> Öğrenci duyuruları ve PDF metinleri
- `static_contents` -> SSS, Tarihçe, bölüm sayfaları vb.
- `academic_units` -> Fakülte-Bölüm hiyerarşisi
- `personnel_details` -> Tüm üniversite personelinin unvan, iletişim ve (istenirse) görsel yollarıyla (path) birlikte bilgileri.
- `chunks` -> Chunkify ile parçalanmış ve yapay zekanın "Vektör Veritabanı" (Chroma/pgvector) seviyesine atılmadan önce tutulacak ana metin blokları. *(Her chunk, hangi URL'den (kaynaktan) geldiğini belirten bir Metadata içerecek).*

### 3. Mevcut Scraper'ların Güncellenmesi
- `statik_icerikler (1).py`
- `inonu_ogrencidb_duyuru_scraper.py`
- `personel/academic.py`, `faculty.py`, `personel_image.py`

*(Tüm bu dosyalar çalıştıkları anda elde ettikleri sonucu kendi lokal `.json` dosyalarına yazmanın yanı sıra doğrudan `db_manager.py` üzerinden MongoDB'ye gönderecek şekilde revize edilecek.)*
