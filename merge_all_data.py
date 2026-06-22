import json
import codecs

def main():
    # Load all the data files
    with codecs.open('data/final_dekanlar.json', 'r', encoding='utf-8') as f:
        dekanlar = json.load(f)
        
    with codecs.open('data/final_bolum_baskanlari.json', 'r', encoding='utf-8') as f:
        bolumler = json.load(f)
        
    with codecs.open('data/idari_personel.json', 'r', encoding='utf-8') as f:
        idari_personel = json.load(f)
        
    # Build a hierarchical structure
    # Fakulteler -> Dekan -> Idari Personel -> Bolumler -> Bolum Baskani
    
    fakulteler_dict = {}
    
    for d in dekanlar:
        fak_name = d['fakulte']
        fakulteler_dict[fak_name] = {
            "fakulte_adi": fak_name,
            "dekan": d.get('dekan'),
            "idari_personel": [],
            "bolumler": []
        }
        
    for b in bolumler:
        fak_name = b['fakulte']
        if fak_name not in fakulteler_dict:
            fakulteler_dict[fak_name] = {
                "fakulte_adi": fak_name,
                "dekan": None,
                "idari_personel": [],
                "bolumler": []
            }
        
        fakulteler_dict[fak_name]["bolumler"].append({
            "bolum_adi": b['bolum'],
            "bolum_baskani": b.get('bolum_baskani'),
            "slug": b.get('slug'),
            "baskan_url": b.get('baskan_url')
        })
        
    # Match idari personel to fakulteler
    diger_birimler = {}
    
    for p in idari_personel:
        birim = p.get('birim', '').strip()
        # if birim matches a fakulte
        matched_fakulte = None
        for fak_name in fakulteler_dict.keys():
            if birim.lower() == fak_name.lower():
                matched_fakulte = fak_name
                break
        
        if matched_fakulte:
            fakulteler_dict[matched_fakulte]["idari_personel"].append(p)
        else:
            if birim not in diger_birimler:
                diger_birimler[birim] = []
            diger_birimler[birim].append(p)
            
    # Compile final structure
    final_structure = {
        "fakulteler": list(fakulteler_dict.values()),
        "diger_idari_birimler": [{"birim_adi": k, "personel": v} for k, v in diger_birimler.items()]
    }
    
    with codecs.open('data/inonu_universitesi_yonetim_rehberi.json', 'w', encoding='utf-8') as f:
        json.dump(final_structure, f, ensure_ascii=False, indent=2)
        
    print(f"Başarıyla birleştirildi: data/inonu_universitesi_yonetim_rehberi.json")
    print(f"Toplam Fakülte Sayısı: {len(final_structure['fakulteler'])}")
    print(f"Toplam Diğer Birim Sayısı: {len(final_structure['diger_idari_birimler'])}")

if __name__ == "__main__":
    main()
