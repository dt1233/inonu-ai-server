#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İnönü AI — Terminal Test
Kullanım: python test_sor.py
"""

import sys
import re
sys.path.insert(0, '/home/yapayzeka/inonu-proje/inonu_ai')

from data_pipeline.indexer import Indexer, encode_batch
from openai import OpenAI

SGLANG_BASE_URL = "http://localhost:30000/v1"
SGLANG_MODEL    = "/home/yapayzeka/models/Qwen3-8B"
TOP_K           = 5
MAX_TOKENS      = 512

SYSTEM_PROMPT = """Rol: İnönü Üniversitesi Öğrenci İşleri yapay zeka asistanısın.

Yanıt kuralları:
1. Yalnızca Türkçe yaz
2. Yalnızca verilen BAĞLAM bilgisini kullan
3. Bağlamda cevap yoksa: "Bu konuda bilgim bulunmuyor." de
4. Üniversite adını daima "İnönü Üniversitesi" olarak yaz, başka türlü yazma
5. Kısa ve net ol"""

print("Sistem başlatılıyor...")
indexer = Indexer()
print("bge-m3 yükleniyor...")
encode_batch(["başlatma"])
print("✓ Hazır!\n")

client = OpenAI(base_url=SGLANG_BASE_URL, api_key="EMPTY")


def clean(text: str) -> str:
    # <think> bloklarını temizle
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # "Sen " ile başlayan cümleleri düzelt
    text = re.sub(r"(?i)\bSen\s+[İI]n[oö]n[üu]\b", "İnönü", text)
    text = re.sub(r"(?i)\b[İI]nanu\b", "İnönü", text)
    # Satır başında "Sen " varsa kaldır
    text = re.sub(r"(?m)^Sen\s+", "", text)
    return text.strip()


def search(query: str) -> list:
    out = encode_batch([query])
    res = indexer.client.query_points(
        collection_name="inonu_docs",
        query=out["dense"][0],
        using="dense",
        limit=TOP_K,
        with_payload=True,
    )
    return res.points


def ask(soru: str) -> str:
    points = search(soru)
    if not points:
        return "Bu konuda bilgim bulunmuyor."

    baglam = "\n\n".join(
        f"[{p.payload.get('source_key', '')}]\n{p.payload.get('text', '')}"
        for p in points
    )

    user_msg = (
        f"BAĞLAM:\n{baglam}\n\n"
        f"SORU: {soru}\n\n"
        f"YANIT (Türkçe, yalnızca bağlamdaki bilgilerle, "
        f"üniversite adı 'İnönü Üniversitesi' olmalı):"
    )

    resp = client.chat.completions.create(
        model=SGLANG_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=MAX_TOKENS,
        temperature=0.1,
        extra_body={
            "chat_template_kwargs": {"enable_thinking": False},
            "skip_special_tokens": True,
        },
    )
    return clean(resp.choices[0].message.content or "")


def main():
    print("=" * 55)
    print("  İNÖNÜ ÜNİVERSİTESİ — Öğrenci Asistanı")
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