#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İnönü AI — Bellek Yönetim Modülü
Session Manager ve Semantic Cache için birleştirici facade.

Bu modül, memory/ paketindeki bileşenleri tek noktadan erişime açar.
"""

from memory.session_manager import (
    new_session,
    get_history,
    add_turn,
    build_history_prompt,
    delete_session,
)
from memory.semantic_cache import (
    get_cached,
    set_cache,
    cache_stats,
)

__all__ = [
    # Session
    "new_session",
    "get_history",
    "add_turn",
    "build_history_prompt",
    "delete_session",
    # Cache
    "get_cached",
    "set_cache",
    "cache_stats",
]
