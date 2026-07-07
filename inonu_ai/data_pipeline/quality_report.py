#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import sys
import os
from pathlib import Path

# Adjust path to import io_utils if run as script
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from inonu_ai.data_pipeline.io_utils import load_json, atomic_write_json
from loguru import logger

def main():
    parser = argparse.ArgumentParser(description="İnönü AI Veri Kalite Raporlayıcı")
    parser.add_argument("--strict", action="store_true", help="Uyarı (Warning) durumunda da sys.exit(1) döndürür.")
    parser.add_argument("--json-only", action="store_true", help="Sadece JSON çıktısı üretir, terminale renkli log basmaz.")
    parser.add_argument("--crawl-path", type=str, default="data/crawl_results.json", help="Crawl verisi yolu")
    parser.add_argument("--chunks-path", type=str, default="data/chunks_output.json", help="Chunk verisi yolu")
    parser.add_argument("--report-path", type=str, default="data/quality_report.json", help="Çıktı raporu yolu")
    args = parser.parse_args()

    if args.json_only:
        logger.remove()

    CRAWL_PATH = args.crawl_path
    CHUNKS_PATH = args.chunks_path
    REPORT_PATH = args.report_path

    crawl_data = load_json(CRAWL_PATH, default={})
    chunks_data = load_json(CHUNKS_PATH, default=[])

    report = {
        "metrics": {
            "total_records": 0,
            "total_chunks": len(chunks_data),
            "owner_mismatches": 0,
            "empty_faculty": 0,
            "empty_page_no": 0,
            "non_text_quality": 0,
            "encoding_anomalies": 0,
            "duplicate_content_hash": 0,
            "missing_content_hash": 0,
        },
        "errors": [],
        "warnings": []
    }

    # Count total records
    if isinstance(crawl_data, dict):
        total_rec = sum(len(v) for k, v in crawl_data.items() if isinstance(v, list))
        report["metrics"]["total_records"] = total_rec

    seen_hashes = set()
    ANOMALY_STRINGS = ["Ã§", "Ã‡", "ÄŸ", "Äž", "Ä±", "Ä°", "Ã¶", "Ã–", "ÅŸ", "Åž", "Ã¼", "Ãœ", "â", "\ufffd"]

    for chunk in chunks_data:
        meta = chunk.get("metadata", {})
        scope = meta.get("scope", "")
        doc_type = meta.get("doc_type", "")
        fakulte = meta.get("fakulte", "")
        source_fakulte = meta.get("source_fakulte", "")
        detected_fakulte = meta.get("detected_fakulte", "")
        pdf_quality = meta.get("pdf_text_quality", "")
        page_no = meta.get("page_no")
        text = chunk.get("text", "")
        
        c_hash = chunk.get("content_hash")
        if not c_hash:
            c_hash = meta.get("content_hash")
            
        if not c_hash:
            report["metrics"]["missing_content_hash"] += 1
            report["warnings"].append(f"Eksik content_hash! (doc_type: {doc_type})")
        else:
            if c_hash in seen_hashes:
                report["metrics"]["duplicate_content_hash"] += 1
                # Duplicate content_hash artık warning olarak eklenmiyor, sadece metrik
            seen_hashes.add(c_hash)

        # Empty Faculty Check
        if scope == "faculty" and not fakulte and not source_fakulte:
            report["metrics"]["empty_faculty"] += 1
            report["errors"].append(f"Boş fakülte (scope=faculty). doc_type: {doc_type}")

        # Empty Page No Check for PDFs
        if doc_type == "pdf_page" and page_no is None:
            report["metrics"]["empty_page_no"] += 1
            report["errors"].append(f"PDF sayfa numarası boş. url: {meta.get('pdf_url')}")

        # PDF Quality Check
        if doc_type == "pdf_page" and pdf_quality and pdf_quality != "text":
            report["metrics"]["non_text_quality"] += 1
            report["warnings"].append(f"PDF sayfası okunamadı (quality={pdf_quality}). Sayfa: {page_no}")

        # Owner Mismatch Check
        if source_fakulte and detected_fakulte and source_fakulte != detected_fakulte:
            report["metrics"]["owner_mismatches"] += 1
            report["warnings"].append(f"Owner mismatch! Source: {source_fakulte}, Detected: {detected_fakulte}")

        # Encoding Anomaly Check
        if any(bad_str in text for bad_str in ANOMALY_STRINGS):
            report["metrics"]["encoding_anomalies"] += 1
            report["warnings"].append(f"Encoding anomalisi tespit edildi (Mojibake).")

    # Save JSON report
    atomic_write_json(REPORT_PATH, report)

    if not args.json_only:
        print("=" * 60)
        print("KALİTE RAPORU")
        print("=" * 60)
        for k, v in report["metrics"].items():
            print(f"  {k}: {v}")
        
        print(f"\nHatalar (ERRORS): {len(report['errors'])}")
        for e in report["errors"][:5]:
            print(f"  - {e}")
        if len(report['errors']) > 5:
            print(f"  ... ve {len(report['errors']) - 5} tane daha.")
            
        print(f"\nUyarılar (WARNINGS): {len(report['warnings'])}")
        for w in report["warnings"][:5]:
            print(f"  - {w}")
        if len(report['warnings']) > 5:
            print(f"  ... ve {len(report['warnings']) - 5} tane daha.")
            
        print("=" * 60)

    # Exit code mechanics
    if len(report["errors"]) > 0:
        if not args.json_only:
            logger.error("Kalite kapısı geçilemedi: Hatalar var.")
        sys.exit(1)
        
    if args.strict and len(report["warnings"]) > 0:
        if not args.json_only:
            logger.error("Kalite kapısı geçilemedi: Strict mode aktif ve uyarılar var.")
        sys.exit(1)
        
    if not args.json_only:
        logger.info("Kalite kapısı başarıyla geçildi.")

if __name__ == "__main__":
    main()
