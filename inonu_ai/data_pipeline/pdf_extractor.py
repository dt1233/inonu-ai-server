import io
import hashlib
from loguru import logger
from .faculty_detector import detect_faculty

def generate_content_hash(pdf_url: str, page_no: int, content: str) -> str:
    raw = f"{pdf_url}|{page_no}|{content}"
    return hashlib.md5(raw.encode("utf-8", errors="ignore")).hexdigest()

def _text_quality(text: str) -> str:
    if not text or not text.strip():
        return "empty"
    # Basit OCR gereksinimi kontrolü: boşluklar hariç çok az alfanümerik karakter varsa
    alnum_count = sum(c.isalnum() for c in text)
    if len(text) > 50 and alnum_count < len(text) * 0.1:
        return "ocr_required"
    return "text"

def _extract_with_pypdf(pdf_bytes: bytes) -> list[str]:
    pages = []
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        for p in reader.pages:
            text = p.extract_text() or ""
            pages.append(text.strip())
    except Exception as e:
        logger.debug(f"pypdf extraction failed: {e}")
    return pages

def _extract_with_pdfminer(pdf_bytes: bytes) -> list[str]:
    pages = []
    try:
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LTTextContainer
        for page_layout in extract_pages(io.BytesIO(pdf_bytes)):
            page_text = ""
            for element in page_layout:
                if isinstance(element, LTTextContainer):
                    page_text += element.get_text()
            pages.append(page_text.strip())
    except Exception as e:
        logger.debug(f"pdfminer extraction failed: {e}")
    return pages

def _build_pdf_page_record(
    text: str,
    page_no: int,
    page_count: int,
    pdf_url: str,
    source_metadata: dict,
    extractor_used: str
) -> dict:
    quality = _text_quality(text)
    if extractor_used == "error":
        quality = "error"
        
    fd = detect_faculty(text)
    detected_fakulte = fd["fakulte"]
    
    if not detected_fakulte:
        detected_fakulte = source_metadata.get("detected_fakulte") or source_metadata.get("source_fakulte") or source_metadata.get("fakulte") or ""
        
    record = {
        "unit": source_metadata.get("unit", ""),
        "unit_label": source_metadata.get("unit_label", ""),
        "fakulte": source_metadata.get("fakulte", ""),
        "source_fakulte": source_metadata.get("source_fakulte", ""),
        "detected_fakulte": detected_fakulte,
        "scope": source_metadata.get("scope", "unknown"),
        "doc_type": "pdf_page",
        "page_no": page_no,
        "page_count": page_count,
        "ann_id": source_metadata.get("ann_id"),
        "title": source_metadata.get("title", ""),
        "published_at": source_metadata.get("published_at", ""),
        "source_url": source_metadata.get("source_url", ""),
        "pdf_url": pdf_url,
        "pdf_text_quality": quality,
        "extractor": extractor_used if quality != "error" else "error",
        "content_hash": generate_content_hash(pdf_url, page_no, text),
        "content": text if quality == "text" else ""
    }
    
    if quality == "ocr_required":
        record["extractor"] = "ocr_required"
        
    return record


def extract_pdf_pages(pdf_bytes: bytes, pdf_url: str = "", source_metadata: dict | None = None) -> list[dict]:
    if source_metadata is None:
        source_metadata = {}
        
    pages_text = _extract_with_pypdf(pdf_bytes)
    extractor_used = "pypdf"
    
    # Check if pypdf completely failed or returned all empty pages
    if not pages_text or all(not p.strip() for p in pages_text):
        pm_pages = _extract_with_pdfminer(pdf_bytes)
        if pm_pages and any(p.strip() for p in pm_pages):
            pages_text = pm_pages
            extractor_used = "pdfminer"
        
    if not pages_text:
        extractor_used = "error"
        pages_text = [""]

    page_count = len(pages_text)
    results = []
    
    for i, text in enumerate(pages_text, 1):
        record = _build_pdf_page_record(text, i, page_count, pdf_url, source_metadata, extractor_used)
        results.append(record)
        
    return results
