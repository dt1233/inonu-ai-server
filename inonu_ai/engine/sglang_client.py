#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İnönü AI — SGLang LLM İstemcisi
OpenAI-uyumlu API üzerinden Qwen3 modeline erişim
"""

import re
from typing import Optional

from openai import OpenAI
from loguru import logger
from config import get_settings

_settings = get_settings()

_client: Optional[OpenAI] = None

# ─── Yanıt Temizleme Kuralları ─────────────────────────────────

REPLACEMENTS = [
    (r"<think>.*?</think>",         "",       re.DOTALL),
    (r"(?i)\bSen\s+[İIiı]n[oö]nü", "İnönü",  0),
    (r"(?i)\b[İIiı]nanu\b",        "İnönü",  0),
    (r"\bInönü\b",                  "İnönü",  0),
    (r"(?m)^Sen\s+",                "",       0),
]


def get_client() -> OpenAI:
    """SGLang OpenAI-uyumlu istemci (singleton)."""
    global _client
    if _client is None:
        logger.info(f"SGLang istemcisi oluşturuluyor → {_settings.sglang_base_url}")
        _client = OpenAI(
            base_url=_settings.sglang_base_url,
            api_key="EMPTY",
        )
        logger.info("SGLang istemcisi hazır ✓")
    return _client


def clean(text: str) -> str:
    """LLM yanıtından <think> bloklarını ve hatalı isimleri temizle."""
    for pattern, repl, flags in REPLACEMENTS:
        text = re.sub(pattern, repl, text, flags=flags)
    return text.strip()


def llm(
    messages: list,
    max_tokens: int = 200,
    temperature: float = 0.1,
    model: Optional[str] = None,
) -> str:
    """
    SGLang/vLLM üzerinden chat completion çağrısı.

    Args:
        messages: OpenAI formatında mesaj listesi
        max_tokens: Maksimum üretilecek token sayısı
        temperature: Yaratıcılık parametresi (0.0-1.0)
        model: Model adı (varsayılan: config'den)

    Returns:
        Temizlenmiş yanıt metni
    """
    resp = get_client().chat.completions.create(
        model=model or _settings.sglang_model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        extra_body={
            "chat_template_kwargs": {"enable_thinking": False},
            "skip_special_tokens": True,
        },
    )
    return clean(resp.choices[0].message.content or "")
