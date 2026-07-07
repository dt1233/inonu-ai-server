#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
from pathlib import Path

# Proje dizinini yola ekle
root_path = Path(__file__).parent.parent
sys.path.insert(0, str(root_path))
sys.path.insert(0, str(root_path / "inonu_ai"))

try:
    import FlagEmbedding
except ImportError:
    pass

from inonu_ai.agents.graph import get_graph
from inonu_ai.agents.state import AgentState

def main():
    print("="*60)
    print("🤖 İNÖNÜ AI - İNTERAKTİF RAG TESTİ 🤖")
    print("="*60)
    print("Qdrant ve LLM modelleri yükleniyor. Lütfen bekleyin...")
    
    # Modelleri yüklemek için graph'ı bir kez initialize ediyoruz
    graph = get_graph()
    print("Sistem hazır! (Çıkmak için 'q', 'quit' veya 'exit' yazın)")
    print("-" * 60)

    while True:
        try:
            question = input("\nSen: ")
            if question.strip().lower() in ['q', 'quit', 'exit']:
                print("Görüşmek üzere!")
                break
                
            if not question.strip():
                continue

            print("\n🔍 Arama yapılıyor ve cevap üretiliyor...\n")
            
            initial: AgentState = {
                "question": question,
                "rewritten_question": "",
                "session_id": "",
                "history": [],
                "route": "",
                "documents": [],
                "answer": "",
                "grade": "",
                "iterations": 0,
                "sources": [],
            }
            
            result = graph.invoke(initial)
            
            answer = result.get("answer", "Cevap üretilemedi.")
            sources = result.get("sources", [])
            
            print("🤖 İNÖNÜ AI:")
            print(answer)
            print("\n📚 KULLANILAN KAYNAKLAR:")
            if not sources:
                print("  - Kaynak bulunamadı (LLM kendi bilgisinden veya genel cevap verdi)")
            else:
                for idx, src in enumerate(sources, 1):
                    fakulte = src.get('fakulte', 'Bilinmiyor')
                    score = src.get('score', 0.0)
                    url = src.get('source_url', 'URL Yok')
                    print(f"  {idx}. [{fakulte}] (Skor: {score:.3f}) -> {url}")
            print("-" * 60)
            
        except KeyboardInterrupt:
            print("\nGörüşmek üzere!")
            break
        except Exception as e:
            print(f"\n[HATA] Beklenmeyen bir hata oluştu: {e}")

if __name__ == "__main__":
    main()
