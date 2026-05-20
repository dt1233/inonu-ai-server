#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İnönü AI — Retroaktif PDF Kurtarma ve Yeniden Chunklama Betiği
"""

import asyncio
import io
import json
import re
import os
from pathlib import Path
from dataclasses import asdict
import httpx
import pypdf
from loguru import logger

# Ayarlar
CRAWL_RESULTS_PATH = Path("data/crawl_results.json")
CHUNKS_OUTPUT_PATH = Path("data/chunks_output.json")
PDF_DIR = Path("data/pdf_belgeler")

CONCURRENCY_LIMIT = 20  # Aynı anda indirilecek maksimum PDF sayısı
REQUEST_TIMEOUT = 15.0

# User-Agent başlığı
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; InonuAI-Bot/1.0)"}


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """PDF baytlarından temiz metin çıkarır."""
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = "\n".join(p.extract_text() or "" for p in reader.pages).strip()
        if text:
            return text
    except Exception as e:
        logger.debug(f"pypdf okuma hatası: {e}")
    return "[PDF Okunamadı]"


async def _download_and_parse_pdf(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    url: str,
    ann_id: int,
    idx: int,
) -> dict:
    """Tek bir PDF'i indirir, kaydeder ve metnini çıkarır."""
    result = {"url": url, "content": "[PDF Okunamadı]", "pdfPath": None, "status": "failed"}
    
    if not url or url.startswith("file://"):
        result["status"] = "skipped"
        return result

    async with semaphore:
        try:
            logger.info(f"[{ann_id}] PDF İndiriliyor: {url[:60]}...")
            resp = await client.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            pdf_bytes = resp.content
            
            # PDF byte'larının doğruluğunu teyit et
            if not pdf_bytes.startswith(b"%PDF"):
                logger.warning(f"[{ann_id}] İndirilen dosya geçerli bir PDF değil (HTML yanıtı olabilir).")
                result["status"] = "invalid_pdf"
                return result
            
            # Diske kaydet
            PDF_DIR.mkdir(parents=True, exist_ok=True)
            safe_name = re.sub(r"[^\w.\-]", "_", url.split("/")[-1].split("?")[0]) or "belge.pdf"
            path = PDF_DIR / f"{ann_id}_rec{idx}_{safe_name}"
            
            path.write_bytes(pdf_bytes)
            result["pdfPath"] = str(path)
            
            # Metni çıkar
            text = _extract_pdf_text(pdf_bytes)
            if text and text != "[PDF Okunamadı]":
                result["content"] = text
                result["status"] = "success"
                logger.info(f"✓ [{ann_id}] PDF başarıyla çözümlendi ({len(text)} karakter).")
            else:
                result["status"] = "unreadable"
                logger.warning(f"✗ [{ann_id}] PDF metni çıkarılamadı.")
                
        except Exception as e:
            logger.error(f"✗ [{ann_id}] PDF indirme/okuma hatası: {e}")
            result["status"] = f"error: {str(e)}"
            
    return result


async def main():
    if not CRAWL_RESULTS_PATH.exists():
        logger.error(f"Hata: {CRAWL_RESULTS_PATH} bulunamadı!")
        return

    logger.info("1. crawl_results.json yükleniyor...")
    with open(CRAWL_RESULTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Düzeltilecek eklentileri bul
    attachments_to_fix = []
    
    announcements = data.get("announcements", [])
    for ann in announcements:
        ann_id = ann.get("id")
        attachments = ann.get("attachments", [])
        for idx, att in enumerate(attachments, 1):
            if att.get("type") == "pdf":
                content = att.get("content", "")
                # Eğer PDF okunamadı olarak işaretlendiyse veya boşsa indir
                if content == "[PDF Okunamadı]" or not content.strip():
                    attachments_to_fix.append({
                        "ann_id": ann_id,
                        "url": att.get("url"),
                        "idx": idx,
                        "attachment_ref": att  # Güncelleme için doğrudan referans
                    })

    total_jobs = len(attachments_to_fix)
    logger.info(f"Kurtarılacak toplam PDF sayısı: {total_jobs}")
    
    if total_jobs == 0:
        logger.info("Tüm PDF'ler zaten başarıyla okunmuş veya kurtarılacak PDF yok!")
        return

    # Asenkron indirme kuyruğu oluştur
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=30)
    
    async with httpx.AsyncClient(limits=limits, follow_redirects=True) as client:
        tasks = []
        for job in attachments_to_fix:
            tasks.append(
                _download_and_parse_pdf(
                    client, semaphore, job["url"], job["ann_id"], job["idx"]
                )
            )
        
        # Tüm görevleri paralel çalıştır
        results = await asyncio.gather(*tasks)

    # Sonuçları crawl_results.json nesnesine geri yaz
    success_count = 0
    failed_count = 0
    skipped_count = 0

    for job, res in zip(attachments_to_fix, results):
        att = job["attachment_ref"]
        if res["status"] == "success":
            att["content"] = res["content"]
            att["pdfPath"] = res["pdfPath"]
            success_count += 1
        else:
            att["content"] = "[PDF Okunamadı]"
            att["pdfPath"] = res.get("pdfPath")
            failed_count += 1

    logger.info(f"PDF İndirmeleri Bitti. Başarılı: {success_count} | Başarısız: {failed_count}")

    # 4. crawl_results.json dosyasını güncelle
    logger.info("2. Güncellenmiş crawl_results.json kaydediliyor...")
    with open(CRAWL_RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("crawl_results.json başarıyla güncellendi!")

    # 5. Chunker ile yeniden chunklama işlemi yap
    logger.info("3. Chunker ile yeniden chunklama başlatılıyor...")
    try:
        from inonu_ai.data_pipeline.chunker import Chunker
        chunker = Chunker()
        new_chunks = chunker.chunk_all(data)
        
        # Dataclass'ları sözlüğe çevirip kaydet
        chunk_dicts = [asdict(c) for c in new_chunks]
        
        with open(CHUNKS_OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(chunk_dicts, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✓ chunks_output.json başarıyla yeniden oluşturuldu! Yeni chunk sayısı: {len(chunk_dicts)}")
    except Exception as e:
        logger.error(f"Yeniden chunklama hatası: {e}")

if __name__ == "__main__":
    asyncio.run(main())
