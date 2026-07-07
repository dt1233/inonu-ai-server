# Sunucu Deploy Yol Haritasi

Bu dokuman, `feature/full-data-rag` branch'i sunucuya cekildikten sonra RAG sistemini
production'a zarar vermeden dogrulamak ve devreye almak icin izlenecek sirayi tanimlar.

Kritik ilke:

- Production `qdrant_storage` ve mevcut servis ilk adimda degistirilmeyecek.
- Ilk sunucu denemesi staging uzerinde yapilacak.
- `written == qdrant_point_count` dogrulanmadan sonraki asamaya gecilmeyecek.
- RAG testleri gecmeden production switch yapilmayacak.
- Hata alinirsa loglar korunacak, production'a dokunulmadan durulacak.

## 0. Dizin ve Ortam Bilgisi

Sunucuda gorulen mevcut paket dizini:

```bash
/home/yapayzeka/inonu-proje/inonuasilproje/inonu_ai
```

Bu dizin Python paketi gibi duruyor; icinde `data_pipeline`, `engine`, `agents`, `api`
klasorleri var. Repo kokunun bir ust dizin oldugu goruluyor:

```bash
/home/yapayzeka/inonu-proje/inonuasilproje
```

Repo kokunde sunlar var:

```text
inonu_ai/
run_indexer.py
rebuild_pipeline.py
tests/
smoke_test_*.py
qdrant_storage/
```

Bu nedenle komutlar repo kokunden calistirilmelidir:

```bash
cd /home/yapayzeka/inonu-proje/inonuasilproje
```

Sanal ortam:

```bash
conda activate lf_egitim
export PY=/home/yapayzeka/miniconda3/envs/lf_egitim/bin/python
```

Eger conda aktiflestirme komutu farkliysa once `conda env list` ile ortam adi dogrulanir.
Bu sunucuda `python` komutu farkli bir binary'ye gidebildigi icin kritik komutlarda
daima `$PY` kullanilir.

## 1. Preflight: Kod ve Import Kontrolu

Amac: Kod syntax/import seviyesinde ayakta mi, sunucu ortaminda gerekli paketler var mi?

```bash
cd /home/yapayzeka/inonu-proje/inonuasilproje
conda activate lf_egitim
export PY=/home/yapayzeka/miniconda3/envs/lf_egitim/bin/python

$PY - <<'PY'
from pathlib import Path

files = [
    "inonu_ai/data_pipeline/indexer.py",
    "run_indexer.py",
    "inonu_ai/engine/embedding.py",
    "inonu_ai/engine/retriever.py",
    "tests/run_rag_cases.py",
]

for f in files:
    p = Path(f)
    print("CHECK", f, "exists=", p.exists())
    compile(p.read_text(encoding="utf-8"), f, "exec")
    print("OK", f)
PY
```

Import kontrolu:

```bash
$PY - <<'PY'
mods = [
    "fastembed",
    "qdrant_client",
    "loguru",
    "yaml",
    "pydantic",
]

for m in mods:
    __import__(m)
    print("OK", m)
PY
```

Basarisizlik durumunda:

- Eksik paket varsa production'a gecilmez.
- Paket kurulumu gerekiyorsa once `requirements.txt` kontrol edilir.
- Internet/model indirme kisiti varsa model cache stratejisi netlestirilir.

## 2. Veri Dosyasi Kontrolu

Amac: Sunucuda indexlenecek gercek veri var mi?

```bash
$PY - <<'PY'
from pathlib import Path
from inonu_ai.data_pipeline.io_utils import load_json

paths = [
    "data/crawl_results.json",
    "data/chunks_output.json",
    "data/quality_report.json",
]

for path in paths:
    p = Path(path)
    print(path, "exists=", p.exists(), "size=", p.stat().st_size if p.exists() else 0)
    if not p.exists():
        continue
    data = load_json(str(p), default=None)
    if isinstance(data, dict):
        print("  keys=", list(data.keys()))
        print("  list_counts=", {k: len(v) for k, v in data.items() if isinstance(v, list)})
    elif isinstance(data, list):
        print("  list_len=", len(data))
PY
```

Kabul kriteri:

- `data/chunks_output.json` var olmali.
- Chunk sayisi 0 olmamali.
- Mümkünse localde uretilen dogrulanmis veri sunucuya tasinmis olmali.

## 3. Quality Gate

Amac: Index oncesi veri kalitesini kontrol etmek.

```bash
$PY inonu_ai/data_pipeline/quality_report.py \
  --crawl-path data/crawl_results.json \
  --chunks-path data/chunks_output.json \
  --report-path data/quality_report.json
```

Kabul kriteri:

- ERROR sayisi 0 olmali.
- WARNING varsa turu incelenmeli.
- Owner mismatch tek basina bloklayici olmayabilir; retrieval filtresi bunu elemelidir.
- Encoding anomaly, empty faculty, empty page_no gibi hatalar production oncesi cozulmelidir.

## 4. Staging Sample Index

Amac: Production Qdrant'a dokunmadan sunucuda model, Qdrant, disk ve indexer akisini test etmek.

Production degil, staging kullanilacak:

```bash
mkdir -p logs

export QDRANT_COLLECTION=inonu_docs_staging
export QDRANT_PATH=qdrant_storage_staging

$PY run_indexer.py \
  --reset \
  --limit 1000 \
  --batch-size 16 \
  --log-file logs/indexer_staging_sample_$(date +%Y%m%d_%H%M%S).log
```

Kabul kriteri:

- Komut exit code 0 ile bitmeli.
- Logda `INDEX COMPLETE` gorulmeli.
- `written == qdrant_point_count` olmali.
- `point_count > 0` olmali.

Bagimsiz point count kontrolu:

```bash
$PY - <<'PY'
from qdrant_client import QdrantClient

c = QdrantClient(path="qdrant_storage_staging")
info = c.get_collection("inonu_docs_staging")
print("points:", info.points_count)
print("status:", info.status)
assert info.points_count > 0
c.close()
PY
```

Basarisizlik durumunda:

- Log dosyasi incelenir.
- Production'a dokunulmaz.
- Hata paket/model/Qdrant/disk izinlerinden hangisiyse ayrilir.

## 5. Staging RAG Test

Amac: Staging collection uzerinden Retriever dogru fakulte filtreliyor mu?

```bash
export QDRANT_COLLECTION=inonu_docs_staging
export QDRANT_PATH=qdrant_storage_staging

$PY tests/run_rag_cases.py
```

Kabul kriteri:

- Bos docs donmemeli.
- Forbidden faculty gelmemeli.
- Expected faculty ilgili sorgularda bulunmali.
- Scope kurallari gecmeli.

Eger test fail olursa:

- Retrieved metadata tablosu istenir.
- `fakulte`, `source_fakulte`, `detected_fakulte`, `scope`, `doc_type`, `source_url`, `pdf_url` incelenir.
- Production'a gecilmez.

## 6. Full Staging Index

Sample index ve RAG smoke basariliysa full staging index calistirilir.

```bash
export QDRANT_COLLECTION=inonu_docs_staging
export QDRANT_PATH=qdrant_storage_staging

$PY run_indexer.py \
  --reset \
  --batch-size 32 \
  --log-file logs/indexer_staging_full_$(date +%Y%m%d_%H%M%S).log
```

Not:

- GPU/RAM durumuna gore `--batch-size 16` daha guvenli olabilir.
- Full index uzun surebilir.
- Komut bitmeden terminal kapatilmamalidir.

Kabul kriteri:

- `INDEX COMPLETE`
- `written == qdrant_point_count`
- Point count beklenen chunk sayisina yakin olmali.
- Indexer exit code 0 donmeli.

## 7. Full Staging RAG Dogrulama

```bash
export QDRANT_COLLECTION=inonu_docs_staging
export QDRANT_PATH=qdrant_storage_staging

$PY tests/run_rag_cases.py
```

Manuel sorgular icin Python snippet:

```bash
$PY - <<'PY'
from inonu_ai.engine.retriever import Retriever

queries = [
    "Muhendislik Fakultesi butleri ne zaman?",
    "Hukuk Fakultesi butunleme sinavlari ne zaman?",
    "Tip Fakultesi butunleme sinavlari ne zaman?",
    "Yemekhane menusu bugun ne?",
]

r = Retriever()
for q in queries:
    print("\nQUERY:", q)
    docs = r.search(q, top_k=5)
    for i, d in enumerate(docs, 1):
        m = d.get("metadata", {})
        print({
            "rank": i,
            "score": d.get("score"),
            "scope": m.get("scope"),
            "doc_type": m.get("doc_type"),
            "fakulte": m.get("fakulte"),
            "source_fakulte": m.get("source_fakulte"),
            "detected_fakulte": m.get("detected_fakulte"),
            "source_url": d.get("source_url"),
            "pdf_url": m.get("pdf_url"),
            "page_no": m.get("page_no"),
        })
PY
```

Kabul kriteri:

- Muhendislik sorgusunda Hukuk/Tip/Dis Hekimligi sonucu gelmemeli.
- Hukuk sorgusunda Muhendislik/Tip/Dis Hekimligi sonucu gelmemeli.
- Tip sorgusunda Muhendislik/Hukuk/Dis Hekimligi sonucu gelmemeli.
- Yemekhane gibi genel sorgularda `scope=university` kabul edilir.

## 8. Production Backup

Full staging basarili olmadan bu adima gecilmez.

```bash
ts=$(date +%Y%m%d_%H%M%S)
mkdir -p backups/deploy_$ts

cp -a qdrant_storage backups/deploy_$ts/qdrant_storage 2>/dev/null || true
cp -a data backups/deploy_$ts/data 2>/dev/null || true
cp -a .env backups/deploy_$ts/.env 2>/dev/null || true

echo "Backup created: backups/deploy_$ts"
```

## 9. Atomic Switch Stratejisi

Production'a gecmeden once net karar:

- Eger uygulama local path olarak `qdrant_storage` kullaniyorsa, staging `qdrant_storage_staging`
  basarili olduktan sonra servis durdurulup klasor switch yapilir.
- Eger env ile `QDRANT_PATH` okunuyorsa, production servis env'i staging path'e alinabilir.

Guvenli switch ornegi:

```bash
# servis durdurma komutu projeye gore degisir
# sudo systemctl stop inonu-ai

mv qdrant_storage qdrant_storage_old_$(date +%Y%m%d_%H%M%S)
mv qdrant_storage_staging qdrant_storage

# sudo systemctl start inonu-ai
```

Bu adimdan once servis yonetimi net degilse uygulanmaz.

## 10. Post Deploy Verify

```bash
# API servis ayagina gore uyarlanir
curl -s http://127.0.0.1:8000/api/health
```

API auth gerekiyorsa `/api/ask` testi token ile yapilir.

Retriever seviyesinde son kontrol:

```bash
$PY tests/run_rag_cases.py
```

## Rollback

Post-deploy verify fail olursa:

```bash
# servis durdur
# sudo systemctl stop inonu-ai

mv qdrant_storage qdrant_storage_failed_$(date +%Y%m%d_%H%M%S)
cp -a backups/deploy_YYYYMMDD_HHMMSS/qdrant_storage qdrant_storage

# servis baslat
# sudo systemctl start inonu-ai
```

Rollback sonrasi:

```bash
$PY tests/run_rag_cases.py
```

## Gecis Karari

Sunucu production switch icin tum maddeler yesil olmali:

- Preflight syntax/import OK.
- Quality report ERROR=0.
- Staging sample index OK.
- Staging sample RAG OK.
- Full staging index OK.
- Full staging RAG OK.
- Backup alindi.
- Switch/rollback komutlari net.

Bu maddelerden biri eksikse production deploy yapilmaz.
