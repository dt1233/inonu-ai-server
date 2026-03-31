import urllib.request
import json
import sys

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

URL = "https://panel.inonu.edu.tr/servlet/academic"

def fetch_academic_data():
    print(f"İstek atılıyor: {URL}")

    req = urllib.request.Request(
        URL,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
            "Referer": "https://panel.inonu.edu.tr/",
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            encoding = response.headers.get_content_charset("utf-8")
            data = json.loads(raw.decode(encoding))

        with open("academic.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Özet istatistikler
        total_units = len(data)
        total_academics = sum(len(unit.get("academicians", [])) for unit in data)

        print(f"✓ Veriler başarıyla alındı!")
        print(f"  - Toplam birim sayısı : {total_units}")
        print(f"  - Toplam akademisyen  : {total_academics}")
        print(f"  - Dosya kaydedildi    : academic.json")

    except urllib.error.HTTPError as e:
        print(f"HTTP Hatası: {e.code} {e.reason}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Bağlantı Hatası: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"JSON ayrıştırma hatası: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    banner()
    fetch_academic_data()