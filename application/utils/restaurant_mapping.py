# application/utils/restaurant_mapping.py

RESTAURANT_TYPE_MAPPING = {
    "chinese": ["中式料理", "火鍋", "熱炒", "港式料理", "川菜"], # 確保包含資料集有的字眼
    "japanese": ["日式料理", "壽司", "燒烤", "拉麵"],
    "western": ["異國料理", "美式料理", "義式料理", "法式料理"],
    "cafe": ["咖啡甜點", "下午茶", "甜點冰品", "複合式料理"],
    "local": ["在地小吃", "傳統美食", "夜市", "小吃"]
}