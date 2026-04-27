#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İnönü AI — Agent Nodes v3
Router, Query Rewriter, Retriever (HyDE + Re-Rank), Generator, Grader
"""

import re
import sys
sys.path.insert(0, '/home/yapayzeka/inonu-proje/inonu_ai')

from openai import OpenAI
from data_pipeline.indexer import Indexer, encode_batch
from tools.reranker import rerank
from .state import AgentState

SGLANG_BASE_URL = "http://localhost:30000/v1"
SGLANG_MODEL    = "/home/yapayzeka/models/Qwen3-8B"
TOP_K_RETRIEVE  = 20
TOP_K_RERANK    = 3
MAX_TOKENS      = 600
MAX_ITERATIONS  = 2

SKIP_URL_PATTERNS = [
    "type=get", "type=list", "servlet/announcement",
    "servlet/content", "servlet/staff", "servlet/menu",
]

_client  = None
_indexer = None

def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=SGLANG_BASE_URL, api_key="EMPTY")
    return _client

def get_indexer() -> Indexer:
    global _indexer
    if _indexer is None:
        _indexer = Indexer()
    return _indexer


REPLACEMENTS = [
    (r"<think>.*?</think>",         "",       re.DOTALL),
    (r"(?i)\bSen\s+[İIiı]n[oö]nü", "İnönü",  0),
    (r"(?i)\b[İIiı]nanu\b",        "İnönü",  0),
    (r"\bInönü\b",                  "İnönü",  0),
    (r"(?m)^Sen\s+",                "",       0),
]

def clean(text: str) -> str:
    for pattern, repl, flags in REPLACEMENTS:
        text = re.sub(pattern, repl, text, flags=flags)
    return text.strip()


def llm(messages: list, max_tokens: int = 200, temperature: float = 0.1) -> str:
    resp = get_client().chat.completions.create(
        model=SGLANG_MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        extra_body={
            "chat_template_kwargs": {"enable_thinking": False},
            "skip_special_tokens": True,
        },
    )
    return clean(resp.choices[0].message.content or "")


# ─── NODE 1: Router ───────────────────────────────────────────────
ROUTER_PROMPT = """Bir üniversite öğrenci işleri asistanısın.
Kullanıcının sorusunu analiz et ve yalnızca tek kelime yanıt ver.

"rag" → şu durumlarda:
- Kişi adı, personel, iletişim bilgisi soruluyor
- Tarih, takvim, sınav, başvuru soruluyor
- Program, ders, yönetmelik soruluyor
- Üniversite hakkında herhangi bir bilgi soruluyor
- Ne zaman, nerede, nasıl, kim gibi sorular

"direct" → YALNIZCA şu durumlarda:
- Sadece selamlama (merhaba, selam, günaydın, iyi günler, naber)
- Teşekkür veya vedalaşma (teşekkürler, görüşürüz, hoşça kal)
- Kişisel yorum veya iltifat (çok iyisin, harikasın)
- Üniversiteyle hiçbir ilgisi olmayan duygusal veya anlamsız ifadeler"""

def router_node(state: AgentState) -> AgentState:
    soru  = state["question"]
    yanit = llm(
        messages=[
            {"role": "system", "content": ROUTER_PROMPT},
            {"role": "user",   "content": f"Soru: {soru}\nYanıt (sadece 'rag' veya 'direct'):"},
        ],
        max_tokens=10,
        temperature=0.0,
    ).strip().lower()

    route = "direct" if "direct" in yanit else "rag"
    return {**state, "route": route}


# ─── NODE 2: Query Rewriter ───────────────────────────────────────
REWRITER_PROMPT = """Bir üniversite asistanı için sorgu yeniden yazma yapıyorsun.

Konuşma geçmişine bakarak kullanıcının mevcut sorusunu bağımsız ve tam bir soruya dönüştür.
Soru zaten tam ve bağımsızsa olduğu gibi bırak.
Yalnızca yeniden yazılmış soruyu döndür, başka hiçbir şey yazma.

Örnekler:
Geçmiş: "erasmus nedir" → "Erasmus değişim programıdır..."
Soru: "nasıl başvurulur"
Yeniden yazılmış: "Erasmus programına nasıl başvurulur?"

Geçmiş: "tacettin kimdir" → "Tacettin KOYUNOĞLU daire başkanıdır..."
Soru: "iletişim bilgileri"
Yeniden yazılmış: "Tacettin KOYUNOĞLU iletişim bilgileri nedir?"

Geçmiş: yok
Soru: "yatay geçiş şartları nelerdir"
Yeniden yazılmış: "yatay geçiş şartları nelerdir" """

def query_rewriter_node(state: AgentState) -> AgentState:
    soru    = state["question"]
    history = state.get("history", [])

    # Geçmiş yoksa veya soru zaten yeterliyse rewrite atla
    if not history or len(soru.split()) > 6:
        return {**state, "rewritten_question": soru}

    # Son 2 tur geçmişi özetle
    gecmis_ozet = ""
    for msg in history[-4:]:
        rol   = "Kullanıcı" if msg["role"] == "user" else "Asistan"
        icerik = msg["content"][:150]
        gecmis_ozet += f"{rol}: {icerik}\n"

    rewritten = llm(
        messages=[
            {"role": "system", "content": REWRITER_PROMPT},
            {"role": "user",   "content": (
                f"Geçmiş:\n{gecmis_ozet}\n"
                f"Mevcut soru: {soru}\n"
                f"Yeniden yazılmış soru:"
            )},
        ],
        max_tokens=60,
        temperature=0.0,
    ).strip()

    # Güvenlik: çok uzun veya boş çıktıyı filtrele
    if not rewritten or len(rewritten) > 200:
        rewritten = soru

    return {**state, "rewritten_question": rewritten}


# ─── NODE 3: Retriever (HyDE + Re-Rank) ──────────────────────────
HYDE_PROMPT = """Bir üniversite bilgi tabanında arama yapacaksın.
Verilen sorunun cevabı nasıl görünürdü diye kısa ve bilgilendirici
bir hipotetik cevap yaz (2-3 cümle).
Bu cevap, veritabanında benzer içerikleri bulmak için kullanılacak."""

def retriever_node(state: AgentState) -> AgentState:
    # Rewrite edilmiş soruyu kullan, yoksa orijinal soru
    soru = state.get("rewritten_question") or state["question"]

    # HyDE: hipotetik cevap üret
    hyde_cevap = llm(
        messages=[
            {"role": "system", "content": HYDE_PROMPT},
            {"role": "user",   "content": f"Soru: {soru}\nHipotetik cevap:"},
        ],
        max_tokens=150,
        temperature=0.3,
    )

    # HyDE cevabının vektörünü al
    out = encode_batch([hyde_cevap])
    vec = out["dense"][0]

    # Qdrant'tan top-20 çek
    res = get_indexer().client.query_points(
        collection_name="inonu_docs",
        query=vec,
        using="dense",
        limit=TOP_K_RETRIEVE,
        with_payload=True,
    )

    # Re-rank: top-20 → top-3
    reranked = rerank(soru, res.points, top_n=TOP_K_RERANK)
    return {**state, "documents": reranked}


# ─── NODE 4: Generator ────────────────────────────────────────────
GENERATOR_SYSTEM = """Rol: İnönü Üniversitesi Öğrenci İşleri yapay zeka asistanısın.

Kurallar:
1. Yalnızca Türkçe yaz
2. Yalnızca verilen BAĞLAM bilgisini kullan, asla uydurma
3. Bağlamda cevap yoksa: "Bu konuda bilgim bulunmuyor." yaz
4. Üniversite adını daima "İnönü Üniversitesi" yaz
5. Teknik kaynak adları (duyurular_api vb.) yanıtta geçmesin
6. Kısa ve net ol"""

DIRECT_SYSTEM = """İnönü Üniversitesi Öğrenci İşleri yapay zeka asistanısın.
Selamlama, iltifat ve vedalaşmalara kısa ve samimi Türkçe yanıt ver.
Üniversiteyle ilgisi olmayan konularda: "Yalnızca öğrenci işleri konularında yardımcı olabilirim." de."""

def generator_node(state: AgentState) -> AgentState:
    soru    = state["question"]           # Orijinal soru gösterilsin
    route   = state.get("route", "rag")
    history = state.get("history", [])

    if route == "direct":
        messages = [{"role": "system", "content": DIRECT_SYSTEM}]
        messages += history[-4:]
        messages.append({"role": "user", "content": soru})
        yanit = llm(messages=messages, max_tokens=150)
        return {**state, "answer": yanit}

    docs = state.get("documents", [])
    if not docs:
        return {**state, "answer": "Bu konuda bilgim bulunmuyor."}

    baglam = "\n\n".join(
        f"[Kaynak {i+1}]\n{p.payload.get('text', '')}"
        for i, p in enumerate(docs)
    )

    links = []
    seen  = set()
    for p in docs:
        for url in p.payload.get("pdf_links", []):
            if not url or not url.startswith("http"):
                continue
            if any(s in url for s in SKIP_URL_PATTERNS):
                continue
            if url not in seen:
                links.append(url)
                seen.add(url)

    messages = [{"role": "system", "content": GENERATOR_SYSTEM}]
    messages += history[-4:]
    messages.append({
        "role": "user",
        "content": (
            f"BAĞLAM:\n{baglam}\n\n"
            f"SORU: {soru}\n\n"
            f"YANIT (Türkçe, üniversite adı 'İnönü Üniversitesi'):"
        )
    })

    yanit = llm(messages=messages, max_tokens=MAX_TOKENS)

    if links:
        yanit += "\n\n📎 İlgili belgeler:\n" + "\n".join(f"- {u}" for u in links[:3])

    return {**state, "answer": yanit}


# ─── NODE 5: Grader ───────────────────────────────────────────────
GRADER_PROMPT = """Bir yanıtın kalitesini değerlendir.
Yalnızca tek kelime yanıt ver: "useful" veya "not_useful"

"useful"     → yanıt soruyu Türkçe ve doğru biçimde yanıtlıyor
"not_useful" → yanıt soruyla alakasız, boş veya "bilgim bulunmuyor" içeriyor"""

def grader_node(state: AgentState) -> AgentState:
    soru  = state["question"]
    yanit = state.get("answer", "")
    iters = state.get("iterations", 0) + 1

    grade = llm(
        messages=[
            {"role": "system", "content": GRADER_PROMPT},
            {"role": "user",   "content": (
                f"Soru: {soru}\n"
                f"Yanıt: {yanit}\n"
                f"Değerlendirme (sadece 'useful' veya 'not_useful'):"
            )},
        ],
        max_tokens=10,
        temperature=0.0,
    ).strip().lower()

    grade = "useful" if "useful" in grade else "not_useful"
    return {**state, "grade": grade, "iterations": iters}