#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os

# OOM hatasını önlemek için RAG araması sırasında bge-m3'ü CPU'da çalışmaya zorluyoruz
os.environ["BGE_DEVICE"] = "cpu"

import requests
import json
import datetime
from loguru import logger
from engine.retriever import Retriever

def get_aktif_yonetim_notu() -> str:
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "aktif_yonetim.json")
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        yonetim = data.get("yonetim", {})
        rek = yonetim.get("rektor", {}).get("unvan_ad_soyad", "")
        rek_yrd = [y.get("unvan_ad_soyad", "") for y in yonetim.get("rektor_yardimcilari", [])]
        gs = yonetim.get("genel_sekreter", {}).get("unvan_ad_soyad", "")
        
        notu = "\n\nGÜNCEL BİLGİ NOTU (BU BİLGİ KESİNDİR VE ASLA DEĞİŞTİRİLEMEZ):\n"
        notu += f"- İnönü Üniversitesi Aktif Rektörü: {rek}\n"
        notu += f"- Rektör Yardımcıları: {', '.join(rek_yrd)}\n"
        notu += f"- Genel Sekreter: {gs}\n"
        return notu
    except Exception:
        return ""

def get_current_date_note() -> str:
    now = datetime.datetime.now()
    return f"\nSİSTEM NOTU: Bugünün tarihi {now.strftime('%d %B %Y')}. Eğer bağlamda 2024 veya 2025 yıllarına ait veriler varsa, kullanıcının güncel tarih ile bu veriler arasındaki farkı anlaması için 'Elimizdeki en son kayıtlara göre (2024/2025 dönemi)' şeklinde belirt."

SGLANG_URL = "http://localhost:30000/v1/chat/completions"

def generate_answer(query: str, retrieved_docs: list) -> str:
    # 1. Bağlamı (Context) oluştur
    context = ""
    for idx, doc in enumerate(retrieved_docs, 1):
        context += f"--- Kaynak {idx} ({doc['source_url']}) ---\n{doc['text']}\n\n"
    
    # 2. RAG Prompt'unu hazırla
    yonetim_notu = get_aktif_yonetim_notu()
    tarih_notu = get_current_date_note()
    
    system_prompt = (
        "Sen İnönü Üniversitesi'nin resmi yapay zeka asistanısın. Adın 'İnönü Asistan'.\n"
        "Seni İnönü Üniversitesi Dijital Dönüşüm Ofisi koordinatörlüğünde "
        "Ferhat Yıldız ve Muhammet Bilal Yıldız geliştirdi. Biri sana kim olduğunu sorarsa bu bilgiyi ver.\n\n"
        "GÖREVİN:\n"
        "Sana sağlanan KAYNAKLAR metinlerindeki verileri analiz ederek kullanıcının sorusunu yanıtlamak.\n\n"
        "KURALLAR:\n"
        "1. Kaynaklardaki metinler tablolardan veya PDF'lerden düz metne çevrilmiş olabilir. Parçalanmış kelimeleri ve tarihleri mantıksal olarak birleştirerek oku.\n"
        "2. DİKKAT: Kullanıcı belirli bir fakülte, bölüm veya yıl soruyorsa (örn: Mühendislik) ve kaynaklarda başka bir fakültenin (örn: Hukuk, Tıp) bilgisi varsa, ASLA o bilgileri kullanıcıya istenen fakülteymiş gibi sunma! Açıkça 'Kaynaklarda ... Fakültesi ile ilgili bilgi bulunmamaktadır' de.\n"
        "3. Kendi kendine bilgi uydurma veya sahte link/adres üretme. Sadece KAYNAKLAR'a dayan."
    ) + yonetim_notu + tarih_notu
    
    user_prompt = f"KAYNAKLAR:\n{context}\n\nSORU: {query}"
    
    # API'den aktif modeli otomatik çek
    try:
        models_resp = requests.get("http://localhost:30000/v1/models", timeout=5)
        models_resp.raise_for_status()
        active_model = models_resp.json()["data"][0]["id"]
    except:
        active_model = "default"

    payload = {
        "model": active_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 512
    }
    
    try:
        response = requests.post("http://localhost:30000/v1/chat/completions", json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[Hata] API sunucusuna bağlanılamadı: {e}"

def main():
    print("="*60)
    print(" İNÖNÜ AI - RAG SOHBET ARAYÜZÜ ".center(60, "█"))
    print(" Çıkmak için 'q' veya 'exit' yazın ".center(60, "="))
    print("="*60)
    
    retriever = Retriever()
    
    while True:
        query = input("\nSoru: ").strip()
        if query.lower() in ["q", "exit", "çıkış"]:
            break
        if not query:
            continue
            
        print("🔍 Veritabanında aranıyor...")
        docs = retriever.search(query, top_k=3)
        
        if not docs:
            print("⚠️ Veritabanında ilgili hiçbir bilgi bulunamadı.")
            continue
            
        print("🤖 Cevap oluşturuluyor...")
        answer = generate_answer(query, docs)
        
        print(f"\n{'-'*60}\nİnönü Asistan: {answer}\n{'-'*60}")
        print("Kullanılan Kaynaklar:")
        for doc in docs:
            print(f"- {doc['source_url']} (Skor: {doc['score']:.2f})")

if __name__ == "__main__":
    main()
