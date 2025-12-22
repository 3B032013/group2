import numpy as np
import torch
import torch.nn as nn
from torchvision import models, transforms

# 💡 必須與生成索引時的模型一致
model = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V1)
model = nn.Sequential(*list(model.children())[:-1])
model.eval()

preprocess = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

def search_similar_images(input_img, index_path, top_k=15):
    # 1. 載入索引檔
    feature_db = np.load(index_path, allow_pickle=True).item()
    
    # 2. 提取上傳圖片的特徵
    img_t = preprocess(input_img)
    batch_t = torch.unsqueeze(img_t, 0)
    with torch.no_grad():
        input_feature = model(batch_t).flatten().numpy()
        # 💡 方案一優化：單位化向量
        input_feature = input_feature / np.linalg.norm(input_feature)

    # 3. 計算相似度
    results = []
    for idx, db_feature in feature_db.items():
        # 💡 方案一優化：資料庫特徵也要單位化
        db_feature = db_feature / np.linalg.norm(db_feature)
        similarity = np.dot(input_feature, db_feature)
        results.append({"index": idx, "score": similarity})

    # 4. 排序
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]