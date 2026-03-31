import os
import json
import requests
import time
import glob

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

KLASOR_ADI = "akademisyen_gorseller"
JSON_DOSYASI = "academic.json"

def main():
    # Klasör yoksa oluştur
    if not os.path.exists(KLASOR_ADI):
        os.makedirs(KLASOR_ADI)
        print(f"'{KLASOR_ADI}' klasörü oluşturuldu.")

    # JSON dosyasını oku
    try:
        with open(JSON_DOSYASI, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Hata: '{JSON_DOSYASI}' dosyası bulunamadı.")
        return

    basarili_indirme = 0
    hatali_indirme = 0
    atlanan = 0

    print("İndirme işlemi başlıyor. Lütfen bekleyin...\n")

    for bolum in data:
        akademisyenler = bolum.get('academicians', [])
        
        if not akademisyenler:
            continue
        
        for akademisyen in akademisyenler:
            file_path = akademisyen.get('filePath')
            file_name = akademisyen.get('fileName')
            full_name = akademisyen.get('fullName', 'Isimsiz_Akademisyen')
            akademisyen_id = akademisyen.get('id', 'Yok')
            
            # JSON'dan uzantıyı al (Orijinal halini koruyoruz, küçük harfe ÇEVİRMİYORUZ)
            json_uzanti = akademisyen.get('fileExtension', '').strip()

            if not file_path or not file_name:
                continue

            # İşletim sistemi için dosya ismindeki geçersiz karakterleri temizle
            guvenli_isim = "".join([c for c in full_name if c.isalnum() or c == ' ']).strip()
            
            # --- 1. ADIM: ZATEN İNDİRİLMİŞ Mİ KONTROLÜ ---
            # Uzantısı ne olursa olsun, bu isim ve ID'ye sahip dosya var mı bak
            mevcut_dosya_aramasi = f"{guvenli_isim}_{akademisyen_id}.*"
            eslesen_dosyalar = glob.glob(os.path.join(KLASOR_ADI, mevcut_dosya_aramasi))

            if eslesen_dosyalar:
                print(f"Zaten mevcut (Atlanıyor): {os.path.basename(eslesen_dosyalar[0])}")
                atlanan += 1
                continue

            # --- 2. ADIM: OLASI TÜM UZANTILARI (BÜYÜK/KÜÇÜK) DENEME ---
            # Denenecek uzantıların ham listesi
            ham_uzantilar = []
            
            # Önce JSON'da gelen uzantının kendisini, sonra küçük ve büyük harfli halini ekle
            if json_uzanti:
                ham_uzantilar.extend([json_uzanti, json_uzanti.lower(), json_uzanti.upper()])
                
            # Ardından standart uzantıların hem küçük hem büyük harfli versiyonlarını ekle
            ham_uzantilar.extend(['jpg', 'JPG', 'jpeg', 'JPEG', 'png', 'PNG'])

            # Listeyi tekrarlardan arındır ama sırayı bozma (Önce en mantıklılar denensin)
            denenecek_uzantilar = []
            for uzanti in ham_uzantilar:
                if uzanti not in denenecek_uzantilar:
                    denenecek_uzantilar.append(uzanti)

            indirildi_mi = False

            for uzanti in denenecek_uzantilar:
                img_url = f"https://panel.inonu.edu.tr/servlet/image/{file_path}/{file_name}_225x300.{uzanti}"
                kaydedilecek_isim = f"{guvenli_isim}_{akademisyen_id}.{uzanti}"
                kayit_yolu = os.path.join(KLASOR_ADI, kaydedilecek_isim)

                try:
                    response = requests.get(img_url, timeout=10)
                    
                    # Eğer istek başarılıysa ve dönen sayfa bir hata sayfası değilse (gerçek bir resimse)
                    if response.status_code == 200 and 'image' in response.headers.get('Content-Type', '').lower():
                        with open(kayit_yolu, 'wb') as img_file:
                            img_file.write(response.content)
                        print(f"Başarıyla indirildi: {kaydedilecek_isim}")
                        basarili_indirme += 1
                        indirildi_mi = True
                        break # Resmi bulduk ve indirdik, diğer uzantıları denemeye gerek kalmadı!
                except Exception as e:
                    pass # Ağ hatası olursa sessizce sıradaki uzantıya geç
                
                # Sunucuyu yormamak için her deneme arası çok kısa bekleme
                time.sleep(0.1)

            if not indirildi_mi:
                print(f"Hata: '{full_name}' için hiçbir uzantı ({', '.join(denenecek_uzantilar)}) sunucuda bulunamadı.")
                hatali_indirme += 1

    print(f"\n--- İŞLEM TAMAMLANDI ---")
    print(f"Yeni İndirilen: {basarili_indirme}")
    print(f"Atlanan (Zaten Var Olan): {atlanan}")
    print(f"Hatalı/Bulunamayan: {hatali_indirme}")

if __name__ == "__main__":
    banner()
    main()