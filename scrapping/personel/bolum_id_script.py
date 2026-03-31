import json

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

banner()

# JSON dosyasını okuma (Kendi dosya adınıza göre değiştirebilirsiniz)
with open('academic.json', 'r', encoding='utf-8') as file:
    data = json.load(file)

# Çıktıyı txt dosyasına kaydetmek için yeni bir dosya oluşturuyoruz
with open('bolumler.txt', 'w', encoding='utf-8') as output_file:
    # Listedeki her bir bölüm objesini döngüye alıyoruz
    for item in data:
        # İlgili anahtarları (.get metoduyla hata almamak için) çekiyoruz
        unit_name = item.get('unitName', 'Belirtilmemiş')
        url = item.get('url', 'Belirtilmemiş')
        unit_id = item.get('id', 'Belirtilmemiş')
        
        # İstediğimiz formata getirip dosyaya yazdırıyoruz
        satir = f"Bölüm Adı: {unit_name} | URL: {url} | ID: {unit_id}\n"
        output_file.write(satir)

print("İşlem tamamlandı! Veriler 'bolumler.txt' adlı dosyaya başarıyla kaydedildi.")