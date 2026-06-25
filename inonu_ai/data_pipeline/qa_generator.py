#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║  İNÖNÜ AI │ qa_generator.py                                     ║
║  Takım 2: Sentetik Soru-Cevap Veri Seti Üretimi                 ║
║                                                                  ║
║  Girdi : crawl_results.json (Takım 1 çıktısı)                   ║
║  Çıktı : egitim_verisi.json (ShareGPT formatı, Takım 3 girdisi) ║
║                                                                  ║
║  Motor : SGLang / vLLM (OpenAI-uyumlu API)                       ║
║  GPU   : L40S 50GB                                               ║
╚══════════════════════════════════════════════════════════════════╝

Kullanım:
  python -m inonu_ai.data_pipeline.qa_generator --input crawl_results.json
  python -m inonu_ai.data_pipeline.qa_generator --resume  # kaldığı yerden devam
"""

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from loguru import logger

# ─────────────────────────────────────────────────────────────────
# SABİTLER
# ─────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "Sen İnönü Üniversitesi'nin resmi yapay zeka asistanısın. "
    "Adın 'İnönü Asistan'. Öğrencilere, akademisyenlere ve personele "
    "üniversiteyle ilgili her konuda yardımcı olursun. "
    "Yanıtların her zaman doğru, güncel ve saygılı olmalıdır. "
    "Bilmediğin konularda bunu açıkça belirt."
)

QA_GENERATION_PROMPT = """Aşağıdaki metni dikkatlice oku. Bu metin İnönü Üniversitesi'ne ait resmi bir kaynaktan alınmıştır.

Bu metne dayanarak, bir üniversite öğrencisinin veya personelinin sorabileceği {qa_count} adet soru-cevap çifti üret.

KURALLAR:
1. Sorular çok çeşitli olmalı (Nasıl, Kim, Nerede, Listeleyebilir misin, Farkı nedir, Neden?).
2. Sorular doğrudan ve doğal bir insan ağzından sorulmalı (örn: "Tıp fakültesi dekanı kim?").
3. Cevaplar SADECE verilen metindeki bilgilere dayanmalı. Uydurma bilgi YASAK.
4. Her soru-cevap çifti birbirinden tamamen farklı açılardan sorulmalı (Tekrarlardan kaçın).
5. Kısa "evet/hayır" soruları yerine açıklayıcı sorular tercih et.

METİN:
---
{context}
---

ÇIKTI FORMATI (Kesinlikle bu JSON formatında yaz, başka hiçbir şey ekleme):
[
  {{"soru": "...", "cevap": "..."}},
  {{"soru": "...", "cevap": "..."}}
]"""

# Chunk kategorisine göre üretilecek QA sayısı (Agresif Mod)
QA_COUNTS = {
    "duyuru":          6,
    "statik":          8,
    "avesis_personel": 5,
    "kisi":            4,
    "default":         5,
}

# Kalite filtreleri
MIN_QUESTION_LEN = 15
MIN_ANSWER_LEN   = 20
MAX_ANSWER_LEN   = 2000

# API ayarları
DEFAULT_API_URL   = os.getenv("SGLANG_BASE_URL", "http://localhost:30000/v1")
DEFAULT_MODEL     = os.getenv("SGLANG_MODEL", "/home/yapayzeka/models/Qwen3-8B")
MAX_CONCURRENT    = int(os.getenv("QA_MAX_CONCURRENT", "8"))
MAX_RETRIES       = 3
RETRY_DELAY       = 2.0
REQUEST_TIMEOUT   = 120.0

# Dosya yolları
DEFAULT_INPUT     = "crawl_results.json"
DEFAULT_OUTPUT    = "egitim_verisi.json"
CHECKPOINT_FILE   = "qa_checkpoint.json"
RAW_QA_FILE       = "qa_raw_pairs.jsonl"


# ─────────────────────────────────────────────────────────────────
# VERİ YAPILARI
# ─────────────────────────────────────────────────────────────────

@dataclass
class QAPair:
    instruction: str   # soru
    output: str        # cevap
    source_key: str    # kaynak chunk key
    source_url: str    # kaynak URL
    category: str      # duyuru / statik / avesis_personel
    chunk_hash: str    # mükerrer kontrolü için


@dataclass
class ShareGPTEntry:
    conversations: list = field(default_factory=list)

    def add_turn(self, role: str, content: str):
        mapping = {"system": "system", "human": "human", "assistant": "gpt"}
        self.conversations.append({
            "from": mapping.get(role, role),
            "value": content,
        })

    def to_dict(self) -> dict:
        return {"conversations": self.conversations}


# ─────────────────────────────────────────────────────────────────
# CHUNK YÜKLEME (crawl_results.json → düz metin listesi)
# ─────────────────────────────────────────────────────────────────

def _hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]


def _staff_to_text(staff_list: list[dict]) -> str:
    lines = []
    for p in staff_list:
        parts = [p.get("ad_soyad", "")]
        for k, prefix in [("unvan",""), ("bolum","Bölüm"), ("departman",""),
                          ("gorev","Görev"), ("email","E-posta"), ("telefon","Tel"),
                          ("fakulte","Fakülte")]:
            val = p.get(k, "")
            if val and val.strip():
                parts.append(f"{prefix}: {val}" if prefix else val)
        lines.append(" | ".join(filter(None, parts)))
    return "\n".join(lines)


def _sss_to_text(sss_dict: dict) -> str:
    blocks = []
    for cat_data in sss_dict.values():
        title = cat_data.get("baslik", "")
        if title:
            blocks.append(f"## {title}")
        items = cat_data.get("content", [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    if item.get("baslik"):
                        blocks.append(f"### {item['baslik']}")
                    if item.get("icerik"):
                        blocks.append(item["icerik"])
    return "\n\n".join(blocks)


@dataclass
class ChunkForQA:
    text: str
    source_key: str
    source_url: str
    category: str
    label: str
    chunk_hash: str


def load_chunks_from_crawl_results(path: str) -> list[ChunkForQA]:
    """crawl_results.json veya scheduler çıktısını yükle ve düz metin chunk'larına dönüştür."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    chunks: list[ChunkForQA] = []

    # Eğer scheduler çıktısı (dict) ise
    if isinstance(data, dict):
        # Duyurular
        for rec in data.get("announcements", []):
            title = rec.get("title", "")
            content = rec.get("content", "")
            text = f"{title}\n\n{content}".strip()
            if len(text) < 50:
                continue
            chunks.append(ChunkForQA(
                text=text[:3000], source_key=rec.get("unit", "duyuru"),
                source_url=rec.get("sourceUrl", ""), category="duyuru",
                label=title[:80], chunk_hash=_hash(text),
            ))

        # Statik içerikler
        for rec in data.get("static_contents", []):
            content = rec.get("content")
            key = rec.get("key", "")
            label = rec.get("label", key)
            url = rec.get("url", "")

            if isinstance(content, list):
                text = f"{label}\n\n{_staff_to_text(content)}"
                cat = "statik"
            elif isinstance(content, dict):
                text = _sss_to_text(content)
                cat = "statik"
            elif isinstance(content, str) and content.strip():
                text = f"{label}\n\n{content}"
                cat = "statik"
            else:
                continue

            if len(text) < 50:
                continue
            chunks.append(ChunkForQA(
                text=text[:3000], source_key=key, source_url=url,
                category=cat, label=label[:80], chunk_hash=_hash(text),
            ))

        # AVESİS personel
        for rec in data.get("avesis_staff", []):
            staff_list = rec.get("content", [])
            if not staff_list:
                continue
            label = rec.get("label", "")
            text = f"{label} — Akademik Kadro\n\n{_staff_to_text(staff_list)}"
            if len(text) < 50:
                continue
            chunks.append(ChunkForQA(
                text=text[:3000], source_key=rec.get("key", ""),
                source_url=rec.get("url", ""), category="avesis_personel",
                label=label[:80], chunk_hash=_hash(text),
            ))

    # Eğer doğrudan chunk listesi ise
    elif isinstance(data, list):
        for item in data:
            text = item.get("text", "")
            if len(text) < 50:
                continue
            meta = item.get("metadata", {})
            chunks.append(ChunkForQA(
                text=text[:3000], source_key=item.get("source_key", ""),
                source_url=item.get("source_url", ""),
                category=meta.get("category", meta.get("kategori", "default")),
                label=meta.get("label", meta.get("baslik", ""))[:80],
                chunk_hash=_hash(text),
            ))

    logger.info(f"Yüklenen chunk sayısı: {len(chunks)}")
    return chunks


# ─────────────────────────────────────────────────────────────────
# LLM API İSTEMCİSİ (Asenkron, OpenAI-uyumlu)
# ─────────────────────────────────────────────────────────────────

class AsyncLLMClient:
    def __init__(self, base_url: str, model: str, max_concurrent: int = 8):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
        self._total_requests = 0
        self._total_tokens = 0

    async def generate(self, messages: list[dict], max_tokens: int = 1500,
                       temperature: float = 0.7) -> Optional[str]:
        """Tek bir chat completion isteği gönder."""
        async with self.semaphore:
            for attempt in range(MAX_RETRIES):
                try:
                    resp = await self.client.post(
                        f"{self.base_url}/chat/completions",
                        json={
                            "model": self.model,
                            "messages": messages,
                            "max_tokens": max_tokens,
                            "temperature": temperature,
                            "extra_body": {
                                "chat_template_kwargs": {"enable_thinking": False},
                                "skip_special_tokens": True,
                            },
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    self._total_requests += 1
                    usage = data.get("usage", {})
                    self._total_tokens += usage.get("total_tokens", 0)
                    return data["choices"][0]["message"]["content"]
                except Exception as e:
                    if attempt < MAX_RETRIES - 1:
                        wait = RETRY_DELAY * (2 ** attempt)
                        logger.warning(f"API hatası (deneme {attempt+1}): {e}. {wait:.0f}s beklenecek...")
                        await asyncio.sleep(wait)
                    else:
                        logger.error(f"API çağrısı başarısız ({MAX_RETRIES} deneme): {e}")
                        return None

    async def close(self):
        await self.client.aclose()

    @property
    def stats(self) -> dict:
        return {"requests": self._total_requests, "tokens": self._total_tokens}


# ─────────────────────────────────────────────────────────────────
# QA ÜRETİMİ VE KALİTE FİLTRESİ
# ─────────────────────────────────────────────────────────────────

def _fix_json_string(text: str) -> str:
    """Yaygın JSON bozukluklarını düzelt."""
    # Trailing comma: ,] veya ,} düzelt
    text = re.sub(r',\s*([\]\}])', r'\1', text)
    # Tek tırnak -> çift tırnak
    text = text.replace("'", '"')
    # Kontrol karakterlerini temizle
    text = re.sub(r'[\x00-\x1f]+', ' ', text)
    return text


def _extract_json_from_response(text: str) -> Optional[list[dict]]:
    """Metin içerisinden JSON dizisini çıkar (Güçlendirilmiş)."""
    # 1. <think>...</think> bloğunu (varsa) tamamen temizle
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
    # Bazen model </think> tagını kapatmadan bırakır, o kısmı da temizle
    if '<think>' in text:
        text = text.split('</think>')[-1].strip() if '</think>' in text else re.sub(r'<think>.*', '', text, flags=re.DOTALL).strip()

    # 2. JSON bloğu bul (birden fazla strateji)
    patterns = [
        r"```json\s*(\[.*?\])\s*```",
        r"```\s*(\[.*?\])\s*```",
        r"(\[\s*\{.*?\}\s*\])",    # [{...}] kalıbı (daha spesifik)
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            candidate = match.group(1)
            # Direkt dene
            try:
                result = json.loads(candidate)
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass
            # Düzeltilmiş haliyle dene
            try:
                result = json.loads(_fix_json_string(candidate))
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                continue

    # 3. Tüm metni JSON olarak parse et
    for attempt_text in [text.strip(), _fix_json_string(text.strip())]:
        try:
            result = json.loads(attempt_text)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    # 4. Son çare: satır satır { } blokları topla
    try:
        items = []
        for m in re.finditer(r'\{[^{}]*"soru"[^{}]*"cevap"[^{}]*\}', text, re.DOTALL):
            try:
                obj = json.loads(_fix_json_string(m.group()))
                if isinstance(obj, dict) and "soru" in obj and "cevap" in obj:
                    items.append(obj)
            except json.JSONDecodeError:
                continue
        if items:
            return items
    except Exception:
        pass

    return None


def _quality_filter(pairs: list[dict]) -> list[dict]:
    """Kalite filtresinden geçir."""
    filtered = []
    for pair in pairs:
        q = pair.get("soru", "").strip()
        a = pair.get("cevap", "").strip()

        if len(q) < MIN_QUESTION_LEN:
            continue
        if len(a) < MIN_ANSWER_LEN:
            continue
        if len(a) > MAX_ANSWER_LEN:
            a = a[:MAX_ANSWER_LEN]

        # Türkçe karakter kontrolü (en az birkaç Türkçe karakter içermeli)
        turkish_chars = set("çÇğĞıİöÖşŞüÜ")
        if not any(c in turkish_chars for c in q + a):
            continue

        # Halüsinasyon belirtileri
        hallucination_markers = [
            "bilmiyorum", "emin değilim", "tahmin ediyorum",
            "sanırım", "muhtemelen", "olabilir",
        ]
        a_lower = a.lower()
        if any(marker in a_lower for marker in hallucination_markers):
            continue

        filtered.append({"soru": q, "cevap": a})

    return filtered


async def generate_qa_for_chunk(
    client: AsyncLLMClient, chunk: ChunkForQA
) -> list[QAPair]:
    """Tek bir chunk için QA çiftleri üret."""
    qa_count = QA_COUNTS.get(chunk.category, QA_COUNTS["default"])

    prompt = QA_GENERATION_PROMPT.format(
        qa_count=qa_count,
        context=chunk.text,
    )

    messages = [
        {"role": "system", "content": "Sen bir eğitim verisi üretme uzmanısın. Verilen metinlerden yüksek kaliteli soru-cevap çiftleri üretirsin. Çıktını her zaman geçerli JSON formatında ver."},
        {"role": "user", "content": prompt},
    ]

    response = await client.generate(messages, max_tokens=1500, temperature=0.3)
    if not response:
        return []

    raw_pairs = _extract_json_from_response(response)
    if not raw_pairs:
        logger.debug(f"JSON parse edilemedi [{chunk.label}]: {response[:100]}...")
        return []

    filtered = _quality_filter(raw_pairs)

    return [
        QAPair(
            instruction=p["soru"],
            output=p["cevap"],
            source_key=chunk.source_key,
            source_url=chunk.source_url,
            category=chunk.category,
            chunk_hash=chunk.chunk_hash,
        )
        for p in filtered
    ]


# ─────────────────────────────────────────────────────────────────
# CHECKPOINT SİSTEMİ (Kaldığı yerden devam)
# ─────────────────────────────────────────────────────────────────

def _load_checkpoint(path: str) -> set[str]:
    """İşlenmiş chunk hash'lerini yükle."""
    if not os.path.exists(path):
        return set()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return set(data.get("processed_hashes", []))


def _save_checkpoint(path: str, processed: set[str], stats: dict):
    """Checkpoint dosyasını güncelle."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "processed_hashes": list(processed),
            "stats": stats,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, f, ensure_ascii=False, indent=2)


def _append_raw_pairs(path: str, pairs: list[QAPair]):
    """Ham QA çiftlerini JSONL olarak ek dosyaya yaz (kayıp önleme)."""
    with open(path, "a", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps({
                "instruction": p.instruction,
                "output": p.output,
                "source_key": p.source_key,
                "source_url": p.source_url,
                "category": p.category,
                "chunk_hash": p.chunk_hash,
            }, ensure_ascii=False) + "\n")


# ─────────────────────────────────────────────────────────────────
# GOLDEN DATA (KUSURSUZ YÖNETİM VERİSİ)
# ─────────────────────────────────────────────────────────────────

def _get_golden_qa_pairs() -> list[QAPair]:
    """Aktif yönetim verilerinden şaşmaz Soru-Cevap çiftleri üretir."""
    try:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "aktif_yonetim.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        yonetim = data.get("yonetim", {})
        rek = yonetim.get("rektor", {}).get("unvan_ad_soyad", "")
        rek_yrd = [y.get("unvan_ad_soyad", "") for y in yonetim.get("rektor_yardimcilari", [])]
        gs = yonetim.get("genel_sekreter", {}).get("unvan_ad_soyad", "")
        
        rek_yrd_str = ", ".join(rek_yrd)
        
        golden_pairs = [
            ("İnönü Üniversitesi rektörü kimdir?", f"İnönü Üniversitesi aktif Rektörü {rek}'tır."),
            ("Rektör kim?", f"İnönü Üniversitesi Rektörü {rek}'tır."),
            ("İnönü Üniversitesi rektör yardımcıları kimlerdir?", f"İnönü Üniversitesi Rektör Yardımcıları: {rek_yrd_str}."),
            ("Rektör yardımcısı kim?", f"İnönü Üniversitesi'nin Rektör Yardımcıları şunlardır: {rek_yrd_str}."),
            ("Genel Sekreter kimdir?", f"İnönü Üniversitesi Genel Sekreteri {gs}'dır."),
            ("İnönü Üniversitesi genel sekreteri kim?", f"İnönü Üniversitesi Genel Sekreteri {gs}'dır."),
            ("Mevcut rektör kim?", f"İnönü Üniversitesi'nin mevcut (aktif) rektörü {rek}'tır."),
            ("Güncel rektör yardımcılarının isimleri neler?", f"Güncel Rektör Yardımcıları: {rek_yrd_str}."),
            # Asistan Kimlik (Identity) Soruları
            ("Seni kim yaptı?", "Beni Ferhat Yıldız ve Muhammet Bilal Yıldız geliştirdi."),
            ("Kim geliştirdi?", "İnönü Üniversitesi'nin yapay zeka asistanı olarak beni Ferhat Yıldız ve Muhammet Bilal Yıldız kodladı."),
            ("Yaratıcın kim?", "Beni Ferhat Yıldız ve Muhammet Bilal Yıldız geliştirdi."),
            ("Seni kim kodladı?", "Bu yapay zeka sistemi Ferhat Yıldız ve Muhammet Bilal Yıldız tarafından kodlanarak geliştirilmiştir.")
        ]
        
        results = []
        for q, a in golden_pairs:
            results.append(QAPair(
                instruction=q,
                output=a,
                source_key="golden_data",
                source_url="aktif_yonetim.json",
                category="yonetim_golden",
                chunk_hash=_hash(q+a)
            ))
        return results
    except Exception as e:
        logger.warning(f"Golden data yüklenirken hata: {e}")
        return []

# ─────────────────────────────────────────────────────────────────
# SHAREGPT FORMATI DÖNÜŞTÜRÜCÜ
# ─────────────────────────────────────────────────────────────────

def convert_to_sharegpt(pairs: list[QAPair]) -> list[dict]:
    """QA çiftlerini LLaMA-Factory uyumlu ShareGPT formatına çevir."""
    entries = []
    for pair in pairs:
        entry = ShareGPTEntry()
        entry.add_turn("system", SYSTEM_PROMPT)
        entry.add_turn("human", pair.instruction)
        entry.add_turn("assistant", pair.output)
        entries.append(entry.to_dict())
    return entries


def convert_to_alpaca(pairs: list[QAPair]) -> list[dict]:
    """QA çiftlerini Alpaca formatına çevir (alternatif)."""
    return [
        {
            "instruction": pair.instruction,
            "input": "",
            "output": pair.output,
            "system": SYSTEM_PROMPT,
        }
        for pair in pairs
    ]


# ─────────────────────────────────────────────────────────────────
# ANA PIPELINE
# ─────────────────────────────────────────────────────────────────

async def run_pipeline(
    input_path: str,
    output_path: str,
    api_url: str,
    model: str,
    max_concurrent: int,
    resume: bool = False,
    output_format: str = "sharegpt",
    batch_size: int = 50,
):
    """
    Ana QA üretim pipeline'ı.

    1. crawl_results.json → chunk listesi
    2. Her chunk için LLM'den QA çiftleri üret (async batch)
    3. Kalite filtresinden geçir
    4. ShareGPT/Alpaca formatına çevir
    5. egitim_verisi.json olarak kaydet
    """
    t0 = time.time()
    logger.info("═══ TAKIM 2: SENTETİK VERİ ÜRETİMİ BAŞLIYOR ═══")
    logger.info(f"Girdi  : {input_path}")
    logger.info(f"Çıktı  : {output_path}")
    logger.info(f"API    : {api_url}")
    logger.info(f"Model  : {model}")
    logger.info(f"Eşzamanlı: {max_concurrent}")

    # 1. Chunk'ları yükle
    chunks = load_chunks_from_crawl_results(input_path)
    if not chunks:
        logger.error("Hiç chunk bulunamadı. Çıkılıyor.")
        return

    # 2. Checkpoint kontrolü
    processed_hashes = _load_checkpoint(CHECKPOINT_FILE) if resume else set()
    remaining = [c for c in chunks if c.chunk_hash not in processed_hashes]
    logger.info(
        f"Toplam chunk: {len(chunks)} | "
        f"Daha önce işlenen: {len(processed_hashes)} | "
        f"Kalan: {len(remaining)}"
    )

    if not remaining:
        logger.info("Tüm chunk'lar zaten işlenmiş. Sadece format dönüşümü yapılıyor...")
    else:
        # 3. LLM istemcisi oluştur
        client = AsyncLLMClient(api_url, model, max_concurrent)

        all_pairs: list[QAPair] = []
        total_generated = 0
        total_filtered = 0

        # Batch'ler halinde işle
        for batch_start in range(0, len(remaining), batch_size):
            batch = remaining[batch_start:batch_start + batch_size]
            batch_num = batch_start // batch_size + 1
            total_batches = (len(remaining) + batch_size - 1) // batch_size

            logger.info(
                f"── Batch {batch_num}/{total_batches}: "
                f"{len(batch)} chunk işleniyor ──"
            )

            # Asenkron olarak tüm batch'i işle
            tasks = [generate_qa_for_chunk(client, c) for c in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            batch_pairs: list[QAPair] = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Chunk hatası [{batch[i].label}]: {result}")
                    continue
                if result:
                    batch_pairs.extend(result)
                    total_generated += len(result)

                # Hash'i işlenmiş olarak kaydet
                processed_hashes.add(batch[i].chunk_hash)

            # Batch sonuçlarını kaydet
            _append_raw_pairs(RAW_QA_FILE, batch_pairs)
            _save_checkpoint(CHECKPOINT_FILE, processed_hashes, {
                "total_chunks": len(chunks),
                "processed": len(processed_hashes),
                "generated_pairs": total_generated,
            })
            all_pairs.extend(batch_pairs)

            logger.info(
                f"  Batch {batch_num} sonuç: {len(batch_pairs)} QA çifti | "
                f"Toplam: {total_generated}"
            )

        await client.close()
        logger.info(f"API istatistikleri: {client.stats}")

    # 4. Tüm ham QA çiftlerini JSONL'den yükle (resume durumu için)
    all_pairs_final: list[QAPair] = []
    if os.path.exists(RAW_QA_FILE):
        seen_hashes = set()
        with open(RAW_QA_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    pair_hash = _hash(d["instruction"] + d["output"])
                    if pair_hash not in seen_hashes:
                        seen_hashes.add(pair_hash)
                        all_pairs_final.append(QAPair(**d))
                except (json.JSONDecodeError, KeyError):
                    continue

    logger.info(f"Toplam benzersiz QA çifti: {len(all_pairs_final)}")

    # 4.5 Golden Dataset Ekle
    golden_pairs = _get_golden_qa_pairs()
    if golden_pairs:
        all_pairs_final.extend(golden_pairs)
        logger.info(f"Golden Dataset'ten {len(golden_pairs)} kusursuz QA çifti eklendi.")

    # 5. Çıktı formatını oluştur ve kaydet
    if output_format == "sharegpt":
        output_data = convert_to_sharegpt(all_pairs_final)
    else:
        output_data = convert_to_alpaca(all_pairs_final)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - t0
    logger.info(
        f"═══ TAMAMLANDI ═══\n"
        f"  Süre          : {elapsed:.0f}s\n"
        f"  İşlenen chunk : {len(processed_hashes)}\n"
        f"  Üretilen QA   : {len(all_pairs_final)}\n"
        f"  Çıktı dosyası : {output_path}\n"
        f"  Format        : {output_format}"
    )


# ─────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="İnönü AI — Sentetik QA Veri Seti Üretici (Takım 2)"
    )
    parser.add_argument(
        "--input", "-i", default=DEFAULT_INPUT,
        help=f"Girdi dosyası (varsayılan: {DEFAULT_INPUT})"
    )
    parser.add_argument(
        "--output", "-o", default=DEFAULT_OUTPUT,
        help=f"Çıktı dosyası (varsayılan: {DEFAULT_OUTPUT})"
    )
    parser.add_argument(
        "--api-url", default=DEFAULT_API_URL,
        help=f"SGLang/vLLM API URL (varsayılan: {DEFAULT_API_URL})"
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"Model adı (varsayılan: {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--max-concurrent", type=int, default=MAX_CONCURRENT,
        help=f"Eşzamanlı istek sayısı (varsayılan: {MAX_CONCURRENT})"
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Checkpoint dosyasından kaldığı yerden devam et"
    )
    parser.add_argument(
        "--format", choices=["sharegpt", "alpaca"], default="sharegpt",
        help="Çıktı formatı (varsayılan: sharegpt)"
    )
    parser.add_argument(
        "--batch-size", type=int, default=50,
        help="Batch boyutu (varsayılan: 50)"
    )

    args = parser.parse_args()

    asyncio.run(run_pipeline(
        input_path=args.input,
        output_path=args.output,
        api_url=args.api_url,
        model=args.model,
        max_concurrent=args.max_concurrent,
        resume=args.resume,
        output_format=args.format,
        batch_size=args.batch_size,
    ))


if __name__ == "__main__":
    main()
