#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "inonu_ai"))

# Mock LLM and heavy deps
sys.modules['engine.sglang_client'] = MagicMock()
sys.modules['qdrant_client'] = MagicMock()
sys.modules['qdrant_client.models'] = MagicMock()
sys.modules['pydantic_settings'] = MagicMock()

from inonu_ai.agents.nodes import retriever_node, generator_node
from inonu_ai.agents.state import AgentState


def main():
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 60)
    print("AGENT NODES SMOKE TEST (API ADAPTATION)")
    print("=" * 60)

    # Mock Retriever.search result (dict format from Adım 6)
    mock_docs = [
        {
            "text": "Mühendislik Fakültesi sınavları 10 Haziranda.",
            "score": 0.95,
            "source_url": "http://example.com/muh-sinav",
            "metadata": {
                "unit": "muhendislik",
                "detected_fakulte": "Mühendislik Fakültesi",
                "doc_type": "announcement"
            }
        },
        {
            "text": "Mühendislik duyurusu pdf içerik...",
            "score": 0.82,
            "source_url": "", # Boş olabilir, pdf_url dolu olabilir
            "metadata": {
                "unit": "muhendislik",
                "detected_fakulte": "Mühendislik Fakültesi",
                "doc_type": "pdf_page",
                "pdf_url": "http://example.com/muh-duyuru.pdf"
            }
        }
    ]

    initial_state: AgentState = {
        "question": "Mühendislik sınavları ne zaman?",
        "rewritten_question": "Mühendislik Fakültesi sınavları ne zaman?",
        "session_id": "test_session",
        "history": [],
        "route": "rag",
        "documents": [],
        "answer": "",
        "grade": "",
        "iterations": 0,
        "sources": []
    }

    print("\n--- TEST 1: retriever_node ---")
    with patch("engine.retriever.Retriever.search", return_value=mock_docs) as mock_search:
        state1 = retriever_node(initial_state)
        
        called = mock_search.called
        print(f"  Merkezi Retriever.search kullanıldı mı: {'✅' if called else '❌'}")
        
        docs = state1.get("documents", [])
        is_dict = len(docs) > 0 and isinstance(docs[0], dict)
        print(f"  Dönen documents dict formatında mı: {'✅' if is_dict else '❌'}")
        print(f"  Belge sayısı: {len(docs)}")

    print("\n--- TEST 2: generator_node (RAG Route) ---")
    with patch("inonu_ai.agents.nodes.llm", return_value="Mocked LLM Response") as mock_llm:
        state2 = generator_node(state1)
        
        answer = state2.get("answer")
        sources = state2.get("sources", [])
        
        print(f"  Generator hata vermeden çalıştı mı: {'✅' if answer else '❌'}")
        print(f"  LLM Çağrıldı mı: {'✅' if mock_llm.called else '❌'}")
        print(f"  Çıkarılan Kaynak Sayısı: {len(sources)}")
        
        # Test the structure of sources
        if len(sources) > 0:
            first_source = sources[0]
            is_structured = isinstance(first_source, dict) and "fakulte" in first_source
            print(f"  Kaynaklar structured formatta mı (dict): {'✅' if is_structured else '❌'}")
            
            # Asset required metadata fields from first mock source
            fakulte_ok = first_source.get("detected_fakulte") == "Mühendislik Fakültesi"
            type_ok = first_source.get("doc_type") == "announcement"
            score_ok = first_source.get("score") == 0.95
            print(f"  Kaynak metadata alanları (fakulte, doc_type, score) eksiksiz mi: {'✅' if fakulte_ok and type_ok and score_ok else '❌'}")
        else:
            is_structured = False
            fakulte_ok = False
            type_ok = False
            score_ok = False
            
    print("\n--- TEST 3: generator_node (Direct Route) ---")
    direct_state = {**initial_state, "route": "direct"}
    with patch("inonu_ai.agents.nodes.llm", return_value="Direct response") as mock_llm2:
        state3 = generator_node(direct_state)
        direct_sources = state3.get("sources", [])
        is_empty = (len(direct_sources) == 0)
        print(f"  Direct route sources listesi boş mu (=[]): {'✅' if is_empty else '❌'} (Gelen: {direct_sources})")

    print("\n" + "=" * 60)
    all_passed = called and is_dict and answer and is_structured and fakulte_ok and type_ok and score_ok and is_empty
    print(f"GENEL SONUÇ: {'✅ TÜM TESTLER GEÇTİ' if all_passed else '❌ BAZI TESTLER BAŞARISIZ'}")
    print("=" * 60)

    if not all_passed:
        sys.exit(1)

if __name__ == "__main__":
    main()
