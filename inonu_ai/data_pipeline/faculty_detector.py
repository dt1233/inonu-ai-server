#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
İnönü AI — Merkezi Fakülte/Birim Tespiti Modülü (DRY & SOLID)
Tüm crawler, chunker, PDF extractor ve retriever için ortak kaynak.
"""

import re
import unicodedata

# ─── Zenginleştirilmiş Fakülte Haritası ───
# Key: Sistemin kullanacağı standart Fakülte/Birim adı (contract'a uygun).
# Value: Metin içinde aranacak olası varyasyonlar.
FACULTY_MAP = {
    "Mühendislik Fakültesi": ["mühendislik fakültesi", "muhendislik", "mühendislik", "müh. fak.", "müh.fak.", "müh."],
    "Hukuk Fakültesi": ["hukuk fakültesi", "hukuk"],
    "Tıp Fakültesi": ["tıp fakültesi", "tip fakultesi", "tıp"],
    "Diş Hekimliği Fakültesi": ["diş hekimliği", "dis hekimligi", "diş hekimliği fakültesi"],
    "Eğitim Fakültesi": ["eğitim fakültesi", "egitim fakultesi"],
    "Fen Edebiyat Fakültesi": ["fen edebiyat fakültesi", "fen-edebiyat", "fen edebiyat"],
    "İktisadi ve İdari Bilimler Fakültesi": ["iktisadi ve idari", "iibf", "iktisadi"],
    "İlahiyat Fakültesi": ["ilahiyat fakültesi", "ilahiyat"],
    "İletişim Fakültesi": ["iletişim fakültesi", "iletisim fakultesi", "iletişim"],
    "Sağlık Bilimleri Fakültesi": ["sağlık bilimleri fakültesi", "saglik bilimleri", "sağlık bilimleri"],
    "Spor Bilimleri Fakültesi": ["spor bilimleri fakültesi", "spor bilimleri"],
    "Ziraat Fakültesi": ["ziraat fakültesi", "ziraat"],
    "Eczacılık Fakültesi": ["eczacılık fakültesi", "eczacilik", "eczacılık"],
    "Güzel Sanatlar Fakültesi": ["güzel sanatlar fakültesi", "güzel sanatlar", "guzel sanatlar"],
    "Hemşirelik Fakültesi": ["hemşirelik fakültesi", "hemsirelik", "hemşirelik"],
    "Sağlık Hizmetleri Meslek Yüksekokulu": ["sağlık hizmetleri meslek yüksekokulu", "shmyo"],
    "Meslek Yüksekokulu": ["meslek yüksekokulu", "myo"],
    "Devlet Konservatuvarı": ["devlet konservatuvarı", "konservatuvar"],
    "Edebiyat Fakültesi": ["edebiyat fakültesi", "edebiyat"] # Fen edebiyatla çakışmamasına dikkat edilmeli
}

def normalize_turkish_text(text: str) -> str:
    """Türkçe karakterleri güvenli şekilde küçük harfe çevirir ve normalize eder."""
    if not text:
        return ""
    
    # Özel Türkçe dönüşümleri
    text = text.replace("İ", "i").replace("I", "ı")
    text = text.lower()
    
    # Unicode NFD normalizasyonu
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    return text

def detect_faculty(text: str) -> dict:
    """
    Verilen metin içinden hangi fakülteye ait olduğunu tespit eder.
    En çok eşleşen veya en uzun varyasyonlu eşleşmeyi birinci seçer.
    
    Dönüş formatı:
    {
        "fakulte": "Mühendislik Fakültesi" | None,
        "confidence": 0.0-1.0,
        "matched_terms": [...]
    }
    """
    if not text:
        return {"fakulte": None, "confidence": 0.0, "matched_terms": []}

    norm_text = normalize_turkish_text(text)
    
    matches = {}
    matched_all_terms = []
    
    for standard_name, variations in FACULTY_MAP.items():
        for var in variations:
            norm_var = normalize_turkish_text(var)
            
            # Word boundary with lookarounds to handle punctuation properly
            # (?<!\w) means not preceded by a word character
            # (?!\w) means not followed by a word character
            pattern = r'(?<!\w)' + re.escape(norm_var) + r'(?!\w)'
            
            occurrences = len(re.findall(pattern, norm_text))
            if occurrences > 0:
                if standard_name not in matches:
                    matches[standard_name] = {"count": 0, "terms": set(), "score": 0}
                
                matches[standard_name]["count"] += occurrences
                matches[standard_name]["terms"].add(var)
                # Uzun terimler daha güvenilirdir (Örn: "mühendislik fakültesi" vs "müh.")
                matches[standard_name]["score"] += (len(norm_var) * occurrences)
                matched_all_terms.append(var)

    if not matches:
        return {"fakulte": None, "confidence": 0.0, "matched_terms": []}

    # "Fen Edebiyat" ve "Edebiyat" çakışması kontrolü
    # Eğer "fen edebiyat" eşleştiyse, saf "edebiyat" match'ini ezsin.
    if "Fen Edebiyat Fakültesi" in matches and "Edebiyat Fakültesi" in matches:
        # Eğer Edebiyat sadece "edebiyat" varyasyonu ile eşleştiyse ve sayısı Fen Edebiyat ile aynıysa, sil.
        if matches["Edebiyat Fakültesi"]["count"] <= matches["Fen Edebiyat Fakültesi"]["count"]:
            del matches["Edebiyat Fakültesi"]

    if not matches:
        return {"fakulte": None, "confidence": 0.0, "matched_terms": []}

    # Skora göre en iyi eşleşmeyi bul
    best_match = max(matches.items(), key=lambda x: x[1]["score"])
    standard_name = best_match[0]
    data = best_match[1]
    
    # Confidence hesabı (basit heuristic)
    # Eğer skor 20'den büyükse (örn: "mühendislik fakültesi" 1 kez geçse 21 kar) %90+ güven
    confidence = min(data["score"] / 25.0, 1.0)
    
    # Çok kısa eşleşmeler için (örn sadece "tıp" 1 kez geçti) confidence düşür
    if data["score"] < 5:
        confidence = 0.4
    elif data["count"] > 2:
        confidence = 0.95

    return {
        "fakulte": standard_name,
        "confidence": round(confidence, 2),
        "matched_terms": list(data["terms"])
    }

def extract_requested_faculties(query: str) -> list[str]:
    """
    Kullanıcı sorusundaki hedeflenen fakülteleri döndürür.
    Bu, eski _extract_faculties'in gelişmiş versiyonudur.
    """
    norm_query = normalize_turkish_text(query)
    found = set()
    
    for standard_name, variations in FACULTY_MAP.items():
        for var in variations:
            norm_var = normalize_turkish_text(var)
            pattern = r'(?<!\w)' + re.escape(norm_var) + r'(?!\w)'
            if re.search(pattern, norm_query):
                found.add(standard_name)
                break # Bu fakülte bulundu, varyasyonları aramaya gerek yok
                
    return list(found)

if __name__ == "__main__":
    # Smoke Test
    test_texts = [
        "Müh. Fak. bahar yarıyılı akademik takvimi güncellenmiştir.",
        "Mühendislik Fakültesi ve Tıp Fakültesi öğrencileri dikkatine...",
        "İktisadi ve İdari Bilimler Fakültesi dekanlığı",
        "Edebiyat fakültesinde okuyanlar...",
        "Fen-Edebiyat öğrencileri",
        "Bu genel bir üniversite duyurusudur."
    ]
    
    print("--- Faculty Detector Smoke Test ---")
    for t in test_texts:
        res = detect_faculty(t)
        print(f"\nText: {t}")
        print(f"Result: {res}")
