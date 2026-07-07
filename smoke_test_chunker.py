import sys
import json
from loguru import logger
from inonu_ai.data_pipeline.chunker import Chunker

def main():
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    logger.remove()

    mock_results = {
        "announcements": [
            {
                "unit": "muhendislik",
                "unit_label": "Mühendislik Fakültesi Duyuruları",
                "fakulte": "Mühendislik Fakültesi",
                "source_fakulte": "Mühendislik Fakültesi",
                "detected_fakulte": "",
                "scope": "faculty",
                "id": "1001",
                "ann_id": "1001",
                "title": "Mühendislik Sınav Programı",
                "published_at": "2024-01-01",
                "source_url": "http://example.com/muhendislik/1001",
                "content": "Sınav programı ektedir. Lütfen tüm detayları pdf eklerinden dikkatlice kontrol ediniz ve sınav saati öncesinde sınıfta hazır bulununuz.",
                "attachments": [
                    {
                        "url": "http://example.com/muhendislik/1001/ek1.pdf",
                        "pages": [
                            {
                                "unit": "muhendislik",
                                "unit_label": "Mühendislik Fakültesi Duyuruları",
                                "fakulte": "Mühendislik Fakültesi",
                                "source_fakulte": "Mühendislik Fakültesi",
                                "detected_fakulte": "Mühendislik Fakültesi",
                                "scope": "faculty",
                                "doc_type": "pdf_page",
                                "page_no": 1,
                                "page_count": 3,
                                "ann_id": "1001",
                                "title": "Mühendislik Sınav Programı",
                                "published_at": "2024-01-01",
                                "source_url": "http://example.com/muhendislik/1001",
                                "pdf_url": "http://example.com/muhendislik/1001/ek1.pdf",
                                "pdf_text_quality": "text",
                                "content": "Mühendislik Fakültesi Bilgisayar Mühendisliği Sınav Tarihleri..."
                            },
                            {
                                "unit": "muhendislik",
                                "unit_label": "Mühendislik Fakültesi Duyuruları",
                                "fakulte": "Mühendislik Fakültesi",
                                "source_fakulte": "Mühendislik Fakültesi",
                                "detected_fakulte": "Diş Hekimliği Fakültesi",
                                "scope": "faculty",
                                "doc_type": "pdf_page",
                                "page_no": 2,
                                "page_count": 3,
                                "ann_id": "1001",
                                "title": "Mühendislik Sınav Programı",
                                "published_at": "2024-01-01",
                                "source_url": "http://example.com/muhendislik/1001",
                                "pdf_url": "http://example.com/muhendislik/1001/ek1.pdf",
                                "pdf_text_quality": "text",
                                "content": "Diş Hekimliği Fakültesi Ortodonti Sınav Tarihleri..."
                            },
                            {
                                "unit": "muhendislik",
                                "unit_label": "Mühendislik Fakültesi Duyuruları",
                                "fakulte": "Mühendislik Fakültesi",
                                "source_fakulte": "Mühendislik Fakültesi",
                                "detected_fakulte": "",
                                "scope": "faculty",
                                "doc_type": "pdf_page",
                                "page_no": 3,
                                "page_count": 3,
                                "ann_id": "1001",
                                "title": "Mühendislik Sınav Programı",
                                "published_at": "2024-01-01",
                                "source_url": "http://example.com/muhendislik/1001",
                                "pdf_url": "http://example.com/muhendislik/1001/ek1.pdf",
                                "pdf_text_quality": "empty",
                                "content": ""
                            }
                        ]
                    }
                ]
            }
        ]
    }

    chunker = Chunker()
    chunks = chunker.chunk_all(mock_results)

    print("\n--- CHUNKER SMOKE TEST RAPORU ---")
    print(f"Toplam Chunk Sayısı: {len(chunks)}")
    
    pdf_chunks = [c for c in chunks if c.metadata.get("doc_type") == "pdf_page"]
    print(f"pdf_page Chunk Sayısı: {len(pdf_chunks)}")
    
    empty_chunks = [c for c in chunks if c.metadata.get("page_no") == 3]
    print(f"Empty/OCR_Required Sayfanın (Page 3) Chunk Sayısı: {len(empty_chunks)}")
    
    print("\nDoğrulamalar:")
    print("1. Context Seal (Bağlam Mührü) Kontrolü (Duyuru Ana Metni):")
    main_ann_chunk = next(c for c in chunks if c.metadata.get("doc_type") == "announcement")
    print("---------------------------------")
    print(main_ann_chunk.text)
    print("---------------------------------")
    
    print("2. Source_key formatı:")
    print(f"   Duyuru Ana Metin: {main_ann_chunk.source_key}")
    for p in pdf_chunks:
        print(f"   PDF Sayfa {p.metadata.get('page_no')}: {p.source_key}")

    print("\n3. Page 2 Metadata (Diş Hekimliği) Korunuyor mu?:")
    p2_chunk = next(c for c in pdf_chunks if c.metadata.get("page_no") == 2)
    print(f"   detected_fakulte: {p2_chunk.metadata.get('detected_fakulte')}")
    print("   Context Seal:")
    print("---------------------------------")
    print(p2_chunk.text)
    print("---------------------------------")

    all_pass = True
    if len(chunks) != 3: all_pass = False
    if len(pdf_chunks) != 2: all_pass = False
    if len(empty_chunks) != 0: all_pass = False

    if not all_pass:
        print("❌ BAZI TESTLER BAŞARISIZ!")
        sys.exit(1)
    else:
        print("✅ TÜM TESTLER GEÇTİ!")

if __name__ == '__main__':
    main()
