#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İnönü AI — FastAPI Ana Uygulama
JWT korumalı REST API — Üniversite AI Asistanı
"""

import time
from datetime import timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from config import get_settings
from .auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
)
from .models import (
    LoginRequest,
    TokenResponse,
    AskRequest,
    AskResponse,
    NewSessionResponse,
    SessionResponse,
    HealthResponse,
    StatsResponse,
    ErrorResponse,
)

_settings = get_settings()

# ─── Uygulama Yaşam Döngüsü ───────────────────────────────────

_start_time: float = 0.0
_graph = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Uygulama başlatma ve kapatma işlemleri."""
    global _start_time, _graph
    _start_time = time.time()
    logger.info("═══ İnönü AI API başlatılıyor ═══")

    # LangGraph'ı ön-yükle (ilk istek gecikmesini önler)
    try:
        from agents.graph import get_graph
        _graph = get_graph()
        logger.info("LangGraph ajan grafiği hazır ✓")
    except Exception as e:
        logger.warning(f"Graf ön-yükleme atlandı: {e}")

    logger.info(f"API hazır → http://{_settings.app_host}:{_settings.app_port}")
    logger.info("═══ İnönü AI API başlatıldı ═══")

    yield

    logger.info("═══ İnönü AI API kapatılıyor ═══")


# ─── FastAPI Uygulaması ────────────────────────────────────────

app = FastAPI(
    title="İnönü AI — Öğrenci İşleri Asistanı",
    description=(
        "İnönü Üniversitesi Öğrenci İşleri Daire Başkanlığı için "
        "yapay zeka destekli soru-cevap API'si. "
        "RAG (Retrieval-Augmented Generation) tabanlı akıllı asistan."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS ayarları
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── ENDPOINT: Sağlık Kontrolü (Açık) ─────────────────────────

@app.get(
    "/api/health",
    response_model=HealthResponse,
    tags=["Sistem"],
    summary="Sağlık Kontrolü",
)
async def health_check():
    """Sistemin çalışıp çalışmadığını kontrol eder. Token gerektirmez."""
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        service="İnönü AI Asistanı",
    )


# ─── ENDPOINT: Giriş & Token Alma ─────────────────────────────

@app.post(
    "/api/auth/login",
    response_model=TokenResponse,
    tags=["Kimlik Doğrulama"],
    summary="Giriş Yap & JWT Token Al",
    responses={401: {"model": ErrorResponse}},
)
async def login(request: LoginRequest):
    """
    Kullanıcı adı ve şifre ile giriş yaparak JWT token alır.

    Bu token, korumalı endpoint'lere erişim için gereklidir.
    Token'ı `Authorization: Bearer <token>` başlığında gönderin.
    """
    user = authenticate_user(request.username, request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kullanıcı adı veya şifre hatalı.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    expire_minutes = _settings.jwt_access_token_expire_minutes
    access_token = create_access_token(
        data={"sub": user["username"], "role": user["role"]},
        expires_delta=timedelta(minutes=expire_minutes),
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expire_minutes * 60,
    )


# ─── ENDPOINT: Soru Sor (JWT Korumalı) ────────────────────────

@app.post(
    "/api/ask",
    response_model=AskResponse,
    tags=["Soru-Cevap"],
    summary="Yapay Zekaya Soru Sor",
    responses={401: {"model": ErrorResponse}},
)
async def ask_question(
    request: AskRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    JWT korumalı soru-cevap endpoint'i.

    Yapay zeka, İnönü Üniversitesi Öğrenci İşleri veritabanından
    bilgi çekerek sorunuza yanıt verir.
    """
    t0 = time.time()

    # Oturum yönetimi
    from memory.session_manager import (
        new_session, get_history, add_turn, build_history_prompt,
    )
    from memory.semantic_cache import get_cached, set_cache
    from data_pipeline.indexer import encode_batch
    from agents.graph import get_graph

    session_id = request.session_id
    if not session_id:
        session_id = new_session()

    soru = request.question
    cached = False
    route = ""

    # 1. Semantic Cache kontrolü
    try:
        q_vec = encode_batch([soru])["dense"][0]
        cached_answer = get_cached(soru, q_vec)
        if cached_answer:
            cached = True
            add_turn(session_id, soru, cached_answer)
            return AskResponse(
                answer=cached_answer,
                session_id=session_id,
                route="cache",
                cached=True,
                response_time=round(time.time() - t0, 3),
            )
    except Exception as e:
        logger.warning(f"Cache kontrolü atlandı: {e}")

    # 2. LangGraph ile soru-cevap
    try:
        history = build_history_prompt(session_id)
    except Exception:
        history = []

    graph = get_graph()
    initial = {
        "question":           soru,
        "rewritten_question": "",
        "session_id":         session_id,
        "history":            history,
        "route":              "",
        "documents":          [],
        "answer":             "",
        "grade":              "",
        "iterations":         0,
    }

    result = graph.invoke(initial)
    yanit = result.get("answer", "Bu konuda bilgim bulunmuyor.")
    route = result.get("route", "rag")

    # 3. Oturum ve cache güncelle
    try:
        add_turn(session_id, soru, yanit)
    except Exception as e:
        logger.warning(f"Oturum güncellenemedi: {e}")

    try:
        if route == "rag" and q_vec:
            set_cache(soru, q_vec, yanit)
    except Exception as e:
        logger.warning(f"Cache yazılamadı: {e}")

    elapsed = round(time.time() - t0, 3)
    logger.info(
        f"[{current_user['username']}] Soru: {soru[:50]}... | "
        f"Rota: {route} | Süre: {elapsed}s"
    )

    return AskResponse(
        answer=yanit,
        session_id=session_id,
        route=route,
        cached=False,
        response_time=elapsed,
    )


# ─── ENDPOINT: Yeni Oturum (JWT Korumalı) ─────────────────────

@app.post(
    "/api/session/new",
    response_model=NewSessionResponse,
    tags=["Oturum Yönetimi"],
    summary="Yeni Oturum Başlat",
)
async def create_session(
    current_user: dict = Depends(get_current_user),
):
    """Yeni bir sohbet oturumu başlatır."""
    from memory.session_manager import new_session
    session_id = new_session()
    return NewSessionResponse(session_id=session_id)


# ─── ENDPOINT: Oturum Geçmişi (JWT Korumalı) ──────────────────

@app.get(
    "/api/session/{session_id}",
    response_model=SessionResponse,
    tags=["Oturum Yönetimi"],
    summary="Oturum Geçmişini Görüntüle",
)
async def get_session_history(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Belirtilen oturumun sohbet geçmişini döndürür."""
    from memory.session_manager import get_history
    history = get_history(session_id)
    return SessionResponse(
        session_id=session_id,
        history=history,
        message_count=len(history),
    )


# ─── ENDPOINT: Sistem İstatistikleri (JWT Korumalı) ────────────

@app.get(
    "/api/stats",
    response_model=StatsResponse,
    tags=["Sistem"],
    summary="Sistem İstatistikleri",
)
async def get_stats(
    current_user: dict = Depends(get_current_user),
):
    """Qdrant ve cache istatistiklerini döndürür."""
    qdrant_info = None
    cache_info = None

    try:
        from data_pipeline.indexer import Indexer
        indexer = Indexer()
        qdrant_info = indexer.collection_info()
    except Exception as e:
        qdrant_info = {"error": str(e)}

    try:
        from memory.semantic_cache import cache_stats
        cache_info = cache_stats()
    except Exception as e:
        cache_info = {"error": str(e)}

    return StatsResponse(
        qdrant=qdrant_info,
        cache=cache_info,
        status="ok",
    )


# ─── Doğrudan Çalıştırma ──────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=_settings.app_host,
        port=_settings.app_port,
        reload=True,
        log_level=_settings.log_level.lower(),
    )
