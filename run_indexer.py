#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
import sys
from pathlib import Path

# Proje ana dizinini path'e ekle
sys.path.append(str(Path(__file__).parent))

from inonu_ai.data_pipeline.indexer import Indexer
from inonu_ai.data_pipeline.chunker import Chunk
from loguru import logger

def main():
    parser = argparse.ArgumentParser(description="İnönü AI Vector Database (Qdrant) Deployment Indexer")
    parser.add_argument("--reset", action="store_true", help="Qdrant koleksiyonundaki eski verileri tamamen siler ve baştan oluşturur (Tavsiye edilen).")
    parser.add_argument("--file", type=str, default="data/chunks_output.json", help="Yüklenecek chunk dosyası (Varsayılan: data/chunks_output.json)")
    args = parser.parse_args()

    chunk_file = Path(args.file)
    if not chunk_file.exists():
        logger.error(f"Hata: {args.file} bulunamadı! Önce veri çekme ve chunking (rebuild_pipeline.py) işlemlerini çalıştırdığınızdan emin olun.")
        return

    logger.info(f"Chunk dosyası okunuyor: {chunk_file}")
    try:
        with open(chunk_file, "r", encoding="utf-8") as f:
            chunks_data = json.load(f)
    except Exception as e:
        logger.error(f"Dosya okuma hatası: {e}")
        return

    # Sözlükleri Chunk veri sınıfına dönüştür
    chunks = [Chunk(**c) for c in chunks_data]
    logger.info(f"Toplam {len(chunks)} adet chunk (vektör adayı) hafızaya alındı.")

    logger.info("Vektör veritabanına bağlanılıyor...")
    try:
        # Eğer --reset kullanılmışsa, indexer_init eski koleksiyonu Drop (silme) işlemi yapacaktır
        indexer = Indexer(reset=args.reset)
    except Exception as e:
        logger.error(f"Qdrant veritabanına bağlanılamadı. Sunucuda Qdrant Docker konteynerinin çalıştığından emin olun. Hata: {e}")
        return

    logger.info("İndeksleme (Embedding ve Qdrant'a yazma) işlemi başlatılıyor...")
    written = indexer.index_chunks(chunks)

    logger.info("="*60)
    logger.info(f"BAŞARILI: Qdrant koleksiyonuna {written} adet vektör kaydedildi.")
    logger.info("="*60)

if __name__ == "__main__":
    main()
