#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import subprocess
from pathlib import Path
from unittest.mock import patch
import runpy

def test_runner_with_mock_docs(mock_docs):
    """Run run_rag_cases with mocked retriever that returns mock_docs."""
    sys.path.insert(0, str(Path(".").absolute()))
    import tests.run_rag_cases as run_rag
    
    class MockRetriever:
        def search(self, query, top_k=5):
            return mock_docs.get(query, [])
            
    run_rag.Retriever = MockRetriever
    
    try:
        run_rag.main()
        return 0
    except SystemExit as e:
        return e.code

def main():
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    print("=" * 60)
    print("RAG RUNNER MOCK SMOKE TEST")
    print("=" * 60)
    
    # Create a temporary yaml for tests
    yaml_content = """
- question: "test_empty_docs"
  expected_faculty: "Mühendislik"
- question: "test_forbidden"
  expected_faculty: "Mühendislik"
  forbidden_faculties: ["Tıp"]
- question: "test_wrong_scope"
  expected_faculty: "Mühendislik"
  allowed_scopes: ["faculty"]
- question: "test_missing_expected"
  expected_faculty: "Hukuk"
- question: "test_success"
  expected_faculty: "Mühendislik"
  allowed_scopes: ["faculty"]
  forbidden_faculties: ["Tıp"]
"""
    yaml_path = Path("tests/rag_cases.yaml")
    original_yaml = yaml_path.read_text(encoding="utf-8") if yaml_path.exists() else ""
    yaml_path.write_text(yaml_content, encoding="utf-8")
    
    try:
        mock_scenarios = {
            # 1. Empty Docs
            "test_empty_docs": [],
            
            # 2. Forbidden Faculty (mock returns Tip)
            "test_forbidden": [
                {
                    "score": 0.9,
                    "metadata": {
                        "source_fakulte": "Tıp",
                        "scope": "faculty"
                    }
                }
            ],
            
            # 3. Wrong Scope
            "test_wrong_scope": [
                {
                    "score": 0.9,
                    "metadata": {
                        "source_fakulte": "Mühendislik",
                        "scope": "university" # Not allowed
                    }
                }
            ],
            
            # 4. Missing Expected Faculty
            "test_missing_expected": [
                {
                    "score": 0.9,
                    "metadata": {
                        "source_fakulte": "Eğitim",
                        "scope": "faculty"
                    }
                }
            ],
            
            # 5. Success Case
            "test_success": [
                {
                    "score": 0.9,
                    "metadata": {
                        "source_fakulte": "Mühendislik",
                        "scope": "faculty",
                        "source_url": "http://test.com"
                    }
                }
            ]
        }
        
        exit_code = test_runner_with_mock_docs(mock_scenarios)
        
        if exit_code == 1:
            print("✅ TEST Runner hataları doğru şekilde tespit edip sys.exit(1) döndürdü.")
        else:
            print(f"❌ TEST Runner fail etmesi gerekirken {exit_code} döndürdü!")
            sys.exit(1)
            
    finally:
        # Restore yaml
        yaml_path.write_text(original_yaml, encoding="utf-8")

if __name__ == "__main__":
    main()
