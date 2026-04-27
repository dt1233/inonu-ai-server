#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İnönü AI — Agent Terminal Test v2
Session Memory + Semantic Cache + HyDE + Re-Rank
Kullanım: python test_agent.py
"""

import sys
sys.path.insert(0, '/home/yapayzeka/inonu-proje/inonu_ai')

from data_pipeline.indexer import encode_batch
from memory.session_manager import new_session, add_turn, build_history_prompt
from memory.semantic_cache import get_cached, set_cache

# Bağlama bağımlı kısa sorgular cache'lenmemeli
MIN_CACHE_LEN    = 10
CONTEXT_KEYWORDS = [
    "nasıl", "ne zaman", "nerede", "hangi", "kaç",
    "bu", "o", "onun", "bunun", "peki", "ya",
]

print("Sistem başlatılıyor...")
print("bge-m3 yükleniyor...")
encode_batch(["başlatma"])
print("Graf derleniyor...")

from agents.graph import get_graph

print("✓ Hazır!\n")

graph      = get_graph()
session_id = new_session()


def should_cache(soru: str) -> bool:
    """Bu sorgu cache'lenmeli mi?"""
    s = soru.strip().lower()
    if len(s) < MIN_CACHE_LEN:
        return False
    for kw in CONTEXT_KEYWORDS:
        if s.startswith(kw):
            return False
    return True


def ask(soru: str) -> str:
    q_vec = encode_batch([soru])["dense"][0]

    # 1. Semantic Cache kontrolü
    if should_cache(soru):
        cached = get_cached(soru, q_vec)
        if cached:
            print("  [CACHE HIT]")
            # Cache hit olsa bile session'a yaz — bağlam korunsun
            add_turn(session_id, soru, cached)
            return cached

    # 2. Oturum geçmişini çek
    history = build_history_prompt(session_id)

    # 3. Graf çalıştır
    initial = {
        "question":   soru,
        "session_id": session_id,
        "history":    history,
        "route":      "",
        "documents":  [],
        "answer":     "",
        "grade":      "",
        "iterations": 0,
    }
    result = graph.invoke(initial)
    yanit  = result.get("answer", "Bu konuda bilgim bulunmuyor.")

    # 4. Oturum geçmişine ekle
    add_turn(session_id, soru, yanit)

    # 5. Cache'e yaz (uygunsa)
    if result.get("route") == "rag" and should_cache(soru):
        set_cache(soru, q_vec, yanit)

    return yanit


def main():
    print("=" * 55)
    print("  İNÖNÜ ÜNİVERSİTESİ — Akıllı Asistan v2")
    print(f"  Oturum: {session_id[:8]}...")
    print("  Çıkmak için: q")
    print("=" * 55 + "\n")

    while True:
        try:
            soru = input("Soru: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGörüşmek üzere!")
            break

        if not soru:
            continue
        if soru.lower() in ("q", "quit", "exit", "çıkış"):
            print("Görüşmek üzere!")
            break

        try:
            yanit = ask(soru)
            print(f"\nYanıt: {yanit}\n")
        except Exception as e:
            print(f"\nHata: {e}\n")

        print("-" * 55 + "\n")


if __name__ == "__main__":
    main()