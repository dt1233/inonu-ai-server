#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from pathlib import Path
from loguru import logger
from data_pipeline.chunker import Chunker
from data_pipeline.indexer import Indexer

def index_existing_data():
    data_file = Path("data/crawl_results.json")
    
    if not data_file.exists():
        logger.error(f"{data_file} bulunamadı!")
        return
        
    logger.info("Mevcut veri dosyası okunuyor...")
    with open(data_file, "r", encoding="utf-8") as f:
        results = json.load(f)
        
    logger.info("Chunking işlemi başlatılıyor...")
    chunker = Chunker()
    chunks = chunker.chunk_all(results)
    
    if not chunks:
        logger.info("Oluşturulan chunk yok.")
        return
        
    logger.info(f"{len(chunks)} adet chunk oluşturuldu. Veritabanına (Qdrant) yazılıyor...")
    indexer = Indexer()
    written = indexer.index_chunks(chunks)
    
    logger.info(f"İşlem tamam! Qdrant veritabanına başarıyla yazılan chunk sayısı: {written}")

if __name__ == "__main__":
    index_existing_data()
