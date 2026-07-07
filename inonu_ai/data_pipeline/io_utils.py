import os
import json
import shutil
from datetime import datetime
from loguru import logger

def load_json(path: str, default=None):
    """Güvenli UTF-8 JSON okuyucu."""
    if default is None:
        default = []
    
    if not os.path.exists(path):
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"JSON okuma hatası ({path}): {e}")
        # Bozuk dosyayı ezmemek için backup alalım
        backup_file(path)
        return default
    except Exception as e:
        logger.error(f"Dosya okuma hatası ({path}): {e}")
        return default

def atomic_write_json(path: str, data) -> bool:
    """Yazma işlemini tmp dosyaya yapıp, başarılıysa asıl dosyanın üzerine yazar."""
    # Ensure directory exists
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    
    tmp_path = f"{path}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        
        # Atomik yer değiştirme (Windows'da os.replace da atomiktir veya en güvenlisidir)
        os.replace(tmp_path, path)
        return True
    except Exception as e:
        logger.error(f"Atomik yazma hatası ({path}): {e}")
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except:
                pass
        return False

def backup_file(path: str):
    """Dosyanın timestamp'li bir yedeğini oluşturur."""
    if not os.path.exists(path):
        return
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{path}.backup_{timestamp}"
    try:
        shutil.copy2(path, backup_path)
        logger.info(f"Yedek alındı: {backup_path}")
    except Exception as e:
        logger.error(f"Yedek alma hatası ({path}): {e}")

import hashlib

def merge_records(existing: list, incoming: list, key_fields: list[str] = None) -> list:
    """
    Kayıtları hiyerarşik benzersiz anahtarlara göre birleştirir. Incoming boşsa existing korunur.
    Öncelik:
    1. ann_id
    2. content_hash
    3. pdf_url + page_no
    4. source_url
    5. sha256(json)
    """
    if not incoming:
        logger.warning("Gelen kayıt listesi boş. Eski veriler aynen korunuyor.")
        return existing

    merged_dict = {}
    
    def get_key(record):
        if record.get("ann_id"):
            return ("ann_id", record.get("ann_id"))
        if record.get("content_hash"):
            return ("content_hash", record.get("content_hash"))
        if record.get("pdf_url") and record.get("page_no") is not None:
            return ("pdf_url_page", record.get("pdf_url"), record.get("page_no"))
        if record.get("source_url"):
            return ("source_url", record.get("source_url"))
            
        json_str = json.dumps(record, sort_keys=True)
        return ("sha256", hashlib.sha256(json_str.encode("utf-8")).hexdigest())
    
    for rec in existing:
        k = get_key(rec)
        merged_dict[k] = rec

    new_count = 0
    updated_count = 0
    
    for rec in incoming:
        k = get_key(rec)
        if k in merged_dict:
            updated_count += 1
        else:
            new_count += 1
        merged_dict[k] = rec
            
    logger.info(f"Merge sonucu: {new_count} yeni, {updated_count} güncellendi.")
    return list(merged_dict.values())
