import os
import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image
import numpy as np
from tqdm import tqdm # 顯示進度條

# 1. 初始化 ResNet-50 模型 (方案一)
# ResNet-50 辨識複雜特徵(如鳥類、果實)的能力比 ResNet-18 強很多
model = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V1)
model = nn.Sequential(*list(model.children())[:-1]) # 移除最後的分類層
model.eval()

# 2. 定義影像預處理
preprocess = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

def generate_npy_index(image_folder, output_path):
    feature_db = {}
    
    # 支援的圖片格式
    valid_extensions = ('.jpg', '.jpeg', '.png', '.webp')
    
    # 取得資料夾內所有圖片
    image_files = [f for f in os.listdir(image_folder) if f.lower().endswith(valid_extensions)]
    
    print(f"開始提取特徵，共 {len(image_files)} 張圖片...")
    
    for filename in tqdm(image_files):
        try:
            # 假設檔名就是你的 AttractionID (例如: 101.jpg -> ID 為 101)
            # 如果你的檔名規則不同，請修改這裡
            attr_id = os.path.splitext(filename)[0]
            
            img_path = os.path.join(image_folder, filename)
            img = Image.open(img_path).convert('RGB')
            
            # 預處理與提取特徵
            img_t = preprocess(img)
            batch_t = torch.unsqueeze(img_t, 0)
            
            with torch.no_grad():
                feature = model(batch_t).flatten().numpy()
            
            # 存入字典
            feature_db[attr_id] = feature
            
        except Exception as e:
            print(f"處理 {filename} 時發生錯誤: {e}")

    # 儲存為 npy 檔案
    np.save(output_path, feature_db)
    print(f"✅ 索引檔已更新並儲存至: {output_path}")

if __name__ == "__main__":
    # --- 請修改以下路徑 ---
    IMAGE_FOLDER = "./data/attraction_images"  # 你的景點圖片路徑
    OUTPUT_FILE = "./data/attraction_image_index.npy"  # 輸出的索引檔路徑
    
    generate_npy_index(IMAGE_FOLDER, OUTPUT_FILE)