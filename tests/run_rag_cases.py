#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import yaml
from pathlib import Path
from loguru import logger

# Ayar
root_path = Path(__file__).parent.parent
sys.path.insert(0, str(root_path))
sys.path.insert(0, str(root_path / "inonu_ai"))

# FlagEmbedding'i önceden yükle ki logları bozmasın
try:
    import FlagEmbedding
except ImportError:
    pass

from inonu_ai.engine.retriever import Retriever

def normalize_faculty(name):
    if not name: return ""
    return name.lower().strip()

def main():
    logger.info("RAG Cases Test Runner Başlatılıyor...")
    
    yaml_path = Path(__file__).parent / "rag_cases.yaml"
    if not yaml_path.exists():
        logger.error(f"{yaml_path} bulunamadı!")
        sys.exit(1)
        
    with open(yaml_path, "r", encoding="utf-8") as f:
        cases = yaml.safe_load(f)
        
    retriever = Retriever()
    all_passed = True
    
    for case in cases:
        question = case["question"]
        expected_faculty = case.get("expected_faculty", "")
        forbidden = [normalize_faculty(f) for f in case.get("forbidden_faculties", [])]
        allowed_scopes = case.get("allowed_scopes", [])
        
        logger.info(f"\nTEST VAKASI: {question}")
        docs = retriever.search(question, top_k=5)
        
        case_passed = True
        found_expected = False
        
        if not docs:
            logger.error("  [HATA] Hiç sonuç dönmedi! (docs boş)")
            case_passed = False
        
        for i, doc in enumerate(docs):
            meta = doc.get("metadata", {})
            f_source = normalize_faculty(meta.get("source_fakulte", ""))
            f_detect = normalize_faculty(meta.get("detected_fakulte", ""))
            f_meta = normalize_faculty(meta.get("fakulte", ""))
            scope = meta.get("scope", "")
            
            # Warn if no URL
            if not doc.get("source_url") and not meta.get("pdf_url"):
                logger.warning(f"  [UYARI] Doküman URL içermiyor! Skor: {doc.get('score')}")
                
            # Check scope
            if allowed_scopes and scope not in allowed_scopes:
                logger.error(f"  [HATA] İzin verilmeyen scope ({scope}) geldi! Doküman {i+1}")
                case_passed = False
                
            # Check forbidden
            for f_val in [f_source, f_detect, f_meta]:
                if f_val and f_val in forbidden:
                    logger.error(f"  [HATA] Yasaklı fakülte ({f_val}) geldi! Doküman {i+1}")
                    case_passed = False
                    
            # Check expected
            expected_norm = normalize_faculty(expected_faculty)
            if expected_norm and expected_norm in [f_source, f_detect, f_meta]:
                found_expected = True
                
        if expected_faculty and not found_expected:
            logger.error(f"  [HATA] Beklenen fakülte ({expected_faculty}) sonuçlarda bulunamadı!")
            case_passed = False
            
        if case_passed:
            logger.info(f"  Vaka Başarılı: {question}")
        else:
            logger.error(f"  Vaka BAŞARISIZ: {question}")
            all_passed = False
            
    if not all_passed:
        logger.error("RAG Kalite Testleri BAŞARISIZ!")
        sys.exit(1)
    else:
        logger.info("\nTÜM RAG TEST VAKALARI BAŞARIYLA GEÇTİ! ✅")

if __name__ == "__main__":
    main()
