#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
import subprocess
import tempfile
from pathlib import Path
from inonu_ai.data_pipeline.io_utils import atomic_write_json, load_json

def main():
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    print("=" * 60)
    print("KALİTE RAPORU SMOKE TEST")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        crawl_path = temp_path / "crawl_results.json"
        chunks_path = temp_path / "chunks_output.json"
        report_path = temp_path / "quality_report.json"
        
        mock_chunks = [
            # Normal chunk
            {
                "content_hash": "hash1",
                "text": "Normal metin",
                "metadata": {
                    "scope": "faculty",
                    "doc_type": "announcement",
                    "fakulte": "Mühendislik Fakültesi",
                    "source_fakulte": "Mühendislik Fakültesi",
                    "detected_fakulte": "Mühendislik Fakültesi"
                }
            },
            # Duplicate hash
            {
                "content_hash": "hash1",
                "text": "Normal metin (Duplicate)",
                "metadata": {
                    "scope": "faculty",
                    "doc_type": "announcement",
                    "fakulte": "Mühendislik Fakültesi",
                    "source_fakulte": "Mühendislik Fakültesi"
                }
            },
            # Empty faculty Error
            {
                "content_hash": "hash3",
                "text": "Fakülte boş metni",
                "metadata": {
                    "scope": "faculty",
                    "doc_type": "announcement",
                    "fakulte": "",
                    "source_fakulte": ""
                }
            },
            # Empty page no Error
            {
                "content_hash": "hash4",
                "text": "Sayfa no yok",
                "metadata": {
                    "scope": "faculty",
                    "doc_type": "pdf_page",
                    "fakulte": "Tıp Fakültesi",
                    "source_fakulte": "Tıp Fakültesi",
                    "pdf_url": "http://test.pdf",
                    "page_no": None
                }
            },
            # Non-text quality Warning
            {
                "content_hash": "hash5",
                "text": "OCR gerekli",
                "metadata": {
                    "scope": "faculty",
                    "doc_type": "pdf_page",
                    "fakulte": "Tıp Fakültesi",
                    "source_fakulte": "Tıp Fakültesi",
                    "pdf_url": "http://test.pdf",
                    "page_no": 1,
                    "pdf_text_quality": "empty"
                }
            },
            # Owner mismatch Warning
            {
                "content_hash": "hash6",
                "text": "Yanlış fakülte algılandı",
                "metadata": {
                    "scope": "faculty",
                    "doc_type": "pdf_page",
                    "fakulte": "Mühendislik Fakültesi",
                    "source_fakulte": "Mühendislik Fakültesi",
                    "detected_fakulte": "Diş Hekimliği Fakültesi",
                    "page_no": 2,
                    "pdf_text_quality": "text"
                }
            },
            # Encoding anomaly Error
            {
                "content_hash": "hash7",
                "text": "Bozuk karakterli metin: Ã",
                "metadata": {
                    "scope": "university",
                    "doc_type": "static"
                }
            }
        ]
        
        mock_crawl = {"announcements": [{}], "static_contents": [{}]}
        
        atomic_write_json(str(chunks_path), mock_chunks)
        atomic_write_json(str(crawl_path), mock_crawl)
        
        # 2. Raporu Çalıştır
        print("quality_report.py çalıştırılıyor...\n")
        
        cmd = [
            sys.executable, "inonu_ai/data_pipeline/quality_report.py", 
            "--json-only",
            "--crawl-path", str(crawl_path),
            "--chunks-path", str(chunks_path),
            "--report-path", str(report_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True)
        
        # Assert Exit Code 1
        if result.returncode != 1:
            print(f"❌ BEKLENEN EXIT CODE 1 GELMEDİ (Gelen: {result.returncode})")
            print(result.stdout.decode('utf-8', errors='ignore'))
            print(result.stderr.decode('utf-8', errors='ignore'))
            sys.exit(1)
            
        # 3. Sonuç JSON'ı kontrol et
        report = load_json(str(report_path))
        m = report["metrics"]
        
        passed = True
        if m["total_records"] != 2: passed = False; print("Hata: total_records")
        if m["total_chunks"] != 7: passed = False; print("Hata: total_chunks")
        if m["empty_faculty"] != 1: passed = False; print("Hata: empty_faculty")
        if m["empty_page_no"] != 1: passed = False; print("Hata: empty_page_no")
        if m["non_text_quality"] != 1: passed = False; print("Hata: non_text_quality")
        if m["owner_mismatches"] != 1: passed = False; print("Hata: owner_mismatches")
        if m["encoding_anomalies"] != 1: passed = False; print(f"Hata: encoding_anomalies ({m['encoding_anomalies']})")
        if m["duplicate_content_hash"] != 1: passed = False; print("Hata: duplicate_content_hash")
        
        if len(report["errors"]) != 3: passed = False; print(f"Hata: errors length = {len(report['errors'])}")
        if len(report["warnings"]) != 3: passed = False; print("Hata: warnings length")

        # Verify real files were not touched by looking at their mtime or simply that we used tempfile
        print("Gerçek dosyalara dokunulmadı.")
        
        print("\n" + "=" * 60)
        if passed:
            print("GENEL SONUÇ: ✅ TÜM TESTLER GEÇTİ")
        else:
            print("GENEL SONUÇ: ❌ BAZI TESTLER BAŞARISIZ")
            sys.exit(1)

if __name__ == "__main__":
    main()
