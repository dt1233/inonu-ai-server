#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İnönü AI — JWT Kimlik Doğrulama Modülü
Token üretme, doğrulama ve kullanıcı yetkilendirme
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from loguru import logger

from config import get_settings

_settings = get_settings()

# ─── Şifre Hash'leme ──────────────────────────────────────────

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ─── Bearer Token Şeması ──────────────────────────────────────

security = HTTPBearer(
    scheme_name="JWT",
    description="JWT Bearer token. Login endpoint'inden alınır.",
)


def hash_password(password: str) -> str:
    """Şifreyi bcrypt ile hash'le."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Düz metin şifreyi hash ile karşılaştır."""
    return pwd_context.verify(plain_password, hashed_password)


# ─── JWT Token İşlemleri ───────────────────────────────────────

def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    JWT erişim token'ı oluştur.
    
    Args:
        data: Token payload'ına eklenecek veriler
        expires_delta: Token geçerlilik süresi
    
    Returns:
        Kodlanmış JWT token string'i
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=_settings.jwt_access_token_expire_minutes
        )

    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    })

    encoded_jwt = jwt.encode(
        to_encode,
        _settings.jwt_secret_key,
        algorithm=_settings.jwt_algorithm,
    )
    return encoded_jwt


def decode_token(token: str) -> dict:
    """
    JWT token'ı çöz ve payload'ı döndür.
    
    Raises:
        HTTPException: Token geçersiz veya süresi dolmuşsa
    """
    try:
        payload = jwt.decode(
            token,
            _settings.jwt_secret_key,
            algorithms=[_settings.jwt_algorithm],
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token süresi dolmuş. Lütfen yeniden giriş yapın.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz token. Lütfen yeniden giriş yapın.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ─── Kullanıcı Doğrulama ──────────────────────────────────────

def authenticate_user(username: str, password: str) -> Optional[dict]:
    """
    Kullanıcı adı ve şifre ile kimlik doğrulama.
    Şu an için .env'deki admin bilgileri kullanılıyor.
    İleride veritabanı entegrasyonu yapılabilir.
    """
    if username == _settings.admin_username and password == _settings.admin_password:
        logger.info(f"Başarılı giriş: {username}")
        return {"username": username, "role": "admin"}

    logger.warning(f"Başarısız giriş denemesi: {username}")
    return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    FastAPI Dependency — Her korumalı endpoint'ten önce çalışır.
    Bearer token'ı doğrular ve kullanıcı bilgisini döndürür.
    """
    payload = decode_token(credentials.credentials)

    username = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token'da kullanıcı bilgisi bulunamadı.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {"username": username, "role": payload.get("role", "user")}
