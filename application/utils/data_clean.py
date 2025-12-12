import pandas as pd
import json
import numpy as np
from typing import List, Dict, Any, Union

def travel_data_clean(travel_df):
    travel_df = travel_df.copy()
    # 去除空值    
    travel_df = travel_df.dropna()

    # 將花費欄位從str轉換成int
    travel_df['Accommodation cost'] = travel_df['Accommodation cost'].str.replace('$', '')
    travel_df['Accommodation cost'] = travel_df['Accommodation cost'].str.replace(',', '')
    travel_df['Accommodation cost'] = travel_df['Accommodation cost'].str.replace(' USD', '')
    travel_df['Accommodation cost'] = travel_df['Accommodation cost'].astype(float)

    travel_df['Transportation cost'] = travel_df['Transportation cost'].str.replace('$', '')
    travel_df['Transportation cost'] = travel_df['Transportation cost'].str.replace(',', '')
    travel_df['Transportation cost'] = travel_df['Transportation cost'].str.replace(' USD', '')
    travel_df['Transportation cost'] = travel_df['Transportation cost'].astype(float)

    # 將日期欄位從str轉換成datetime
    travel_df['Start date'] = pd.to_datetime(travel_df['Start date'])
    travel_df['End date'] = pd.to_datetime(travel_df['End date'])

    # 新增總花費欄位
    travel_df['Total cost'] = travel_df['Accommodation cost'] + travel_df['Transportation cost']

    # 將年齡劃分成不同區間 - 5歲一組
    # 先取出最大最小值
    min_age = travel_df['Traveler age'].min()
    max_age = travel_df['Traveler age'].max()
    # 以5歲為一組，劃分年齡區間
    bins = list(range(int(min_age), int(max_age), 5))
    # 將年齡區間轉換成str
    labels = [f'{i}-{i+4}' for i in bins[:-1]]
    # 將年齡區間新增到DataFrame中
    travel_df['Age group'] = pd.cut(travel_df['Traveler age'], bins=bins, labels=labels)

    # 依照旅遊開始日期劃分月份
    travel_df['Start month'] = travel_df['Start date'].dt.month
    # 將月份轉換成英文
    travel_df['Start month'] = travel_df['Start month'].map({1: 'January', 2: 'February', 3: 'March', 4: 'April', 5: 'May', 6: 'June', 7: 'July', 8: 'August', 9: 'September', 10: 'October', 11: 'November', 12: 'December'})

    return travel_df

def countryinfo_data_clean(countryinfo_df):
    # 去除空值
    countryinfo_df = countryinfo_df.dropna()

    return countryinfo_df

def data_merge(df_travel, df_countryinfo):

    df_countryinfo = df_countryinfo.rename(columns={'Country': 'Destination'})

    df = pd.merge(df_travel, df_countryinfo, on='Destination', how='left')

    return df

# Attraction景點
# ==========================================================
# 內部輔助函式 (Internal Helper Functions)
# ==========================================================

def _load_and_normalize_json(file_path: str, list_key: str) -> pd.DataFrame:
    """
    內部輔助函式：載入 JSON 檔案，提取指定鍵下的列表，並規範化為 DataFrame。
    """
    try:
        # 載入 JSON 檔案內容
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
        
        # 提取景點/費用/時間列表
        data_list = data.get(list_key)
        if not isinstance(data_list, list):
             print(f"錯誤：檔案 {file_path} 中找不到鍵 '{list_key}' 或其內容不是列表。")
             return pd.DataFrame()
        
        # 使用 json_normalize 處理巢狀結構
        return pd.json_normalize(data_list)
        
    except FileNotFoundError:
        print(f"錯誤：找不到檔案 {file_path}。請確認路徑設定。")
        return pd.DataFrame()
    except Exception as e:
        print(f"載入 {file_path} 時發生錯誤: {e}")
        return pd.DataFrame()


def _summarize_list_data(
    data_list: List[Dict[str, Any]], 
    name_key: str, 
    value_key: str, 
    is_fee: bool = False, 
    is_time: bool = True  # 假設預設為時間格式，因為 ServiceTimes 更常見
) -> Union[str, float]:  # 將回傳類型改為 Union[str, float] 以兼容 np.nan
    """
    內部輔助函式：用於將巢狀列表（Fees, ServiceTimes）轉換為單一摘要字串。
    """
    if not isinstance(data_list, list) or not data_list:
        return np.nan
    
    summary = []
    for item in data_list:
        name = item.get(name_key, '項目')
        
        if is_fee:
            # 費用 (Fees) 處理 (value_key='Price')
            value = item.get(value_key)
            # 這裡 Price 欄位可能是字串或數值，假設您已處理為數值
            price_value = float(value) if isinstance(value, (int, float, str)) and str(value).isdigit() else None
            
            if value_key == 'Price':
                price_str = f"${int(price_value)}" if price_value is not None and price_value > 0 else "免費"
                summary.append(f"{name}: {price_str}")
            else:
                summary.append(f"{name}: {value}")
                
        elif is_time:
            # 服務時間 (ServiceTimes) 處理 (通常 value_key='ServiceDays')
            days_list = item.get('ServiceDays', [])
            days = ", ".join(days_list)
            
            # 對於公休日/休假日，只顯示日期
            if name in ["公休日", "休假日"] or not days_list:
                 summary.append(f"{name}: {days}")
                 continue

            start = item.get('StartTime', '')
            end = item.get('EndTime', '')
            summary.append(f"{name}: ({days}) {start} - {end}")
            
        else:
            # 一般列表摘要 (例如電話，簡單顯示名稱和值)
             summary.append(f"{name}: {item.get(value_key, 'N/A')}")
            
    return "\n".join(summary)

def _convert_classes_to_names(class_list):
    """將景點類別的數字列表轉換為中文名稱字串，例如 [16] -> '森林遊樂區類'"""
    # ... (此函式保持不變) ...
    if not isinstance(class_list, list) or not class_list:
        return np.nan
    
    names = [_ATTRACTION_CLASS_MAP.get(code, f"未知代碼({code})") for code in class_list]
    return ", ".join(names)

def _convert_classes_to_names_event(class_list):
    """將景點類別的數字列表轉換為中文名稱字串，例如 [16] -> '森林遊樂區類'"""
    # ... (此函式保持不變) ...
    if not isinstance(class_list, list) or not class_list:
        return np.nan
    
    names = [_EVENT_CLASS_MAP.get(code, f"未知代碼({code})") for code in class_list]
    return ", ".join(names)

def _get_thumbnail_url(images_list):
    """從 Images 列表中提取第一張圖片的 URL 作為縮圖。"""
    if isinstance(images_list, list) and len(images_list) > 0:
        # 提取列表中的第一個物件，並從中獲取 'URL' 鍵的值
        return images_list[0].get('URL', np.nan)
    return np.nan

# ==========================================================
# 內部常數與映射 (Internal Constants and Maps)
# ==========================================================

# 景點類別代碼到中文名稱的映射字典
_ATTRACTION_CLASS_MAP = {
    1: "文化類", 3: "文化資產類", 5: "藝術類", 
    7: "國家公園類", 9: "休閒農業類", 11: "自然風景類", 
    13: "體育健身類", 15: "都會公園類", 17: "平地森林園區類", 
    19: "公園綠地類", 21: "原住民文化類", 23: "交通場站類", 
    25: "藝文場館類", 27: "娛樂場館類", 2: "生態類", 
    4: "宗教廟宇類", 6: "商圈商店類", 8: "國家風景區類", 
    10: "溫泉類", 12: "遊憩類", 14: "觀光工廠類", 
    16: "森林遊樂區類", 18: "國家自然公園類", 20: "觀光遊樂業類", 
    22: "客家文化類", 24: "水域環境類", 26: "生態場館類", 
    254: "其他"
}

_EVENT_CLASS_MAP = {
    # 主要大類 (Primary Categories)
    1: "節慶活動",
    2: "藝文活動",
    3: "年度活動",
    4: "遊憩活動",
    5: "地方社區型活動",
    9: "其他活動",
    
    # 節慶活動子類 (Sub-categories of 1)
    101: "節慶活動 - 傳統民俗型",
    102: "節慶活動 - 宗教信仰型",
    103: "節慶活動 - 原住民文化型",
    104: "節慶活動 - 客家文化型",
    105: "節慶活動 - 藝文慶典活動",
    106: "節慶活動 - 生態體驗型",
    107: "節慶活動 - 地方特產型",
    108: "節慶活動 - 娛樂型活動",
    109: "節慶活動 - 體育賽會活動",
    110: "節慶活動 - 商貿會展型",
    
    # 藝文活動子類 (Sub-categories of 2)
    201: "藝文活動 - 音樂",
    202: "藝文活動 - 戲劇",
    203: "藝文活動 - 舞蹈",
    204: "藝文活動 - 親子",
    205: "藝文活動 - 獨立音樂",
    206: "藝文活動 - 展覽",
    207: "藝文活動 - 講座",
    208: "藝文活動 - 電影",
    209: "藝文活動 - 綜藝",
    210: "藝文活動 - 競賽",
    211: "藝文活動 - 徵選",
    212: "藝文活動 - 演唱會",
    213: "藝文活動 - 研習課程",
    214: "藝文活動 - 閱讀",
    215: "藝文活動 - 其他藝文活動",
}

HOTEL_CLASS_MAP = {
    1: "國際觀光旅館",
    2: "一般觀光旅館",
    3: "一般旅館",
    4: "民宿",
    5: "露營區",
    9: "其他"
}

HOTEL_STARS_MAP = {
    0: "無星級",
    1: "1 星級",
    2: "2 星級",
    3: "3 星級",
    4: "4 星級",
    5: "5 星級",
    6: "卓越 5 星級"
}

# ==========================================================
# 核心公開函式 (Core Public Function)
# ==========================================================

def _convert_classes_to_names(class_list):
    """將景點類別的數字列表轉換為中文名稱字串，例如 [16] -> '森林遊樂區類'"""
    if not isinstance(class_list, list) or not class_list:
        return np.nan
    
    # 假設 _ATTRACTION_CLASS_MAP 是一個全局可用的字典
    names = [_ATTRACTION_CLASS_MAP.get(code, f"未知代碼({code})") for code in class_list]
    return ", ".join(names)

# --------------------------------------------------------------------------

def _get_main_telephone(telephones_list):
    """從 Telephones 列表中提取第一個電話號碼"""
    if isinstance(telephones_list, list) and telephones_list and 'Tel' in telephones_list[0]:
        return telephones_list[0]['Tel']
    return np.nan

# --------------------------------------------------------------------------

def load_and_merge_attractions_data(
    attraction_path: str, 
    fee_path: str, 
    service_time_path: str
) -> pd.DataFrame:
    """
    主要函式：載入三個景點相關的 JSON 檔案，並進行資料清理、
    合併、摘要化，最終回傳單一的景點資訊 DataFrame。
    """
    print("--- 開始載入並處理景點 JSON 資料 ---")

    # 1. 載入並規範化三個獨立的 DataFrame
    df_main = _load_and_normalize_json(attraction_path, "Attractions")
    df_fees = _load_and_normalize_json(fee_path, "AttractionFees")
    df_service = _load_and_normalize_json(service_time_path, "AttractionServiceTimes")

    if df_main.empty:
        print("景點主檔載入失敗或為空。")
        return pd.DataFrame()
    
    df_main_processed = df_main.copy()
        
    # --- 預處理步驟 2.1：處理主檔巢狀欄位 ---
    
    # 景點類別轉換
    if 'AttractionClasses' in df_main_processed.columns:
        df_main_processed['AttractionCategory'] = df_main_processed['AttractionClasses'].apply(_convert_classes_to_names)
    
    # 提取縮圖 URL
    if 'Images' in df_main_processed.columns:
        df_main_processed['ThumbnailURL'] = df_main_processed['Images'].apply(_get_thumbnail_url)
        
    # ⭐️ 提取主要電話號碼
    if 'Telephones' in df_main_processed.columns:
        df_main_processed['MainTelephone'] = df_main_processed['Telephones'].apply(_get_main_telephone)

    # 刪除原始的 PostalAddress 欄位 (假設攤平後 PostalAddress.City 等已存在)
    df_main_processed = df_main_processed.drop(columns=['PostalAddress'], errors='ignore')
    
    # 2. 處理 Fees 和 ServiceTimes 的巢狀列表並建立摘要欄位
    if not df_fees.empty:
        df_fees['FeesSummary'] = df_fees['Fees'].apply(
            lambda x: _summarize_list_data(x, 'Name', 'Price', is_fee=True)
        )
    
    if not df_service.empty:
        # 這裡 is_fee=False 是正確的，假設 _summarize_list_data 也能處理 ServiceTimes
        df_service['ServiceTimesSummary'] = df_service['ServiceTimes'].apply(
            lambda x: _summarize_list_data(x, 'Name', 'ServiceDays', is_fee=False) 
        )
    
    # 3. 進行資料合併
    df_combined = df_main_processed
        
    if 'FeesSummary' in df_fees.columns:
        df_combined = df_combined.merge(
            df_fees[['AttractionID', 'FeesSummary']], 
            on='AttractionID', 
            how='left'
        )
        
    if 'ServiceTimesSummary' in df_service.columns:
        df_combined = df_combined.merge(
            df_service[['AttractionID', 'ServiceTimesSummary']], 
            on='AttractionID', 
            how='left'
        )
        
    # 4. 最終清理、重新命名和選擇關鍵欄位
    df_combined = df_combined.rename(
        columns={'PositionLat': 'Lat', 'PositionLon': 'Lon'}
    )

    df_combined['PrimaryCategory'] = df_combined['AttractionCategory'].str.split(',').str[0].str.strip()
    
    FINAL_COLUMNS = [
        # 核心識別與地理資訊
        'AttractionID', 'AttractionName', 'Description', 
        'Lat', 'Lon', 
        
        # 類別與圖片
        'PrimaryCategory', 'AttractionCategory', 'ThumbnailURL',
        'PostalAddress.City', 'PostalAddress.Town', # 假設已經攤平
        
        # 摘要與服務
        'FeesSummary', 'ServiceTimesSummary',
        'IsAccessibleForFree', 'MainTelephone', # ⭐️ 新增 MainTelephone
        
        # 其他資訊
        'WebsiteURL', 'TrafficInfo', 'ParkingInfo', 'FeeInfo',
        
        # 原始複雜欄位 (如果您確定要保留，請確保它們是單一值)
        'Images',
        # 'Telephones', 
        
        'UpdateTime',
    ]
    
    # 過濾只保留需要的欄位
    attraction_df = df_combined.filter(items=FINAL_COLUMNS)
    
    print(f"--- 景點資料處理完畢。總筆數: {len(attraction_df)} ---")
    return attraction_df

def load_and_clean_event_data(event_path: str) -> pd.DataFrame:
    """
    載入 Event JSON 資料，進行清洗和特徵工程。
    """
    print("--- 開始載入並處理活動 JSON 資料 ---")
    
    # 載入 EventList.json，主列表鍵為 'Events'
    event_df = _load_and_normalize_json(event_path, 'Events')
    
    if event_df.empty:
        print("--- 活動資料載入失敗或為空 ---")
        return pd.DataFrame()

    # ==========================================================
    # 2. 處理時間欄位：轉換為 datetime 格式並計算持續天數
    # ==========================================================
    time_cols = ['StartDateTime', 'EndDateTime']
    
    for col in time_cols:
        if col in event_df.columns:
            event_df[col] = pd.to_datetime(event_df[col], errors='coerce', utc=True)
            
    if all(col in event_df.columns for col in time_cols):
        event_df['DurationDays'] = (event_df['EndDateTime'] - event_df['StartDateTime']).dt.days + 1
        
    # ==========================================================
    # 3. 處理 EventClasses (活動類別)
    # ==========================================================
    event_df = event_df.rename(columns={'EventClasses': 'EventCategoryIDs'})
    
    # ⭐️ 建議修改 1: 轉換 EventCategoryIDs 為中文名稱
    if 'EventCategoryIDs' in event_df.columns:
        # 假設 _convert_classes_to_names 已經在某處定義並可存取
        event_df['EventCategoryNames'] = event_df['EventCategoryIDs'].apply(_convert_classes_to_names_event)
    else:
        event_df['EventCategoryNames'] = np.nan
        
    # ⭐️ 建議修改 3: 確保經緯度為 float 類型
    for col in ['PositionLat', 'PositionLon']:
        if col in event_df.columns:
            event_df[col] = pd.to_numeric(event_df[col], errors='coerce')
    
    event_df = event_df.rename(
        columns={'PositionLat': 'Lat', 'PositionLon': 'Lon'}
    )

    # ==========================================================
    # 4. 欄位整理
    # ==========================================================
    keep_cols = [
        'EventID', 'EventName', 'Description', 'PostalAddress.City', 'PostalAddress.Town',
        'Lat', 'Lon', 'StartDateTime', 'EndDateTime', 
        'DurationDays', 
        'EventCategoryIDs', 
        'EventCategoryNames', # ⭐️ 建議修改 2: 加入中文名稱欄位
        'EventStatus'
    ]
    
    final_event_df = event_df.reindex(columns=keep_cols)
    
    print(f"--- 活動資料處理完畢。總筆數: {len(final_event_df)} ---")
    
    return final_event_df.copy()

def load_and_clean_hotel_data(hotel_path: str) -> pd.DataFrame:
    """
    載入 Hotel JSON 資料，進行清洗和特徵工程。
    """
    print("--- 開始載入並處理旅館 JSON 資料 ---")
    
    # 1. 載入並規範化 (假設主列表鍵為 'Hotels')
    # ⚠️ 這裡需要您的 _load_and_normalize_json 函式來實現
    hotel_df = _load_and_normalize_json(hotel_path, 'Hotels')
    
    if hotel_df.empty:
        print("--- 旅館資料載入失敗或為空 ---")
        return pd.DataFrame()

    # ==========================================================
    # 2. 處理巢狀或列表欄位
    # ==========================================================
    
    # 提取第一個電話號碼
    if 'Telephones' in hotel_df.columns:
        hotel_df['MainTelephone'] = hotel_df['Telephones'].apply(
            lambda x: x[0]['Tel'] if isinstance(x, list) and x else None
        )
    
    # 提取第一個圖片 URL 作為縮圖
    if 'Images' in hotel_df.columns:
        hotel_df['ThumbnailURL'] = hotel_df['Images'].apply(
            lambda x: x[0]['URL'] if isinstance(x, list) and x and 'URL' in x[0] else None
        )

    # 提取 HotelClasses 的第一個類別代碼
    if 'HotelClasses' in hotel_df.columns:
        hotel_df['MainHotelClass'] = hotel_df['HotelClasses'].apply(
            lambda x: x[0] if isinstance(x, list) and x else None
        )
    
    # 將 ServiceInfo 字串轉為列表 (用於後續分析)
    if 'ServiceInfo' in hotel_df.columns:
        hotel_df['ServiceList'] = hotel_df['ServiceInfo'].str.split(',')
    
    # ==========================================================
    # 3. 數值/地理欄位處理與**分類代碼轉換**
    # ==========================================================
    
    # 數值/地理處理
    for col in ['PositionLat', 'PositionLon', 'TotalRooms', 'LowestPrice', 'CeilingPrice', 'TotalCapacity']:
        if col in hotel_df.columns:
            # 將欄位名稱標準化並轉為數字
            new_col = col.replace('Position', '')
            hotel_df[new_col] = pd.to_numeric(hotel_df[col], errors='coerce')
    
    # ⭐️ 類別代碼轉換：旅宿類型
    if 'MainHotelClass' in hotel_df.columns:
        hotel_df['HotelClassName'] = hotel_df['MainHotelClass'].map(HOTEL_CLASS_MAP).fillna('未知類型')
        
    # ⭐️ 類別代碼轉換：旅館星級
    if 'HotelStars' in hotel_df.columns:
        hotel_df['HotelStarsName'] = hotel_df['HotelStars'].map(HOTEL_STARS_MAP).fillna('未知星級')

    # ==========================================================
    # 4. 欄位整理
    # ==========================================================
    keep_cols = [
        # 核心識別與地理
        'HotelID', 'HotelName', 'Description', 
        'PostalAddress.City', 'PostalAddress.Town',
        'Lat', 'Lon', 
        
        # 價格與容量
        'TotalRooms', 'LowestPrice', 'CeilingPrice', 'TotalCapacity',
        
        # 分類與服務 (新增中文名稱)
        'MainHotelClass', 'HotelClassName', 
        'HotelStars', 'HotelStarsName', 'TaiwanHost',
        'ServiceInfo', 'ServiceList', 'Facilities', 'PaymentMethods',
        'MainTelephone', 'ThumbnailURL',
        
        # 額外資訊
        'TrafficInfo', 'ParkingInfo', 'WebsiteURL', 'UpdateTime'
    ]
    
    # 只保留我們需要的欄位
    final_hotel_df = hotel_df.filter(items=keep_cols)
    
    # 清理不必要的空格
    if 'HotelName' in final_hotel_df.columns:
        final_hotel_df['HotelName'] = final_hotel_df['HotelName'].str.strip()

    print(f"--- 旅館資料處理完畢。總筆數: {len(final_hotel_df)} ---")
    return final_hotel_df.copy()


# ==========================================================
# 1. 餐廳分類和特色映射字典
# ==========================================================

# 18. 餐飲料理類型代碼 (CuisineClassEnum)
CUISINE_CLASS_MAP = {
    1: "台灣小吃/台菜", 2: "中式料理", 3: "港式料理", 4: "日式料理",
    5: "韓式料理", 96: "南亞料理", 97: "東南亞料理", 98: "美式/歐式料理",
    99: "其他異國料理", 100: "夜市小吃", 101: "甜點冰品", 102: "麵包糕點",
    103: "非酒精飲品", 104: "酒類飲品", 105: "燒烤/鐵板燒", 106: "火鍋",
    107: "海鮮", 108: "牛排", 109: "速食", 110: "連鎖餐飲",
    111: "吃到飽", 112: "便當/自助餐", 113: "牛肉麵", 114: "粥品",
    115: "地方特產", 116: "伴手禮/禮盒", 200: "純素飲食", 201: "素食飲食",
    202: "清真飲食", 203: "無麩質飲食", 204: "健康飲食", 254: "其他",
}

# 19. 餐飲特色資料代碼 (RestaurantFeatureEnum)
RESTAURANT_FEATURE_MAP = {
    1: "素食餐廳", 2: "無障礙餐廳", 3: "寵物友善", 4: "兒童友善",
    5: "性別友善", 6: "禁菸餐廳", 7: "現場音樂表演", 8: "室外雅座",
    9: "頂樓座位", 10: "餐桌服務", 99: "其他服務", 101: "內用",
    102: "外帶", 103: "外送", 104: "預訂", 105: "免下車服務",
    106: "外燴", 107: "團膳", 108: "路邊取貨", 109: "無接觸送餐服務",
    201: "米其林指南一星", 202: "米其林指南二星", 203: "米其林指南三星",
    204: "米其林指南必比登推薦", 205: "米其林綠星", 206: "穆斯林認證餐廳",
    254: "其他",
}

# ==========================================================
# 2. 輔助函式
# ==========================================================

def _convert_codes_to_names(codes: List[int], code_map: Dict[int, str]) -> Union[str, float]:
    """將代碼列表轉換為中文名稱的逗號分隔字串"""
    if not isinstance(codes, list) or not codes:
        return np.nan
    
    names = [code_map.get(code, f'未知代碼({code})') for code in codes]
    return ", ".join(names)


def _summarize_list_restaurant_data(data_list: List[Dict[str, Any]], name_key: str, value_key: str) -> Union[str, float]:
    """
    輔助函式：將 RestaurantServiceTimes 的巢狀列表轉換為摘要字串。
    """
    if not isinstance(data_list, list) or not data_list:
        return np.nan
    
    summaries = []
    for item in data_list:
        name = item.get(name_key, 'N/A')
        # 處理 ServiceTimes 的時間和服務日
        days = item.get(value_key, [])
        day_count = len(days)
        
        if name in ["公休日", "休假日"] and day_count > 0:
            summaries.append(f"{name}: {', '.join(days)}")
            continue
            
        start = item.get('StartTime', 'N/A')
        end = item.get('EndTime', 'N/A')
        
        # 簡化服務日描述
        if day_count == 7:
            day_str = '每日'
        elif day_count > 0:
            day_str = f'每週{day_count}天'
        else:
            day_str = 'N/A'
            
        summaries.append(f"{name}: {day_str} ({start} - {end})")
            
    return " | ".join(summaries)


# ==========================================================
# 3. 主要載入與合併函式
# ==========================================================

def load_and_merge_restaurant_data(
    restaurant_path: str, 
    service_time_path: str
) -> pd.DataFrame:
    """
    主要函式：載入餐廳主檔和營業時間檔，進行清理和合併。
    """
    print("--- 開始載入並處理餐廳 JSON 資料 ---")

    # 1. 載入並規範化兩個獨立的 DataFrame
    # ⚠️ 請確保 _load_and_normalize_json 函式可用
    df_main = _load_and_normalize_json(restaurant_path, "Restaurants")
    df_service = _load_and_normalize_json(service_time_path, "RestaurantServiceTimes")

    if df_main.empty:
        print("餐廳主檔載入失敗或為空。")
        return pd.DataFrame()

    # --- 預處理步驟 2.1：處理主檔巢狀欄位與分類轉換 ---
    
    df_main = df_main.copy()

    # 提取第一個圖片 URL 作為縮圖
    if 'Images' in df_main.columns:
        df_main['ThumbnailURL'] = df_main['Images'].apply(
            lambda x: x[0]['URL'] if isinstance(x, list) and x and 'URL' in x[0] else np.nan
        )
    
    # 提取第一個電話號碼
    if 'Telephones' in df_main.columns:
        df_main['MainTelephone'] = df_main['Telephones'].apply(
            lambda x: x[0]['Tel'] if isinstance(x, list) and x else np.nan
        )
        
    # ⭐️ 轉換菜系類別代碼 (CuisineClasses)
    if 'CuisineClasses' in df_main.columns:
        df_main['CuisineNames'] = df_main['CuisineClasses'].apply(
            lambda x: _convert_codes_to_names(x, CUISINE_CLASS_MAP)
        )
    else:
        df_main['CuisineNames'] = np.nan
        
    # ⭐️ 轉換餐廳特色代碼 (RestaurantFeatures)
    if 'RestaurantFeatures' in df_main.columns:
        df_main['FeatureNames'] = df_main['RestaurantFeatures'].apply(
            lambda x: _convert_codes_to_names(x, RESTAURANT_FEATURE_MAP)
        )
    else:
        df_main['FeatureNames'] = np.nan
        
    # --- 預處理步驟 2.2：處理服務時間檔並建立摘要欄位 ---
    if not df_service.empty and 'ServiceTimes' in df_service.columns:
        df_service['ServiceTimesSummary'] = df_service['ServiceTimes'].apply(
            lambda x: _summarize_list_restaurant_data(x, 'Name', 'ServiceDays')
        )
    else:
        df_service['ServiceTimesSummary'] = np.nan
    
    # 3. 進行資料合併
    df_combined = df_main.copy()
    
    if 'ServiceTimesSummary' in df_service.columns:
        df_combined = df_combined.merge(
            df_service[['RestaurantID', 'ServiceTimesSummary']], 
            on='RestaurantID', 
            how='left'
        )
        
    # 4. 最終清理、重新命名和選擇關鍵欄位
    df_combined = df_combined.rename(
        columns={'PositionLat': 'Lat', 'PositionLon': 'Lon'}
    )
    
    FINAL_COLUMNS = [
        # 核心識別與地理資訊
        'RestaurantID', 
        'RestaurantName', 
        'Description', 
        'Lat', 
        'Lon', 
        'PostalAddress.City',
        'PostalAddress.Town',
        
        # 服務與分類資訊
        'CuisineClasses',           # 原始代碼
        'CuisineNames',             # 菜系分類中文名稱
        'RestaurantFeatures',       # 原始代碼
        'FeatureNames',             # 餐廳特色中文名稱
        'ServiceTimesSummary',      # 營業時間摘要
        'MainTelephone',
        'ThumbnailURL',
        'ServiceStatus',
        'ParkingInfo',
        'WebsiteURL',
        'UpdateTime',
    ]
    
    # 過濾只保留需要的欄位
    restaurant_df = df_combined.filter(items=FINAL_COLUMNS)
    
    # 清理不必要的空格
    if 'RestaurantName' in restaurant_df.columns:
        restaurant_df['RestaurantName'] = restaurant_df['RestaurantName'].str.strip()
        
    print(f"--- 餐廳資料處理完畢。總筆數: {len(restaurant_df)} ---")
    return restaurant_df