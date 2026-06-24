#!/bin/bash

# ==========================================
# İNÖNÜ AI - LLaMA-Factory Eğitim Başlatıcı
# ==========================================

echo "🚀 LLaMA-Factory QLoRA Eğitimi Başlıyor..."

# 1. Gerekli yolları belirle
PROJECT_DIR="/home/yapayzeka/inonu-proje/inonuasilproje/inonu_ai"
DATA_FILE="$PROJECT_DIR/data/egitim_verisi.json"
BASE_MODEL="/home/yapayzeka/models/Qwen3-8B"
OUTPUT_DIR="$PROJECT_DIR/data/qlora_output"
MERGE_DIR="/home/yapayzeka/models/Qwen3-8B-inonu"
LF_DIR="/home/yapayzeka/LLaMA-Factory"

# 2. Veri setini LLaMA-Factory'ye tanıt (dataset_info.json güncellemesi)
echo "📋 Veri seti LLaMA-Factory'e tanımlanıyor..."
python3 -c "
import json, os
info_path = '$LF_DIR/data/dataset_info.json'
if os.path.exists(info_path):
    with open(info_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
else:
    data = {}

data['inonu_qa'] = {
  'file_name': '$DATA_FILE',
  'formatting': 'sharegpt',
  'columns': {
    'messages': 'conversations'
  },
  'tags': {
    'role_tag': 'from',
    'content_tag': 'value',
    'user_tag': 'human',
    'assistant_tag': 'gpt'
  }
}

with open(info_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
"

# 3. YAML Konfigürasyonunu Oluştur
cat <<EOF > $PROJECT_DIR/train_config.yaml
### model
model_name_or_path: $BASE_MODEL

### method
stage: sft
do_train: true
finetuning_type: lora
lora_target: all
lora_rank: 16
lora_alpha: 32

### dataset
dataset: inonu_qa
template: qwen
cutoff_len: 2048
max_samples: 20000
overwrite_cache: true
preprocessing_num_workers: 16

### output
output_dir: $OUTPUT_DIR
logging_steps: 10
save_steps: 500
plot_loss: true
overwrite_output_dir: true

### train
per_device_train_batch_size: 4
gradient_accumulation_steps: 4
learning_rate: 2.0e-4
num_train_epochs: 3.0
lr_scheduler_type: cosine
warmup_ratio: 0.1
bf16: true
flash_attn: fa2

EOF

echo "⚙️ Eğitim yapılandırması oluşturuldu: train_config.yaml"

# 4. Eğitimi Başlat
echo "🔥 QLoRA Eğitimi L40S üzerinde başlatılıyor..."
cd $LF_DIR
llamafactory-cli train $PROJECT_DIR/train_config.yaml

# 5. Eğitilmiş Modeli Merge Et (Birleştir)
echo "🧩 LoRA adaptörleri ana modelle birleştiriliyor..."

cat <<EOF > $PROJECT_DIR/merge_config.yaml
### Note: DO NOT use quantized model or quantization_bit when merging lora adapters

### model
model_name_or_path: $BASE_MODEL
adapter_name_or_path: $OUTPUT_DIR
template: qwen
finetuning_type: lora

### export
export_dir: $MERGE_DIR
export_size: 2
export_device: auto
export_legacy_format: false
EOF

llamafactory-cli export $PROJECT_DIR/merge_config.yaml

echo "✅ TEBRİKLER! Eğitim tamamlandı ve yeni model şu dizine kaydedildi: $MERGE_DIR"
