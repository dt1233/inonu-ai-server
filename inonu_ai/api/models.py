#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İnönü AI — Pydantic Request/Response Modelleri
API endpoint'leri için veri doğrulama şemaları
"""

from pydantic import BaseModel, Field
from typing import Optional


# ─── Auth Modelleri ─────────────────────────────────────────────

class LoginRequest(BaseModel):
    """Kullanıcı giriş isteği."""
    username: str = Field(..., min_length=1, description="Kullanıcı adı")
    password: str = Field(..., min_length=1, description="Şifre")


class TokenResponse(BaseModel):
    """JWT token yanıtı."""
    access_token: str = Field(..., description="JWT erişim token'ı")
    token_type: str = Field(default="bearer", description="Token türü")
    expires_in: int = Field(..., description="Token geçerlilik süresi (saniye)")


# ─── Soru-Cevap Modelleri ───────────────────────────────────────

class AskRequest(BaseModel):
    """Soru sorma isteği."""
    question: str = Field(
        ..., min_length=1, max_length=1000,
        description="Kullanıcının sorusu"
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Oturum ID'si (çok turlu konuşma için)"
    )


class SourceItem(BaseModel):
    """Kaynak öğesi."""
    source_url: str = Field(default="", description="Kaynak URL'si")
    pdf_url: str = Field(default="", description="Varsa PDF bağlantısı")
    title: str = Field(default="", description="Kaynak başlığı")
    fakulte: str = Field(default="", description="Orijinal fakülte bilgisi")
    source_fakulte: str = Field(default="", description="URL'den çekilen fakülte")
    detected_fakulte: str = Field(default="", description="İçerikten tespit edilen fakülte")
    doc_type: str = Field(default="", description="Doküman türü (announcement, pdf_page vb.)")
    page_no: Optional[int] = Field(default=None, description="PDF sayfa numarası")
    score: float = Field(default=0.0, description="Nihai skor")
    retrieval_score: float = Field(default=0.0, description="Qdrant skoru")
    rerank_score: Optional[float] = Field(default=None, description="Reranker skoru")


class AskResponse(BaseModel):
    """Soru-cevap yanıtı."""
    answer: str = Field(..., description="Yapay zeka yanıtı")
    session_id: str = Field(..., description="Oturum ID'si")
    route: str = Field(..., description="Kullanılan yol (rag/direct)")
    cached: bool = Field(default=False, description="Cache'den mi geldi?")
    response_time: float = Field(..., description="Yanıt süresi (saniye)")
    sources: list[SourceItem] = Field(default_factory=list, description="Kullanılan kaynaklar")


# ─── Oturum Modelleri ──────────────────────────────────────────

class SessionResponse(BaseModel):
    """Oturum bilgisi yanıtı."""
    session_id: str
    history: list[dict] = Field(default_factory=list)
    message_count: int = Field(default=0)


class NewSessionResponse(BaseModel):
    """Yeni oturum yanıtı."""
    session_id: str
    message: str = Field(default="Yeni oturum oluşturuldu")


# ─── Sistem Modelleri ──────────────────────────────────────────

class HealthResponse(BaseModel):
    """Sağlık kontrolü yanıtı."""
    status: str = Field(default="healthy")
    version: str = Field(default="1.0.0")
    service: str = Field(default="İnönü AI Asistanı")


class StatsResponse(BaseModel):
    """Sistem istatistikleri yanıtı."""
    qdrant: Optional[dict] = None
    cache: Optional[dict] = None
    status: str = Field(default="ok")


# ─── Hata Modelleri ────────────────────────────────────────────

class ErrorResponse(BaseModel):
    """Hata yanıtı."""
    detail: str
    error_code: Optional[str] = None
