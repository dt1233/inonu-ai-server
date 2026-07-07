#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import json
import os

from inonu_ai.data_pipeline.io_utils import load_json, atomic_write_json, merge_records, backup_file

def main():
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 60)
    print("SAFE MERGE SMOKE TEST")
    print("=" * 60)

    # Prepare mock existing data
    existing = [
        {"ann_id": 1, "source_url": "url1", "title": "Duyuru 1", "content_hash": "hash1"},
        {"content_hash": "hash2", "title": "Chunk 1"},
        {"pdf_url": "pdf1", "page_no": 1, "title": "PDF Sayfa 1 (Eski)"},
        {"source_url": "url2", "title": "Statik Sayfa (Eski)"}
    ]

    incoming = [
        # ann_id same, url changed -> update
        {"ann_id": 1, "source_url": "url1_new", "title": "Duyuru 1 (Yeni URL)"},
        # content_hash same -> update
        {"content_hash": "hash2", "title": "Chunk 1 (Updated)"},
        # pdf_url + page_no same -> update
        {"pdf_url": "pdf1", "page_no": 1, "title": "PDF Sayfa 1 (Yeni)"},
        # source_url same -> update
        {"source_url": "url2", "title": "Statik Sayfa (Yeni)"},
        # New record with sha256 fallback
        {"title": "No ID record"}
    ]

    print("\n--- TEST 1: Merge Operations (Hierarchical Keys) ---")
    merged = merge_records(existing, incoming)
    
    is_count_5 = len(merged) == 5
    ann_id_updated = any(r.get("source_url") == "url1_new" for r in merged)
    hash_updated = any(r.get("title") == "Chunk 1 (Updated)" for r in merged)
    pdf_updated = any(r.get("title") == "PDF Sayfa 1 (Yeni)" for r in merged)
    source_updated = any(r.get("title") == "Statik Sayfa (Yeni)" for r in merged)
    
    print(f"  Toplam kayıt sayısı 5 mi: {'✅' if is_count_5 else '❌'}")
    print(f"  ann_id bazlı URL değişimi update edildi mi: {'✅' if ann_id_updated else '❌'}")
    print(f"  content_hash bazlı duplicate elenip update edildi mi: {'✅' if hash_updated else '❌'}")
    print(f"  pdf_url+page_no bazlı update edildi mi: {'✅' if pdf_updated else '❌'}")
    print(f"  source_url bazlı update edildi mi: {'✅' if source_updated else '❌'}")

    print("\n--- TEST 2: Empty Incoming Fallback ---")
    merged_empty = merge_records(existing, [])
    kept_all = len(merged_empty) == 4
    print(f"  Gelen liste boşsa eski veriler korundu mu: {'✅' if kept_all else '❌'}")

    print("\n--- TEST 3: Encoding Guard (UTF-8) ---")
    test_path = "data/test_encoding.json"
    tr_text = "Mühendislik Fakültesi Şöğüncü İöü"
    atomic_write_json(test_path, [{"text": tr_text}])
    loaded = load_json(test_path)
    encoding_ok = loaded[0]["text"] == tr_text
    print(f"  Türkçe karakterler bozulmadan okundu/yazıldı mı: {'✅' if encoding_ok else '❌'}")

    print("\n--- TEST 4: Bozuk JSON Backup ---")
    with open(test_path, "w", encoding="utf-8") as f:
        f.write("{bozuk json]")
    loaded_bad = load_json(test_path, default=[])
    backup_exists = any(f.startswith("test_encoding.json.backup_") for f in os.listdir("data"))
    backup_handled = (loaded_bad == []) and backup_exists
    print(f"  Bozuk JSON'da default dönülüp backup alındı mı: {'✅' if backup_handled else '❌'}")

    # Clean up test files
    for f in os.listdir("data"):
        if f.startswith("test_encoding.json"):
            os.remove(os.path.join("data", f))

    all_passed = is_count_5 and ann_id_updated and hash_updated and pdf_updated and source_updated and kept_all and encoding_ok and backup_handled

    
    print("\n" + "=" * 60)
    print(f"GENEL SONUÇ: {'✅ TÜM TESTLER GEÇTİ' if all_passed else '❌ BAZI TESTLER BAŞARISIZ'}")
    print("=" * 60)

    if not all_passed:
        sys.exit(1)

if __name__ == "__main__":
    main()
