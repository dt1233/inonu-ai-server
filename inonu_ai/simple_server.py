import os
import torch
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict
import uvicorn
from transformers import AutoModelForCausalLM, AutoTokenizer

app = FastAPI()

MODEL_PATH = "/home/yapayzeka/models/Qwen3-8B-inonu"
print("Model yükleniyor... Lütfen bekleyin (Bu işlem yaklaşık 1 dakika sürebilir)...")

tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH, 
    torch_dtype=torch.bfloat16, 
    device_map="auto"
)
print("Model başarıyla yüklendi! API Sunucusu başlatılıyor...")

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: str = "default"
    messages: List[Message]
    temperature: float = 0.2
    max_tokens: int = 512

@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    # ChatML formatına çevir
    prompt = ""
    for msg in req.messages:
        prompt += f"<|im_start|>{msg.role}\n{msg.content}<|im_end|>\n"
    prompt += "<|im_start|>assistant\n"
    
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=req.max_tokens,
            temperature=req.temperature,
            do_sample=True if req.temperature > 0 else False,
            pad_token_id=tokenizer.eos_token_id
        )
    
    # Sadece yeni üretilen tokenları al
    input_length = inputs.input_ids.shape[1]
    generated_tokens = outputs[0][input_length:]
    response_text = tokenizer.decode(generated_tokens, skip_special_tokens=True)
    
    return {
        "choices": [
            {
                "message": {
                    "content": response_text
                }
            }
        ]
    }

@app.get("/v1/models")
async def get_models():
    return {"data": [{"id": "Qwen3-8B-inonu"}]}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=30000)
