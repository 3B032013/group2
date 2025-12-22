import pandas as pd
from .data_clean import _ATTRACTION_CLASS_MAP

ALERT_RANK_MAP = {'灰色': 2, '黃色': 3, '橙色': 4}
ALL_COMPARE_METRICS = ['safety', 'cpi', 'pce', 'accommodation', 'transportation', 'travelers']
TAB_STYLE = {
    'idle': {
        'borderRadius': '10px','padding': '0px','marginInline': '5px','display':'flex',
        'alignItems':'center','justifyContent':'center','fontWeight': 'bold',
        'backgroundColor': '#deb522','border':'none'
    },
    'active': {
        'borderRadius': '10px','padding': '0px','marginInline': '5px','display':'flex',
        'alignItems':'center','justifyContent':'center','fontWeight': 'bold','border':'none',
        'textDecoration': 'underline','backgroundColor': '#deb522'
    }
}

def get_constants(attraction_df):
    """
    計算旅遊資料的主要統計數據 (Compute key travel statistics).

    包含：
        - 總旅遊國家數 (Number of destination countries)
        - 總旅遊人數 (Number of travelers)
        - 總國籍數 (Number of traveler nationalities)
        - 平均旅遊天數 (Average travel duration, 四捨五入到小數點一位)

    參數 (Args):
        travel_df (pandas.DataFrame): 旅遊資料的 DataFrame。

    回傳 (Returns):
        tuple: (num_of_country, num_of_traveler, num_of_nationality, avg_days)
    """
    # 總縣市數
    num_of_city = attraction_df['PostalAddress.City'].nunique()
    
    # 總鄉鎮數
    num_of_town = attraction_df['PostalAddress.Town'].nunique()

    # 總景點數
    nums_of_name = attraction_df['AttractionID'].nunique()

    # 平均旅遊天數
    # avg_days = round(float(attraction_df['Duration (days)'].mean()), 1)

    return num_of_city, num_of_town, nums_of_name

def get_constants_event(event_df):
    # 總活動數
    nums_of_name = event_df['EventID'].nunique()

    return nums_of_name

def get_constants_hotel(hotel_df):
    # 總住宿數
    nums_of_name = hotel_df['HotelID'].nunique()

    return nums_of_name

def get_constants_restaurant(restaurant_df):
    # 總餐廳數
    nums_of_name = restaurant_df['RestaurantID'].nunique()

    return nums_of_name