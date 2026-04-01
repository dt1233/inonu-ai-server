import os
import json
import requests
import time
import glob
import urllib3
import sys
from pathlib import Path

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── MongoDB entegrasyonu ──────────────────────────────────────────
try:
    _PARENT = Path(__file__).resolve().parent.parent  # scrapping/
    sys.path.insert(0, str(_PARENT))
    from db_manager import DBManager, COL_PERSONNEL
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

# Ayarlar
GIRDI_DOSYASI = "bolumler_ve_fakulteler.json"
PERSONEL_JSON_DOSYASI = "tum_personeller.json"
GÖRSEL_KLASORU = "personel_gorseller"

def personelleri_cek():
    # 1. bolumler_ve_fakulteler.json dosyasını oku ve URL'leri al
    try:
        with open(GIRDI_DOSYASI, 'r', encoding='utf-8') as f:
            bolumler = json.load(f)
    except FileNotFoundError:
        print(f"Hata: '{GIRDI_DOSYASI}' dosyası bulunamadı!")
        return None

    benzersiz_urller = set()
    for bolum in bolumler:
        url = bolum.get('url')
        if url:
            benzersiz_urller.add(url)

    print(f"Toplam {len(benzersiz_urller)} farklı birim/fakülte URL'si bulundu.")
    print("API'den personeller çekiliyor. Lütfen bekleyin...\n")

    tum_personeller = {} # Aynı personeli tekrar eklememek için sözlük kullanıyoruz

    for url in benzersiz_urller:
        api_url = f"https://panel.inonu.edu.tr/servlet/staff?unit={url}"
        try:
            response = requests.get(api_url, timeout=10, verify=False)
            if response.status_code == 200:
                personel_listesi = response.json()
                
                # Gelen veri bir liste ise içindeki personelleri döngüye al
                if isinstance(personel_listesi, list):
                    for kisi in personel_listesi:
                        staff_info = kisi.get('staff', {})
                        kisi_id = staff_info.get('id')
                        
                        if kisi_id and kisi_id not in tum_personeller:
                            tum_personeller[kisi_id] = kisi
                            
        except Exception as e:
            print(f"Hata ({url} adresine ulaşılamadı): {e}")
            
        time.sleep(0.2) # Sunucuyu yormamak için kısa bir bekleme

    # Sözlükteki değerleri listeye çevir
    kaydedilecek_liste = list(tum_personeller.values())
    
    with open(PERSONEL_JSON_DOSYASI, 'w', encoding='utf-8') as f:
        json.dump(kaydedilecek_liste, f, ensure_ascii=False, indent=4)
        
    print(f"\n--- 1. AŞAMA TAMAMLANDI ---")
    print(f"Toplam {len(kaydedilecek_liste)} benzersiz personel bulundu ve kaydedildi.\n")
    return kaydedilecek_liste

def gorselleri_indir(personeller):
    if not os.path.exists(GÖRSEL_KLASORU):
        os.makedirs(GÖRSEL_KLASORU)
        print(f"'{GÖRSEL_KLASORU}' klasörü oluşturuldu.")

    print("--- 2. AŞAMA: GÖRSELLER İNDİRİLİYOR ---\n")

    basarili = 0
    hatali = 0
    atlanan = 0

    for kisi in personeller:
        image_info = kisi.get('image')
        staff_info = kisi.get('staff')

        # Kişinin fotoğraf bilgisi veya temel bilgileri yoksa atla
        if not image_info or not staff_info:
            continue

        file_path = image_info.get('filePath')
        file_name = image_info.get('fileName')
        json_uzanti = image_info.get('fileExtension', '').strip()
        
        # YENİ EKLENEN KISIM: Boyut ekini JSON'dan dinamik alıyoruz (Örn: "SP")
        # Eğer dizide bir şey yoksa varsayılan olarak "SP" kullanıyoruz
        image_sizes = image_info.get('imageSizes', [])
        boyut_eki = image_sizes[0] if image_sizes else "SP"

        kisi_id = staff_info.get('id', 'Yok')
        isim = staff_info.get('name', '').strip()
        soyisim = staff_info.get('surName', '').strip()
        full_name = f"{isim} {soyisim}".strip()

        if not file_path or not file_name:
            continue

        # Klasör ismi için geçersiz karakterleri temizle
        guvenli_isim = "".join([c for c in full_name if c.isalnum() or c == ' ']).strip()
        
        # Daha önce indirilmiş mi diye kontrol et (Kaldığı yerden devam etme)
        mevcut_aramasi = f"{guvenli_isim}_{kisi_id}.*"
        eslesen = glob.glob(os.path.join(GÖRSEL_KLASORU, mevcut_aramasi))

        if eslesen:
            print(f"Zaten mevcut (Atlanıyor): {os.path.basename(eslesen[0])}")
            atlanan += 1
            continue

        # Uzantı Kombinasyonları (Büyük/Küçük harf duyarlılığı sorunu için)
        ham_uzantilar = []
        if json_uzanti:
            ham_uzantilar.extend([json_uzanti, json_uzanti.lower(), json_uzanti.upper()])
        ham_uzantilar.extend(['jpg', 'JPG', 'jpeg', 'JPEG', 'png', 'PNG'])

        # Tekrarlayan uzantıları temizle
        denenecek_uzantilar = []
        for uzanti in ham_uzantilar:
            if uzanti not in denenecek_uzantilar:
                denenecek_uzantilar.append(uzanti)

        indirildi_mi = False

        for uzanti in denenecek_uzantilar:
            # DÜZELTİLEN URL YAPISI: _SP eklentisi kullanılıyor
            img_url = f"https://panel.inonu.edu.tr/servlet/image/{file_path}/{file_name}_{boyut_eki}.{uzanti}"
            kaydedilecek_isim = f"{guvenli_isim}_{kisi_id}.{uzanti}"
            kayit_yolu = os.path.join(GÖRSEL_KLASORU, kaydedilecek_isim)

            try:
                response = requests.get(img_url, timeout=10, verify=False)
                
                # Başarılı dönüş 200 ise ve gerçekten bir resimse indir
                if response.status_code == 200 and 'image' in response.headers.get('Content-Type', '').lower():
                    with open(kayit_yolu, 'wb') as img_file:
                        img_file.write(response.content)
                    print(f"İndirildi: {kaydedilecek_isim}")
                    basarili += 1
                    indirildi_mi = True
                    break # Bulduğu an döngüden çık
            except:
                pass 
            
            time.sleep(0.1)

        if not indirildi_mi:
            print(f"Hata: '{full_name}' ({kisi_id}) için resim sunucuda bulunamadı.")
            hatali += 1

    print(f"\n--- TÜM İŞLEMLER TAMAMLANDI ---")
    print(f"Yeni İndirilen: {basarili}")
    print(f"Zaten Var Olan (Atlanan): {atlanan}")
    print(f"Hatalı/Resmi Olmayan: {hatali}")

if __name__ == "__main__":
    banner()
    # 1. API'den verileri topla
    personel_verileri = personelleri_cek()
    
    # 2. Toplanan verilerle görselleri indir
    if personel_verileri:
        gorselleri_indir(personel_verileri)