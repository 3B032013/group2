import os
import json
import pandas as pd
import requests
import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image
from io import BytesIO
import numpy as np
from tqdm import tqdm
import urllib.parse

# 1. 模型初始化 (ResNet-50)
model = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V1)
model = nn.Sequential(*list(model.children())[:-1])
model.eval()

preprocess = transforms.Compose([
    transforms.Resize(256), transforms.CenterCrop(224),
    transforms.ToTensor(), transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

def run_all():
    # 路徑設定
    data_dir = r'c:\Users\Jhen\Desktop\group2\group2-master\data'
    json_path = os.path.join(data_dir, 'AttractionList.json')
    img_dir = os.path.join(data_dir, 'attraction_images')
    output_npy = os.path.join(data_dir, 'attraction_image_index.npy')
    
    if not os.path.exists(img_dir): os.makedirs(img_dir)

    print(f"正在讀取 JSON: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        full_data = json.load(f)
    
    # 💡 關鍵修正：進入 Attractions 層級
    attractions_list = full_data.get('Attractions', [])
    print(f"成功解析！共有 {len(attractions_list)} 筆景點資料。")

    feature_db = {}
    success_count = 0
    
    # 建議先測試 3000 筆，看鳥的照片有沒有變準
    test_limit = 3000 
    
    print(f"開始下載圖片並建立 ResNet-50 特徵索引 (預計處理前 {test_limit} 筆)...")
    
    for i, item in enumerate(tqdm(attractions_list[:test_limit])):
        attr_id = item.get('AttractionID')
        images = item.get('Images', [])
        
        if not images or not attr_id:
            continue
            
        # 取得第一張圖片網址
        raw_url = images[0].get('URL')
        if not raw_url:
            continue
            
        try:
            # 處理網址中的特殊字元編碼
            encoded_url = urllib.parse.quote(raw_url, safe='/:?=&')
            # 💡 增加 headers 並關閉 SSL 驗證，通常可以抓到更多政府網站圖片
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            resp = requests.get(encoded_url, headers=headers, timeout=10, verify=False)
            
            if resp.status_code == 200:
                img = Image.open(BytesIO(resp.content)).convert('RGB')
                
                # 儲存實體照片到資料夾
                img_filename = f"{attr_id}.jpg"
                img.save(os.path.join(img_dir, img_filename))

                # 提取 AI 特徵向量
                img_t = preprocess(img)
                batch_t = torch.unsqueeze(img_t, 0)
                with torch.no_grad():
                    feat = model(batch_t).flatten().numpy()
                    feat = feat / np.linalg.norm(feat) # 單位化提高精準度
                
                feature_db[attr_id] = feat
                success_count += 1
        except Exception as e:
            # print(f"跳過 {attr_id}: {e}")
            continue

    # 儲存索引
    np.save(output_npy, feature_db)
    print(f"\n🎉 大功告成！")
    print(f"成功下載圖片數量: {success_count}")
    print(f"請確認此路徑已有照片: {img_dir}")

if __name__ == "__main__":
    run_all()