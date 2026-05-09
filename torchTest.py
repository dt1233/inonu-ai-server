import torch

print("CUDA Aktif mi:", torch.cuda.is_available())

gpu_sayisi = torch.cuda.device_count()
print(f"Toplam GPU sayısı: {gpu_sayisi}")

if torch.cuda.is_available():
    print("\nAlgılanan Ekran Kartları:")
    # Algılanan toplam GPU sayısı kadar döngü oluşturur
    for i in range(gpu_sayisi):
        print(f"GPU {i}: {torch.cuda.get_device_name(i)}")
else:
    print("CUDA destekli bir ekran kartı bulunamadı.")