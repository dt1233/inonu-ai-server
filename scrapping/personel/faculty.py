import json
import requests
import time
from pathlib import Path
import sys

# ── MongoDB entegrasyonu ──────────────────────────────────────────
try:
    _PARENT = Path(__file__).resolve().parent.parent  # scrapping/
    sys.path.insert(0, str(_PARENT))
    from db_manager import DBManager, COL_ACADEMIC_UNITS
    _MONGO_ENABLED = True
except ImportError:
    _MONGO_ENABLED = False

class C:
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'
    WHITE = '\033[97m'
    DIM = '\033[2m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'

def banner() -> None:
    lines = [
        "",
        f"{C.CYAN}{C.BOLD}  ╔══════════════════════════════════════════════════════════════════╗{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║    {C.WHITE}██╗███╗   ██╗ ██████╗ ███╗   ██╗██╗   ██╗{C.CYAN}          ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║    {C.WHITE}██║████╗  ██║██╔═══██╗████╗  ██║██║   ██║{C.CYAN}          ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║    {C.WHITE}██║██╔██╗ ██║██║   ██║██╔██╗ ██║██║   ██║{C.CYAN}          ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║    {C.WHITE}██║██║╚██╗██║██║   ██║██║╚██╗██║██║   ██║{C.CYAN}          ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║    {C.WHITE}██║██║ ╚████║╚██████╔╝██║ ╚████║╚██████╔╝{C.CYAN}          ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║      {C.DIM}╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═══╝ ╚═════╝{C.CYAN}           ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║                                                                        ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║    {C.YELLOW}mert ege sungur {C.GREEN}meges.com.tr{C.CYAN}             ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║                {C.DIM}İnönü Üniversitesi {C.CYAN}          ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ╚══════════════════════════════════════════════════════════════════╝{C.RESET}",
        "",
    ]
    for line in lines:
        print(line)

# --- ADIM 1: academic.json'dan id, ad ve url çekip yeni bir json oluşturma ---
def bolumleri_ayikla(girdi_dosyasi, ara_cikti_dosyasi):
    with open(girdi_dosyasi, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    ayiklanan_veriler = []
    
    for item in data:
        bolum_id = item.get('id')
        bolum_adi = item.get('unitName')
        url = item.get('url')
        
        # Sadece URL bilgisi olanları listeye ekliyoruz (istek atabilmek için)
        if url: 
            ayiklanan_veriler.append({
                "bolum_id": bolum_id,
                "bolum_adi": bolum_adi,
                "url": url
            })
            
    # Ayıklanan verileri yeni bir JSON dosyasına kaydet
    with open(ara_cikti_dosyasi, 'w', encoding='utf-8') as f:
        json.dump(ayiklanan_veriler, f, ensure_ascii=False, indent=4)
        
    print(f"--- 1. ADIM TAMAMLANDI ---")
    print(f"Toplam {len(ayiklanan_veriler)} bölüm '{ara_cikti_dosyasi}' adlı dosyaya JSON formatında kaydedildi.\n")
    return ayiklanan_veriler

# --- ADIM 2: Oluşan JSON'dan faydalanarak fakülte ID'lerini tespit etme ---
def fakulte_id_tespit_et(ara_girdi_dosyasi, nihai_cikti_dosyasi):
    # 1. adımda oluşturduğumuz JSON'u okuyoruz
    with open(ara_girdi_dosyasi, 'r', encoding='utf-8') as f:
        bolumler = json.load(f)
        
    print("--- 2. ADIM BAŞLIYOR ---")
    print("Fakülte ID'leri API üzerinden çekiliyor. Lütfen bekleyin...\n")
    
    nihai_sonuclar = []
    
    for bolum in bolumler:
        url = bolum['url']
        api_url = f"https://panel.inonu.edu.tr/servlet/unit?type=breadcrumb&unit={url}"
        
        try:
            # API'ye istek at
            response = requests.get(api_url, timeout=10)
            if response.status_code == 200:
                breadcrumb_data = response.json()
                
                fakulte_id = None
                fakulte_adi = "Bulunamadı"
                
                # Gelen veride en az 2 eleman varsa (Bölüm -> Fakülte hiyerarşisi)
                if len(breadcrumb_data) > 1:
                    fakulte_bilgisi = breadcrumb_data[1]  # Genellikle 2. eleman fakültedir
                    fakulte_id = fakulte_bilgisi.get('id')
                    
                    # Translate içinden Türkçe adını çekme
                    translate_str = fakulte_bilgisi.get('translate', '{}')
                    try:
                        translate_json = json.loads(translate_str)
                        fakulte_adi = translate_json.get('tr', translate_str)
                    except json.JSONDecodeError:
                        fakulte_adi = translate_str
                        
                print(f"Bölüm: {bolum['bolum_adi']} -> Fakülte: {fakulte_adi} (Fakülte ID: {fakulte_id})")
                
                # Bölüm bilgilerine fakülte bilgilerini de ekliyoruz
                bolum['fakulte_id'] = fakulte_id
                bolum['fakulte_adi'] = fakulte_adi
                nihai_sonuclar.append(bolum)
                
            else:
                print(f"Hata: {url} için istek başarısız oldu. (Durum Kodu: {response.status_code})")
                
        except Exception as e:
            print(f"Hata ({url}): İstek atılırken sorun oluştu -> {e}")
            
        # Çok hızlı istek atıp sunucu tarafından engellenmemek için yarım saniye bekliyoruz
        time.sleep(0.5)
        
    # Tüm sonuçları en son JSON dosyasına kaydet
    with open(nihai_cikti_dosyasi, 'w', encoding='utf-8') as f:
        json.dump(nihai_sonuclar, f, ensure_ascii=False, indent=4)
        
    print(f"\n--- İŞLEM TAMAMLANDI ---")
    print(f"Fakülte ID'lerini içeren nihai veriler '{nihai_cikti_dosyasi}' dosyasına başarıyla kaydedildi.")

    # ── MongoDB'ye yaz ──────────────────────────────────────────
    if _MONGO_ENABLED:
        _save_faculty_to_mongo(nihai_sonuclar)
    else:
        print("[!] db_manager bulunamadı, MongoDB'ye yazma atlandı.")


def _save_faculty_to_mongo(bolumler: list) -> None:
    """
    Fakülte-bölüm hiyerarşisini academic_units koleksiyonuna upsert eder.
    Fakülte ikilisi (bolum_id + fakulte_id) birer belge olarak yazılır.
    """
    try:
        with DBManager() as db_mgr:
            ins = upd = 0
            for bolum in bolumler:
                doc = {
                    "id":          bolum.get("bolum_id"),
                    "unit_name":   bolum.get("bolum_adi", ""),
                    "url":         bolum.get("url", ""),
                    "fakulte_id":  bolum.get("fakulte_id"),
                    "fakulte_adi": bolum.get("fakulte_adi", ""),
                    "kaynak":      "faculty",
                }
                status = db_mgr.upsert(COL_ACADEMIC_UNITS, doc, id_field="id")
                if status == "inserted": ins += 1
                else: upd += 1
            print(f"  [MongoDB] Akademik birimler: {ins} yeni / {upd} güncellendi")
    except Exception as e:
        print(f"  [!] MongoDB yazma hatası (JSON kaydı etkilenmedi): {e}")

# Script doğrudan çalıştırıldığında bu kısım tetiklenir
if __name__ == "__main__":
    banner()
    # Dosya isimlerini belirliyoruz
    ana_veri_dosyasi = 'academic.json'
    ara_json_dosyasi = 'bolumler.json'
    nihai_json_dosyasi = 'bolumler_ve_fakulteler.json'
    
    # 1. Adımı çalıştır
    bolumleri_ayikla(ana_veri_dosyasi, ara_json_dosyasi)
    
    # 2. Adımı çalıştır
    fakulte_id_tespit_et(ara_json_dosyasi, nihai_json_dosyasi)