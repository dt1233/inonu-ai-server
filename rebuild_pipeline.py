import json
import re
import asyncio
from pathlib import Path

# --- CORE LOGIC (SINGLE RESPONSIBILITY) ---

class TurkishNormalizer:
    """Türkçe karakterleri güvenli bir şekilde büyük harfe ve standart forma çeviren sınıf."""
    @staticmethod
    def normalize(text: str) -> str:
        if not text:
            return ""
        # 1. Unvanları temizle
        text = re.sub(r"(Prof\.?|Doç\.?|Dr\.?|Öğr\.?|Gör\.?|Üyesi)\s*", "", text, flags=re.IGNORECASE)
        # 2. Fazla boşlukları temizle
        text = re.sub(r"\s+", " ", text).strip()
        # 3. Türkçe karakter dönüşümleri
        char_map = {
            'ı': 'I', 'i': 'İ', 'ş': 'Ş', 'ğ': 'Ğ', 'ü': 'Ü', 'ö': 'Ö', 'ç': 'Ç',
            'I': 'I', 'İ': 'İ', 'Ş': 'Ş', 'Ğ': 'Ğ', 'Ü': 'Ü', 'Ö': 'Ö', 'Ç': 'Ç'
        }
        upper_chars = []
        for char in text:
            if char in char_map:
                upper_chars.append(char_map[char])
            else:
                upper_chars.append(char.upper())
        
        # Sonuç olarak tamamen büyük harfli, unvansız, temiz bir string döner
        # Eşleşme kolaylığı için I/İ ayrımını tamamen yoksaymak adına her ikisini de I'ya çeviriyoruz.
        # Böylece "ALİ" ile "ALI" aynı (AL I -> ALI) olur.
        normalized = "".join(upper_chars)
        normalized = normalized.replace("İ", "I").replace("Ü", "U").replace("Ö", "O").replace("Ş", "S").replace("Ç", "C").replace("Ğ", "G")
        return normalized

class Matcher:
    """İki ismin aynı kişiye ait olup olmadığını kontrol eder."""
    @staticmethod
    def is_match(name1: str, name2: str) -> bool:
        norm1 = TurkishNormalizer.normalize(name1)
        norm2 = TurkishNormalizer.normalize(name2)
        if not norm1 or not norm2:
            return False
        # Bir isim diğerini içeriyorsa veya tam eşleşiyorsa (örneğin göbek adı eksikliği durumu)
        return norm1 in norm2 or norm2 in norm1

class RoleDataSource:
    """Farklı kaynaklardan idari görevleri toplayan soyut sınıf (Open/Closed Prensibi)"""
    def get_roles(self) -> dict:
        raise NotImplementedError

class JSONFileRoleDataSource(RoleDataSource):
    """Bölüm başkanları ve dekanlar gibi önceden çekilmiş JSON dosyalarından rolleri okur."""
    def __init__(self, file_path: str, role_key: str, name_key: str, default_role_suffix: str = ""):
        self.file_path = Path(file_path)
        self.role_key = role_key # Hangi alanı okuyacağımız (örn: "bolum")
        self.name_key = name_key # Hangi alanı isim olarak alacağımız (örn: "bolum_baskani")
        self.default_role_suffix = default_role_suffix # Örn: " Bölüm Başkanı"

    def get_roles(self) -> dict:
        roles = {}
        if not self.file_path.exists():
            return roles
        
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data:
                    name = item.get(self.name_key)
                    if name and name.strip() and name != "Bulunamadı":
                        unit = item.get(self.role_key, "").strip()
                        role_title = f"{unit} {self.default_role_suffix}".strip()
                        roles[name] = role_title
        except Exception as e:
            print(f"Hata ({self.file_path}): {e}")
        return roles

class AvesisUpdater:
    """Avesis dosyasındaki hocaların profillerini günceller."""
    def __init__(self, avesis_path: str):
        self.avesis_path = Path(avesis_path)
    
    def update_roles(self, roles_dict: dict) -> int:
        if not self.avesis_path.exists():
            print("avesis_results.json bulunamadı.")
            return 0
            
        with open(self.avesis_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        updated_count = 0
        if data and isinstance(data, list):
            for staff in data[0].get('content', []):
                avesis_name = staff.get('ad_soyad', '')
                # Hocanın adını tüm rollerle karşılaştır
                for role_name, role_title in roles_dict.items():
                    if Matcher.is_match(avesis_name, role_name):
                        # Mevcut idari görevini ez veya birleştir
                        current_role = staff.get('idari_gorev', '')
                        if current_role and role_title not in current_role:
                            staff['idari_gorev'] = f"{role_title}, {current_role}"
                        else:
                            staff['idari_gorev'] = role_title
                        updated_count += 1
                        break # Aynı hoca birden fazla kez bulunursa ilkini alır
                        
        with open(self.avesis_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        return updated_count

class CrawlResultsUpdater:
    """Crawl_results dosyasındaki avesis_staff kısmını günceller ve yönetim rehberini ekler."""
    
    @staticmethod
    def _format_yonetim_rehberi(data: dict) -> str:
        lines = []
        lines.append("# İnönü Üniversitesi Yönetim ve İdari Personel Rehberi\n")
        
        for fak in data.get("fakulteler", []):
            lines.append(f"## {fak.get('fakulte_adi', '')}")
            if fak.get("dekan"):
                lines.append(f"**Dekan:** {fak['dekan']}")
            if fak.get("bolumler"):
                lines.append("\n### Bölüm Başkanları")
                for b in fak["bolumler"]:
                    lines.append(f"- {b.get('bolum_adi')}: {b.get('bolum_baskani') or 'Belirtilmemiş'}")
            if fak.get("idari_personel"):
                lines.append("\n### İdari Personel")
                for p in fak["idari_personel"]:
                    unvan = p.get('unvan', '')
                    gorev = p.get('gorev', '')
                    lines.append(f"- {p.get('ad_soyad')} ({unvan}) - {gorev} | Tel: {p.get('telefon', '')}")
            lines.append("\n---\n")
            
        for birim in data.get("diger_idari_birimler", []):
            lines.append(f"## {birim.get('birim_adi', '')}")
            for p in birim.get("personel", []):
                unvan = p.get('unvan', '')
                gorev = p.get('gorev', '')
                lines.append(f"- {p.get('ad_soyad')} ({unvan}) - {gorev} | Tel: {p.get('telefon', '')}")
            lines.append("\n---\n")
            
        return "\n".join(lines)

    @staticmethod
    def sync(avesis_path: str, crawl_path: str):
        if not Path(crawl_path).exists():
            print("Senkronizasyon için crawl_results.json bulunamadı.")
            return
            
        with open(crawl_path, "r", encoding="utf-8") as f:
            crawl_data = json.load(f)
            
        # 1. Avesis Staff İdari Görev Senkronizasyonu
        if Path(avesis_path).exists():
            with open(avesis_path, "r", encoding="utf-8") as f:
                avesis_data = json.load(f)
                
            if avesis_data and isinstance(avesis_data, list):
                updated_staff = avesis_data[0].get('content', [])
                for unit in crawl_data.get('avesis_staff', []):
                    for p in unit.get('content', []):
                        avesis_id = p.get('avesis_id')
                        for u_staff in updated_staff:
                            if u_staff.get('avesis_id') == avesis_id:
                                p['idari_gorev'] = u_staff.get('idari_gorev', '')
                                break
        else:
            print("avesis_results.json bulunamadı, idari görev eşleşmesi atlanıyor.")

        # 2. Yönetim ve İdari Personel Rehberinin Eklenmesi
        yonetim_path = "data/inonu_universitesi_yonetim_rehberi.json"
        if Path(yonetim_path).exists():
            with open(yonetim_path, "r", encoding="utf-8") as f:
                yonetim_data = json.load(f)
            
            markdown_content = CrawlResultsUpdater._format_yonetim_rehberi(yonetim_data)
            
            static_contents = crawl_data.get('static_contents', [])
            # Eski kaydı temizle
            static_contents = [sc for sc in static_contents if sc.get('key') != 'yonetim_rehberi']
            
            # Yeni kaydı ekle
            static_contents.append({
                "key": "yonetim_rehberi",
                "label": "İnönü Üniversitesi Yönetim ve İdari Personel Rehberi",
                "url": "local://data/inonu_universitesi_yonetim_rehberi.json",
                "fetchedAt": "2026-06-22T00:00:00Z",
                "content": markdown_content,
                "pdfLinks": [],
                "extra": {"fakulte": "Genel Yönetim", "type": "markdown"},
                "error": None
            })
            crawl_data['static_contents'] = static_contents
            print(f"Yönetim Rehberi (Markdown Formatı) başarıyla crawl_results içerisine entegre edildi.")
        else:
            print(f"{yonetim_path} bulunamadı, yönetim rehberi atlanıyor.")
                            
        with open(crawl_path, "w", encoding="utf-8") as f:
            json.dump(crawl_data, f, ensure_ascii=False, indent=2)

class PipelineOrchestrator:
    """Tüm süreci yöneten ana sınıf (Facade Pattern)."""
    def __init__(self):
        self.roles = {}
    
    def gather_roles(self):
        print("1. İdari Görevler Toplanıyor...")
        sources = [
            JSONFileRoleDataSource("data/final_bolum_baskanlari.json", "bolum", "bolum_baskani", "Bölüm Başkanı"),
            JSONFileRoleDataSource("data/final_dekanlar.json", "fakulte", "dekan", "Dekanı")
            # Not: admin_crawler.py doğrudan avesis'e yazıyorsa onu import edip çalıştırabiliriz.
            # Şu an için JSON'ları birleştiriyoruz. Rektör ve Yrd. için aktif_yonetim.json'dan da beslenebiliriz.
        ]
        
        # Aktif yönetim verisini ekle
        aktif_path = Path("data/aktif_yonetim.json")
        if aktif_path.exists():
            try:
                with open(aktif_path, "r", encoding="utf-8") as f:
                    aktif = json.load(f)
                    yonetim = aktif.get("yonetim", {})
                    rek = yonetim.get("rektor", {}).get("unvan_ad_soyad")
                    if rek: self.roles[rek] = "Rektör"
                    for r in yonetim.get("rektor_yardimcilari", []):
                        if r.get("unvan_ad_soyad"):
                            self.roles[r["unvan_ad_soyad"]] = "Rektör Yardımcısı"
            except Exception as e:
                print(f"Aktif yönetim okuma hatası: {e}")

        for source in sources:
            self.roles.update(source.get_roles())
            
        print(f"Toplam {len(self.roles)} benzersiz idari görev tespit edildi.")
        
    def update_databases(self):
        print("2. Avesis Veritabanı Güncelleniyor...")
        updater = AvesisUpdater("data/avesis_results.json")
        count = updater.update_roles(self.roles)
        print(f"Avesis'te {count} hocanın idari görevi başarıyla güncellendi.")
        
        print("3. Crawl Results Senkronize Ediliyor...")
        CrawlResultsUpdater.sync("data/avesis_results.json", "data/crawl_results.json")
        print("Crawl results senkronizasyonu tamamlandı.")
        
    def rebuild_chunks(self):
        import subprocess
        import sys
        print("4. Vektör Veritabanı (Chunks) Yeniden Oluşturuluyor...")
        try:
            # run_chunker.py'ı alt süreç (subprocess) olarak çalıştır
            result = subprocess.run([sys.executable, "run_chunker.py"], capture_output=True, text=True, check=True)
            print("Chunk oluşturma işlemi başarıyla tamamlandı.")
            # Çıktının son 3 satırını yazdırarak kullanıcıya özet göster
            print("\n".join(result.stdout.strip().split("\n")[-3:]))
        except subprocess.CalledProcessError as e:
            print("Chunk oluşturulurken hata meydana geldi!")
            print(e.stderr)

    def run_all(self):
        self.gather_roles()
        self.update_databases()
        self.rebuild_chunks()
        print("\n=== TÜM VERİ HATTI BAŞARIYLA YENİLENDİ ===")

if __name__ == "__main__":
    orchestrator = PipelineOrchestrator()
    orchestrator.run_all()
