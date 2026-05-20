#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İnönü AI — Router Agent
Kullanıcı sorgusunu sınıflandırır: RAG mi yoksa direkt yanıt mı?
"""

from .nodes import router_node, ROUTER_PROMPT

__all__ = ["router_node", "ROUTER_PROMPT"]
