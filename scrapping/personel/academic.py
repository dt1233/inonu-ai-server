import urllib.request
import json
import sys
from pathlib import Path

class C:
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'
    WHITE = '\033[97m'
    DIM = '\033[2m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    RED = '\033[91m'

# ── MongoDB entegrasyonu ──────────────────────────────────────────
try:
    _PARENT = Path(__file__).resolve().parent.parent  # scrapping/
    sys.path.insert(0, str(_PARENT))
    from db_manager import DBManager, COL_ACADEMIC_UNITS, COL_PERSONNEL, COL_CHUNKS
    _MONGO_ENABLED = True
except ImportError:
    _MONGO_ENABLED = False

def banner() -> None:
    lines = [
        "",
        f"{C.CYAN}{C.BOLD}  ╔══════════════════════════════════════════════════════════════════╗{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║    {C.WHITE}██╗███╗   ██╗ ██████╗ ███╗   ██╗██╗   ██╗{C.CYAN}          ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║    {C.WHITE}██║████╗  ██║██╔═══██╗████╗  ██║██║   ██║{C.CYAN}          ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║    {C.WHITE}██║██╔██╗ ██║██║   ██║██╔██╗ ██║██║   ██║{C.CYAN}          ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║    {C.WHITE}██║██║└██╗██║██║   ██║██║└██╗██║██║   ██║{C.CYAN}          ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║    {C.WHITE}██║██║ └████║└██████╔╝██║ └████║└██████╔╝{C.CYAN}          ║{C.RESET}",
        f"{C.CYAN}{C.BOLD}  ║      {C.DIM}╔═╗╔═╗  ╔═══╝ └═════╝ └═╝  └═══╝ └═════╝ {C.CYAN}           ║{C.RESET}",
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

    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

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
        with urllib.request.urlopen(req, timeout=30, context=ctx) as response:
            raw = response.read()
            encoding = response.headers.get_content_charset("utf-8")
            data = json.loads(raw.decode(encoding))

        # ── JSON'a kaydet (mevcut davranış korunuyor) ──
        with open("academic.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        total_units     = len(data)
        total_academics = sum(len(unit.get("academicians", [])) for unit in data)

        print(f"✓ Veriler başarıyla alındı!")
        print(f"  - Toplam birim sayısı : {total_units}")
        print(f"  - Toplam akademisyen  : {total_academics}")
        print(f"  - Dosya kaydedildi    : academic.json")

        # ── MongoDB'ye yaz ──────────────────────────────────────────
        if _MONGO_ENABLED:
            _save_to_mongo(data)
        else:
            print(f"{C.YELLOW}  [!] db_manager bulunamadı, MongoDB'ye yazma atlandı.{C.RESET}")

    except urllib.error.HTTPError as e:
        print(f"HTTP Hatası: {e.code} {e.reason}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Bağlantı Hatası: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"JSON ayrıştırma hatası: {e}", file=sys.stderr)
        sys.exit(1)


def _save_to_mongo(data: list) -> None:
    """
    academic.json verisini MongoDB'ye yazar.
    - Her birim → academic_units koleksiyonu
    - Her akademisyen → personnel_details koleksiyonu
    - Akademisyen biyografileri → chunks koleksiyonu
    """
    try:
        with DBManager() as db_mgr:
            unit_ins = unit_upd = pers_ins = pers_upd = chunk_total = 0

            for unit in data:
                unit_id   = unit.get("id")
                unit_name = unit.get("unitName", "")
                unit_url  = unit.get("url", "")
                academics = unit.get("academicians", [])

                # ── 1. Birimi academic_units'e yaz ──────────────────
                unit_doc = {
                    "id":               unit_id,
                    "unit_name":        unit_name,
                    "url":              unit_url,
                    "academician_count": len(academics),
                    "raw":              unit,
                }
                status = db_mgr.upsert(COL_ACADEMIC_UNITS, unit_doc, id_field="id")
                if status == "inserted": unit_ins += 1
                else: unit_upd += 1

                # ── 2. Her akademisyeni personnel_details'e yaz ─────
                for person in academics:
                    p_id   = person.get("id")
                    p_name = f"{person.get('name', '').strip()} {person.get('surName', '').strip()}".strip()
                    title  = person.get("title", "")
                    email  = person.get("email", "")
                    bio    = (person.get("description") or "").strip()

                    person_doc = {
                        "id":          p_id,
                        "ad_soyad":    p_name,
                        "unvan":       title,
                        "email":       email,
                        "birim_id":    unit_id,
                        "birim_adi":   unit_name,
                        "kaynak":      "academic",
                        "raw":         person,
                    }
                    pstatus = db_mgr.upsert(COL_PERSONNEL, person_doc, id_field="id")
                    if pstatus == "inserted": pers_ins += 1
                    else: pers_upd += 1

                    # ── 3. Biyografiyi chunk'la ─────────────────────
                    if bio:
                        full_text = f"{p_name} - {title}\n\n{bio}"
                        n = db_mgr.upsert_chunks(
                            text=full_text,
                            source_url=f"https://panel.inonu.edu.tr/servlet/academic#{p_id}",
                            source_collection=COL_PERSONNEL,
                            doc_id=p_id,
                        )
                        chunk_total += n

            print(f"  {C.GREEN}[+] MongoDB:{C.RESET} "
                  f"Birimler: {C.BOLD}{unit_ins} yeni / {unit_upd} gün.{C.RESET}  "
                  f"Personel: {C.BOLD}{pers_ins} yeni / {pers_upd} gün.{C.RESET}  "
                  f"Chunk: {C.CYAN}{chunk_total}{C.RESET}")
    except Exception as e:
        print(f"  {C.YELLOW}[!] MongoDB yazma hatası (JSON kaydı etkilenmedi): {e}{C.RESET}")


if __name__ == "__main__":
    banner()
    fetch_academic_data()