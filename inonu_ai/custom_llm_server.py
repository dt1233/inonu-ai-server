from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
import warnings
import traceback

warnings.filterwarnings("ignore")

app = FastAPI()

model_path = "/home/yapayzeka/models/Qwen3-8B-inonu"
print("Model belleğe yükleniyor... (Yaklaşık 30 sn)")

tokenizer = AutoTokenizer.from_pretrained(model_path)
model = AutoModelForCausalLM.from_pretrained(
    model_path, 
    torch_dtype=torch.bfloat16, 
).to("cuda")

print("Model başarıyla yüklendi! Sunucu başlatılıyor...")

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        data = await request.json()
        messages = data.get("messages", [])
        
        max_tokens = data.get("max_tokens")
        if not max_tokens:
            max_tokens = 1024
            
        temperature = data.get("temperature", 0.6)
        do_sample = True
        
        # SIFIR SICAKLIK KONTROLU (Greedy Decoding)
        if temperature <= 0.0:
            temperature = 1.0 # 0 olamaz, uydurma degeri atiyoruz cunku do_sample=False ile zaten iptal olacak
            do_sample = False
            
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        
        pad_token_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id
        if isinstance(pad_token_id, list):
            pad_token_id = pad_token_id[0]
            
        with torch.no_grad():
            outputs = model.generate(
                **inputs, 
                max_new_tokens=max_tokens,
                temperature=temperature,
                top_p=data.get("top_p", 0.95),
                do_sample=do_sample,
                pad_token_id=pad_token_id
            )
        
        input_length = inputs["input_ids"].shape[1]
        response_text = tokenizer.decode(outputs[0][input_length:], skip_special_tokens=True)
        
        return {
            "id": "chatcmpl-v3",
            "object": "chat.completion",
            "created": 123456789,
            "model": "qwen3",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": response_text},
                "finish_reason": "stop"
            }]
        }
    except Exception as e:
        print("\n\n=== SUNUCUDA BIR HATA OLUSTU ===")
        traceback.print_exc()
        print("==================================\n\n")
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=30000)
