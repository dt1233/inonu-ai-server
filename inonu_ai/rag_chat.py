#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import requests
import json
from loguru import logger
from engine.retriever import Retriever

SGLANG_URL = "http://localhost:30000/v1/chat/completions"

def generate_answer(query: str, retrieved_docs: list) -> str:
    # 1. Bağlamı (Context) oluştur
    context = ""
    for idx, doc in enumerate(retrieved_docs, 1):
        context += f"--- Kaynak {idx} ({doc['source_url']}) ---\n{doc['text']}\n\n"
    
    # 2. RAG Prompt'unu hazırla
    system_prompt = (
        "Sen İnönü Üniversitesi'nin resmi yapay zeka asistanısın. Adın 'İnönü Asistan'. "
        "Seni İnönü Üniversitesi Dijital Dönüşüm Ofisi koordinatörlüğünde "
        "Ferhat Yıldız ve Muhammet Bilal Yıldız geliştirdi. Biri sana kim olduğunu veya "
        "seni kimin geliştirdiğini sorarsa gururla bu bilgiyi ver. "
        "Aşağıda verilen KAYNAKLAR kısmındaki bilgileri kullanarak kullanıcının sorusunu yanıtla. "
        "Eğer verilen kaynaklarda cevap yoksa veya emin değilsen 'Üzgünüm, bu konu hakkında bilgim yok.' de. "
        "Kendi kendine bilgi uydurma veya PDF linkleri icat etme."
    )
    
    user_prompt = f"KAYNAKLAR:\n{context}\n\nSORU: {query}"
    
    payload = {
        "model": "default",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 512
    }
    
    try:
        response = requests.post(SGLANG_URL, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[Hata] SGLang sunucusuna bağlanılamadı: {e}"

def main():
    print("="*60)
    print(" İNÖNÜ AI - RAG SOHBET ARAYÜZÜ ".center(60, "█"))
    print(" Çıkmak için 'q' veya 'exit' yazın ".center(60, "="))
    print("="*60)
    
    retriever = Retriever()
    
    while True:
        query = input("\nSoru: ").strip()
        if query.lower() in ["q", "exit", "çıkış"]:
            break
        if not query:
            continue
            
        print("🔍 Veritabanında aranıyor...")
        docs = retriever.search(query, top_k=3)
        
        if not docs:
            print("⚠️ Veritabanında ilgili hiçbir bilgi bulunamadı.")
            continue
            
        print("🤖 Cevap oluşturuluyor...")
        answer = generate_answer(query, docs)
        
        print(f"\n{'-'*60}\nİnönü Asistan: {answer}\n{'-'*60}")
        print("Kullanılan Kaynaklar:")
        for doc in docs:
            print(f"- {doc['source_url']} (Skor: {doc['score']:.2f})")

if __name__ == "__main__":
    main()
