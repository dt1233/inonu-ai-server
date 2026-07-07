import os
import sys
import json
from loguru import logger
from inonu_ai.data_pipeline.pdf_extractor import extract_pdf_pages, _build_pdf_page_record

def main():
    # Force UTF-8 output for Windows console
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    logger.remove()
    pdf_dir = r"c:\projelerim\inönü ai\data\pdf_belgeler"
    
    if not os.path.exists(pdf_dir):
        print(f"Dizin bulunamadı: {pdf_dir}")
        return
        
    files = [f for f in os.listdir(pdf_dir) if f.endswith('.pdf')]
    if not files:
        print(f"Bu dizinde PDF bulunamadı: {pdf_dir}")
        return
        
    test_pdf = os.path.join(pdf_dir, files[0])
    print(f"Test Edilen PDF: {files[0]}")
    
    with open(test_pdf, "rb") as f:
        pdf_bytes = f.read()
        
    source_metadata = {
        "unit": "muhendislik",
        "unit_label": "Mühendislik Fakültesi",
        "fakulte": "Mühendislik Fakültesi",
        "source_fakulte": "Mühendislik Fakültesi",
        "scope": "faculty",
        "doc_type": "announcement",
        "ann_id": 9999,
        "title": "Mühendislik Fakültesi Duyurusu",
        "published_at": "2024-01-01",
        "source_url": "http://example.com/duyuru/9999",
    }
    
    pages = extract_pdf_pages(pdf_bytes, pdf_url=f"http://example.com/{files[0]}", source_metadata=source_metadata)
    
    page_count = len(pages)
    content_pages = sum(1 for p in pages if p.get("pdf_text_quality") == "text")
    detected_fakulte_pages = sum(1 for p in pages if p.get("detected_fakulte"))
    owner_mismatch = sum(1 for p in pages if p.get("detected_fakulte") and p.get("detected_fakulte") != source_metadata["fakulte"])
    empty_or_ocr = sum(1 for p in pages if p.get("pdf_text_quality") in ["empty", "ocr_required", "error"])
    
    print("\n--- SMOKE TEST RAPORU ---")
    print(f"Toplam Sayfa (page_count): {page_count}")
    print(f"Metin İçeren Sayfa Sayısı: {content_pages}")
    print(f"Fakülte Tespit Edilen (detected_fakulte): {detected_fakulte_pages}")
    print(f"OWNER MISMATCH (detected != source) Sayısı: {owner_mismatch}")
    print(f"Empty / OCR Required / Error Sayfaları: {empty_or_ocr}")
    
    print("\nÖrnek Sayfa Kaydı (1. Sayfa):")
    if pages:
        sample = dict(pages[0])
        if sample.get("content"):
            sample["content"] = sample["content"][:200] + " ... [TRUNCATED]"
        print(json.dumps(sample, indent=2, ensure_ascii=False))

    print("\n--- OWNER MISMATCH SİMÜLASYONU (Doğrudan record akışı) ---")
    test_text = "T.C. İnönü Üniversitesi Diş Hekimliği Fakültesi Dekanlığı. Sınav takvimi duyurusu."
    print(f"Mock Sayfa Metni: '{test_text}'")
    
    # Simulate extraction flow natively via the helper function used in extract_pdf_pages
    mock_record = _build_pdf_page_record(
        text=test_text,
        page_no=1,
        page_count=1,
        pdf_url="http://example.com/mock.pdf",
        source_metadata=source_metadata,
        extractor_used="pypdf_mock"
    )
    
    print(f"Sayfa İçi Tespit Edilen (detected_fakulte): {mock_record.get('detected_fakulte')}")
    print(f"Kaynak/Duyuru Fakültesi (source_fakulte): {mock_record.get('source_fakulte')}")
    
    all_pass = True
    if page_count != 2: all_pass = False
    if owner_mismatch != 1: all_pass = False

    if not all_pass:
        print("\n❌ BAZI TESTLER BAŞARISIZ!")
        import sys
        sys.exit(1)
    else:
        print("\n✅ TÜM TESTLER GEÇTİ!")

if __name__ == '__main__':
    main()
