# İnönü Üniversitesi Akademik Veri Çekme Araçları

Bu proje, İnönü Üniversitesi panelinden akademik birim, personel ve görsel verilerini çekmek için oluşturulmuş Python betiklerini içerir.

## Gerekli Kurulumlar (Pip Komutları)

Projeyi çalıştırmak için Python'un standart kütüphanelerine ek olarak `requests` kütüphanesine ihtiyaç vardır. Kurmak için terminalinize (komut satırına) aşağıdaki komutu yazınız:

```bash
pip install requests
```

> **Not:** `json`, `urllib`, `time`, `os`, `glob`, `sys` gibi kütüphaneler Python ile birlikte standart olarak geldiği için ekstra kurulum gerektirmez.

## Kullanım Sırası ve Proje Akışı

Dosyalar birbirine veri akışı bağlamında bağımlı çalıştığı için (bir betiğin çıktısı diğerinin girdisi olabiliyor) belirli bir sırayla çalıştırılmalıdırlar.

### 1. Adım: Ana Verileri Çekmek
* **Çalıştırılacak Dosya:** `academic.py`
* **İşlevi:** API'ye istek atarak üniversitedeki tüm birimlerin ve bu birimlerdeki akademisyenlerin temel listesini JSON formatında çeker.
* **Çıktısı:** `academic.json` dosyası oluşturulur.

### 2. Adım: Bölüm ve Fakülte İlişkilerini Çözümlemek
* **Çalıştırılacak Dosya:** `faculty.py`
* **Gereksinim:** 1. adımda oluşturulan `academic.json` dosyasını kullanır.
* **İşlevi:** Sadece bölümleri ayıklar. Daha sonra her bölüm için tek tek API'ye istek atarak o bölümün bağlı olduğu fakülte ID'sini ve adını tespit eder. Sonuçları detaylı bir şekilde JSON dosyalarına kaydeder.
* **Çıktısı:** `bolumler.json` (ara dosya) ve `bolumler_ve_fakulteler.json` (nihai dosya)

#### Opsiyonel Adım: ID'leri Metin Olarak Kaydetmek
* **Çalıştırılacak Dosya:** `bolum_id_script.py`
* **Gereksinim:** `academic.json` dosyasını kullanır.
* **İşlevi:** JSON dosyasındaki verileri daha okunabilir bir metin formatına dönüştürür.
* **Çıktısı:** `bolumler.txt`

### 3. Adım: Personel Verilerini Detaylandırma ve Görselleri İndirme

Projede görsel indirme ve personel bilgilerini listeleme için iki farklı yaklaşım scripti bulunmaktadır:

**Seçenek A (Sadece Akademisyen Görselleri):**
* **Çalıştırılacak Dosya:** `academic_image.py`
* **Gereksinim:** 1. adımdaki `academic.json` dosyasını kullanır.
* **İşlevi:** Doğrudan akademisyenlerin fotoğraflarını tespit eder. Olası tüm uzantıları (jpg, jpeg, png) büyük/küçük harf duyarlı olarak deneyerek indirmeye çalışır.
* **Çıktısı:** İndirilen görseller `akademisyen_gorseller/` klasörüne kaydedilir.

**Seçenek B (Tüm Personeller, Detayları ve Görselleri):**
* **Çalıştırılacak Dosya:** `personel_image.py`
* **Gereksinim:** 2. adımdaki `bolumler_ve_fakulteler.json` dosyasını kullanır.
* **İşlevi:** Birim URL'lerini alır, API'den o birime ait tüm personellerin (sadece akademisyen değil) detaylı bilgilerini çeker. Ardından tüm bu personellerin güncel isimlerini ve bilgilerini bir JSON'a kaydeder, profillerindeki `_SP` (veya varsayılan) boyutundaki fotoğraflarını indirir.
* **Çıktısı:** `tum_personeller.json` dosyası ve indirilen görseller `personel_gorseller/` klasörüne kaydedilir.

## Özet Kullanım Tablosu

| Sıra | Dosya Adı | Gerekli Okunacak Dosya | Ürettiği Dosya / Klasör |
| :---: | :--- | :--- | :--- |
| **1.** | `academic.py` | *(Yok)* | `academic.json` |
| **2.** | `faculty.py` | `academic.json` | `bolumler.json`, `bolumler_ve_fakulteler.json` |
| **3.** | `academic_image.py` | `academic.json` | `akademisyen_gorseller/` klasörü |
| **4.** | `personel_image.py` | `bolumler_ve_fakulteler.json` | `tum_personeller.json`, `personel_gorseller/` klasörü |
