import json
from pathlib import Path
from inonu_ai.data_pipeline.chunker import Chunker
from dataclasses import asdict

data = json.load(open('data/crawl_results.json', 'r', encoding='utf-8'))

chunker = Chunker()
all_chunks = []

if 'announcements' in data:
    all_chunks.extend(chunker.chunk_announcements(data['announcements']))
if 'static_contents' in data:
    all_chunks.extend(chunker.chunk_static_contents(data['static_contents']))
if 'avesis_staff' in data:
    all_chunks.extend(chunker.chunk_avesis_staff(data['avesis_staff']))

# Export chunks
out = Path("data/chunks_output.json")
out.write_text(json.dumps([asdict(c) for c in all_chunks], ensure_ascii=False, indent=2), encoding='utf-8')
print(f"Generated {len(all_chunks)} chunks and saved to {out}")
