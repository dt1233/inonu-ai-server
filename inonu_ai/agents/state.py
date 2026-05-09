#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İnönü AI — Agent State v3
"""

from typing import TypedDict


class AgentState(TypedDict):
    question:           str    # Kullanıcının orijinal sorusu
    rewritten_question: str    # Query rewriter çıktısı
    session_id:         str    # Redis oturum ID'si
    history:            list   # Oturum geçmişi
    route:              str    # "rag" | "direct"
    documents:          list   # Re-rank sonrası chunk'lar
    answer:             str    # Üretilen yanıt
    grade:              str    # "useful" | "not_useful"
    iterations:         int    # Kaç kez denendiği