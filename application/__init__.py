import os
import json
import re
from datetime import datetime
import math

# Flask 與 Dash 核心
from flask import Flask, redirect
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from dash import Dash, html, dcc, Input, State, Output, dash_table, no_update, ctx
from dash.exceptions import PreventUpdate
from dash.dependencies import Input, Output, State, ALL
import dash_bootstrap_components as dbc
import dash_leaflet as dl
import plotly.express as px
import pandas as pd
import numpy as np
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from .utils.theme import THEME, TAB_STYLE, SIDEBAR_STYLE, CONTENT_STYLE, GRAPH_STYLE

db = SQLAlchemy()
login_manager = LoginManager()

from .nav_config import SIDEBAR_ITEMS
from .models import User, Favorite

# 1: Import 路徑
from .utils.const import get_constants, TAB_STYLE, ALL_COMPARE_METRICS, get_constants_event, get_constants_hotel, get_constants_restaurant
from .utils.data_clean import travel_data_clean, countryinfo_data_clean, data_merge, load_and_merge_attractions_data, load_and_clean_event_data, load_and_clean_hotel_data, load_and_merge_restaurant_data
from .utils.data_transform import (
    prepare_country_compare_data, 
    get_dashboard_default_values,
    get_dashboard_default_attraction_values,
    get_dashboard_default_hotel_values,
    get_dashboard_default_restaurant_values,
    get_exploded_categories,
    get_alert_rank, 
    sanitize_list_input,
    sanitize_cost_bounds,
    filter_by_cost_and_types,
    preprocess_attraction_df,
    preprocess_event_df,
    preprocess_hotel_df,
    preprocess_restaurant_df,
    pick_country_level,
    filter_by_alert_and_visa,
    compute_scores,
)
from .utils.visualization import (
    build_compare_figure, 
    generate_stats_card, 
    generate_bar, 
    generate_pie, 
    generate_map, 
    generate_box,
    build_table_component
)

########################
#### 2: 資料載入路徑修正 ####
########################

# 取得專案根目錄 (從 application/ 資料夾往上兩層)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

# 定義 helper 函數來組合路徑
def get_data_path(filename):
    return os.path.join(DATA_DIR, filename)

print(f"Loading data from: {DATA_DIR}") # Debug 用

# --- 資料載入與全域變數 (Global Scope) ---
# 這樣做的好處是資料只會被載入一次，不會每次 request 都重讀

ATTRACTION_JSON_PATH = get_data_path('AttractionList.json')
FEE_JSON_PATH = get_data_path('AttractionFeeList.json')
SERVICE_TIME_JSON_PATH = get_data_path('AttractionServiceTimeList.json')

attraction_df = load_and_merge_attractions_data(
    attraction_path=ATTRACTION_JSON_PATH,
    fee_path=FEE_JSON_PATH,
    service_time_path=SERVICE_TIME_JSON_PATH
)

EVENT_JSON_PATH = get_data_path('EventList.json')
event_df = load_and_clean_event_data(event_path=EVENT_JSON_PATH)

HOTEL_DATA_PATH = get_data_path('HotelList.json')
hotel_df = load_and_clean_hotel_data(HOTEL_DATA_PATH)

RESTAURANT_PATH = get_data_path('RestaurantList.json')
RESTAURANT_SERVICE_PATH = get_data_path('RestaurantServiceTimeList.json')

restaurant_df = load_and_merge_restaurant_data(
    restaurant_path=RESTAURANT_PATH,
    service_time_path=RESTAURANT_SERVICE_PATH,
)

# 為了兼容比較圖表的邏輯 (若有用到 df_merged 再保留)
# travel_df = ...
df_merged = pd.DataFrame() # 暫時給空值或是根據你的需求補上

# 統計數據計算
num_of_city, num_of_town, nums_of_name = get_constants(attraction_df)
nums_of_event_name = get_constants_event(event_df)
nums_of_hotel_name = get_constants_hotel(hotel_df)
nums_of_restaurant_name = get_constants_restaurant(restaurant_df)

# 設定 Overview 頁面預設值
DEFAULTS = get_dashboard_default_values(event_df)
DEFAULTS_attraction = get_dashboard_default_attraction_values(attraction_df)
DEFAULTS_hotel = get_dashboard_default_hotel_values(hotel_df)
DEFAULTS_restaurant = get_dashboard_default_restaurant_values(restaurant_df)


##########################
#### 3: 封裝 Callback ####
##########################
# 放到 app.py 或 __init__.py 的適當位置
def generate_trip_card(row, type_tag, user_favs=None):
    """
    生成 Trip Card，並根據 user_favs 決定愛心初始顏色
    """
    # ⭐️ 1. 確保 user_favs 是集合
    if user_favs is None:
        user_favs = set()

    # 圖片與基本資料處理
    img_url = row.get('ThumbnailURL') or row.get('Picture.PictureUrl1') or row.get('PictureUrl1')
    if not img_url: img_url = "https://placehold.co/600x400/f5f5f5/999?text=No+Image"

    name = row.get('AttractionName') or row.get('EventName') or row.get('HotelName') or row.get('RestaurantName') or '未命名'
    city = row.get('PostalAddress.City') or row.get('City') or ''
    location_str = f"{city}" 
    
    # ID 處理
    raw_id = row.get('AttractionID') or row.get('HotelID') or row.get('RestaurantID') or row.get('EventID')
    if raw_id is None or pd.isna(raw_id):
        item_id = f"idx-{row.name}"
    else:
        item_id = str(raw_id)

    # ⭐️ 2. 判斷顏色：如果 ID 在收藏名單內，就顯示紅色
    initial_color = '#dc3545' if item_id in user_favs else 'white'

    return html.Div(
        className="trip-card",
        children=[
            html.Div(
                [
                    html.Img(src=img_url, className="trip-card-img"),
                    
                    # ⭐️ 3. 設定按鈕樣式
                    dbc.Button(
                        html.Span("❤", className="heart-icon", style={'fontSize': '24px', 'lineHeight': '1', 'color': 'inherit'}),
                        id={'type': 'btn-add-favorite', 'index': item_id, 'category': type_tag},
                        className="btn-favorite-overlay",
                        style={'color': initial_color}, # 這裡設定顏色
                        n_clicks=0
                    )
                ],
                className="trip-card-img-container"
            ),
            html.Div(
                className="trip-card-body",
                children=[
                    html.Div([
                        html.Span(location_str, className="trip-location"),
                        html.Span(" • ", style={'margin': '0 5px', 'color': '#ccc'}),
                        html.Span(type_tag, style={'color': '#888'})
                    ], className="trip-tag-line"),
                    html.Div(name, className="trip-card-title", title=name),
                    html.Div([
                        dbc.Button(
                            "查看詳情 >", 
                            id={'type': 'btn-view-detail', 'index': item_id, 'category': type_tag},
                            color="link", 
                            className="link-details p-0", 
                            style={'textDecoration': 'none', 'fontWeight': '600'}
                        ),
                    ], className="trip-card-footer")
                ]
            )
        ]
    )

def create_detail_content(row, category):
    """
    根據資料列與類別，生成美化後的詳細內容 (含地圖、圖示與分塊資訊)
    """
    # --- 1. 基本資料提取 ---
    name = row.get('AttractionName') or row.get('EventName') or row.get('HotelName') or row.get('RestaurantName') or "未命名"
    desc = row.get('Description') or row.get('DescriptionSummary') or "暫無詳細介紹"
    
    # 地址清理
    city = str(row.get('PostalAddress.City', '')).replace('nan', '')
    town = str(row.get('PostalAddress.Town', '')).replace('nan', '')
    street = str(row.get('PostalAddress.StreetAddress', '')).replace('nan', '')
    full_address = f"{city}{town}{street}"
    if not full_address or full_address == "":
        full_address = row.get('Address') or row.get('Location') or "暫無地址資訊"

    # 電話與網頁
    tel = row.get('Telephones.Tel') or row.get('Phone') or row.get('MainTelephone') or '無電話資訊'
    website = row.get('WebsiteUrl') or row.get('Url')

    # 圖片處理
    img_url = row.get('ThumbnailURL') or row.get('Picture.PictureUrl1') or row.get('PictureUrl1')
    if not img_url or pd.isna(img_url): 
        img_url = "https://placehold.co/800x400/f5f5f5/999?text=No+Image"

    # 地標座標
    lat = row.get('Lat') or row.get('PositionLat')
    lon = row.get('Lon') or row.get('PositionLon')

    # --- 2. 建立動態資訊塊 (根據不同類別) ---
    specs = []
    
    # 類別標籤顏色
    cat_colors = {"景點": "info", "活動": "primary", "住宿": "warning", "餐廳": "success"}
    cat_color = cat_colors.get(category, "secondary")

    if category == "活動":
        start = str(row.get('StartDateTime', '')).split('T')[0]
        end = str(row.get('EndDateTime', '')).split('T')[0]
        specs.append(html.Div([
            html.I(className="bi bi-calendar-event-fill me-2 text-primary"),
            html.Span(f"活動期間：{start} 至 {end}", className="fw-bold")
        ], className="mb-2"))
        if row.get('Organizer'):
            specs.append(html.P([html.I(className="bi bi-people-fill me-2"), f"主辦單位：{row.get('Organizer')}"]))

    elif category == "住宿":
        grade = row.get('HotelStars')
        if grade and pd.notna(grade):
            specs.append(html.Div([
                html.I(className="bi bi-star-fill me-2 text-warning"),
                html.Span(f"評等：{grade} 星級飯店", className="fw-bold")
            ], className="mb-2"))
        if row.get('ServiceInfo'):
            specs.append(html.P([html.I(className="bi bi-info-circle-fill me-2"), f"設施服務：{row.get('ServiceInfo')}"]))

    elif category == "餐廳":
        cuisine = row.get('CuisineNames')
        if cuisine:
            specs.append(html.Div([
                html.I(className="bi bi-egg-fried me-2 text-success"),
                html.Span(f"料理種類：{cuisine}", className="fw-bold")
            ], className="mb-2"))

    # 共通：服務時間 (景點與餐廳常有)
    service_time = row.get('ServiceTimesSummary') or row.get('OpenTime')
    if service_time and pd.notna(service_time):
        time_lines = str(service_time).split('\n')
        specs.append(html.Div([
            html.I(className="bi bi-clock-fill me-2 text-muted"),
            html.Span("營業/開放時間：", className="fw-bold"),
            html.Div([html.Small(line, className="d-block text-muted ms-4") for line in time_lines])
        ], className="mb-2"))

    # 共通：費用資訊
    fee = row.get('FeeInfo') or row.get('TicketInfo')
    if fee and pd.notna(fee):
        specs.append(html.Div([
            html.I(className="bi bi-currency-dollar me-2 text-danger"),
            html.Span(f"費用說明：{fee}")
        ], className="mb-2"))

    # --- 3. 建立地圖組件 ---
    map_component = html.Div([
        html.I(className="bi bi-geo-alt me-2"), "暫無座標資訊"
    ], className="text-muted p-4 text-center border rounded")
    
    if pd.notna(lat) and pd.notna(lon):
        try:
            map_component = dl.Map(center=[float(lat), float(lon)], zoom=15, children=[
                dl.TileLayer(),
                dl.Marker(position=[float(lat), float(lon)], children=dl.Tooltip(name))
            ], style={'width': '100%', 'height': '300px', 'borderRadius': '12px', 'boxShadow': '0 4px 12px rgba(0,0,0,0.1)'})
        except: pass

    # --- 4. 組合最終佈局 ---
    return html.Div([
        # 頂部大圖
        html.Div(style={
            'backgroundImage': f'url({img_url})',
            'backgroundSize': 'cover',
            'backgroundPosition': 'center',
            'height': '350px',
            'borderRadius': '12px',
            'boxShadow': 'inset 0 -60px 100px rgba(0,0,0,0.5)',
            'position': 'relative',
            'marginBottom': '24px'
        }, children=[
            html.Span(category, className=f"badge bg-{cat_color} position-absolute", 
                    style={'top': '20px', 'left': '20px', 'padding': '8px 16px', 'fontSize': '1rem'})
        ]),
        
        # 標題與基本標籤
        html.H2(name, className="fw-bold mb-3", style={'color': '#2c3e50'}),
        
        # 核心資訊卡
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H6("📍 聯絡與地點", className="fw-bold border-bottom pb-2 mb-3"),
                        html.P([html.I(className="bi bi-geo-alt-fill text-danger me-2"), full_address], className="small mb-2"),
                        html.P([html.I(className="bi bi-telephone-fill text-primary me-2"), tel], className="small mb-3"),
                        dbc.ButtonGroup([
                            dbc.Button([html.I(className="bi bi-google me-2"), "Google 地圖"], 
                                      href=f"https://www.google.com/maps/search/?api=1&query={name}+{full_address}", 
                                      target="_blank", color="outline-success", size="sm"),
                            dbc.Button([html.I(className="bi bi-globe me-2"), "官方網站"], 
                                      href=website if website else "#", disabled=not website,
                                      target="_blank", color="outline-primary", size="sm"),
                        ], className="w-100")
                    ])
                ], className="border-0 shadow-sm h-100")
            ], width=12, lg=5),
            
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H6("ℹ️ 詳細資訊", className="fw-bold border-bottom pb-2 mb-3"),
                        html.Div(specs if specs else "暫無更多規格資訊", className="small")
                    ])
                ], className="border-0 shadow-sm h-100")
            ], width=12, lg=7),
        ], className="g-3 mb-4"),

        # 介紹文字
        html.Div([
            html.H5("💬 關於這裡", className="fw-bold mb-3 mt-4"),
            html.P(desc, style={
                'lineHeight': '1.8', 
                'color': '#444', 
                'whiteSpace': 'pre-wrap',
                'backgroundColor': '#f9f9f9',
                'padding': '20px',
                'borderRadius': '8px'
            }),
        ]),

        # 地圖區
        html.Div([
            html.H5("🗺️ 地理位置", className="fw-bold mb-3 mt-4"),
            map_component
        ], className="mb-5")
    ], className="p-2")

def calculate_distance(lat1, lon1, lat2, lon2):
    """
    計算兩點經緯度的距離 (單位: 公里)
    """
    import math
    R = 6371  # 地球半徑 (km)
    
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) * math.sin(dlat / 2) + \
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
        math.sin(dlon / 2) * math.sin(dlon / 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c
    return distance

def register_callbacks(app):
    """
    將所有的 @app.callback 邏輯放在這裡
    """
    
    @app.callback(
        Output('page-content', 'children'),
        [Input('url', 'pathname')]
    )
    def render_page_content(pathname):
        # 1. 處理根目錄導向 (如果網址是 /dashboard/ 或 /dashboard，預設顯示 overview)
        if pathname in ["/dashboard/", "/dashboard"]:
            pathname = "/dashboard/overview"

        # ====== 頁面 1: Overview (數據總覽) ======
        if pathname == "/dashboard/overview":
            return html.Div([
                # 四格統計 (原本在 Layout，因為現在 Layout 變了，移進來這裡顯示)
                # 第一排：地理與景點資訊
                dbc.Row([
                    dbc.Col(generate_stats_card("縣市總數", num_of_city, "assets/earth.svg"), width=4),
                    dbc.Col(generate_stats_card("鄉鎮總數", num_of_town, "assets/village.png"), width=4),
                    dbc.Col(generate_stats_card("景點總數", nums_of_name, "assets/landmark.png"), width=4),
                ], style={'marginBottom': '5px'}), # 增加列與列之間的間距
                
                # 第二排：活動、住宿與餐廳
                dbc.Row([
                    dbc.Col(generate_stats_card("活動總數", nums_of_event_name, "assets/calendar.svg"), width=4),
                    dbc.Col(generate_stats_card("住宿總數", nums_of_hotel_name, "assets/bed.png"), width=4),
                    dbc.Col(generate_stats_card("餐廳總數", nums_of_restaurant_name, "assets/dinner.png"), width=4),
                ], style={'marginBottom': '5px'}),

                # 第一排：長條 + 圓餅
                dbc.Row([
                    dbc.Col([
                        html.H3("各縣市/鄉鎮每個月份活動數", style={'color': THEME['primary'], 'marginTop': '5px', 'fontWeight': 'bold'}),
                        dcc.Dropdown(
                            id='dropdown-bar-1',
                            options=[{'label': i, 'value': i}for i in pd.concat([event_df['PostalAddress.City'], event_df['PostalAddress.Town']]).dropna().unique()],
                            value=DEFAULTS['bar1_geo'],
                            placeholder='Select a City/Town',
                            style={'width': '90%', 'marginTop': '10px', 'marginBottom': '10px', 'color': THEME['text']}
                        )
                    ]),
                    dbc.Col([
                        html.H3("各縣市/鄉鎮的活動種類分佈", style={'color': THEME['primary'], 'marginTop': '5px', 'fontWeight': 'bold'}),
                        dcc.Dropdown(
                            id='dropdown-pie-1',
                            options=[{'label': i, 'value': i}for i in pd.concat([event_df['PostalAddress.City'], event_df['PostalAddress.Town']]).dropna().unique()],
                            value=DEFAULTS['pie1_geo'],
                            placeholder='Select a City/Town',
                            style={'width': '50%', 'margin': '5px 0', 'display': 'inline-block', 'color': THEME['text']}
                        ),
                        dcc.Dropdown(
                            id='dropdown-pie-2',
                            options=[{'label': '活動類別', 'value': 'EventCategoryNames'}],
                            value=DEFAULTS["pie2_field"],
                            placeholder='Select a value',
                            style={'width': '50%', 'margin': '5px 0', 'display': 'inline-block', 'color': THEME['text']}
                        )
                    ]),
                ]),
                dbc.Row([
                    dbc.Col([dcc.Loading([html.Div(id='tabs-content-1')], type='default', color=THEME['primary'])]),
                    dbc.Col([dcc.Loading([html.Div(id='tabs-content-2')], type='default', color=THEME['primary'])]),
                ]),

                # 第二排：地圖 + 箱型圖
                dbc.Row([
                    dbc.Col([
                        html.H3("景點地理分佈與分類", style={'color': THEME['primary'], 'marginTop': '5px', 'fontWeight': 'bold'}),
                        dcc.Dropdown(
                            id='dropdown-map-1',
                            options=[{'label': 'All', 'value': ""}] + 
                                    [{'label': str(i), 'value': str(i)} for i in pd.concat([attraction_df['PostalAddress.City'], attraction_df['PostalAddress.Town']]).dropna().unique().tolist()],
                            value=DEFAULTS_attraction["map1_geo"],
                            placeholder='Select a City/Town',
                            style={'width': '50%', 'margin': '5px 0', 'display': 'inline-block', 'color': THEME['text']}
                        ),
                        dcc.Dropdown(
                            id='dropdown-map-2',
                            options=[
                                {'label': '景點類別 (Category)', 'value': 'PrimaryCategory'}, 
                                {'label': '是否免費 (IsAccessibleForFree)', 'value': 'IsAccessibleForFree'},
                            ],
                            value=DEFAULTS_attraction["map2_metric"],
                            placeholder='Select a value',
                            style={'width': '50%', 'margin': '5px 0', 'display': 'inline-block', 'color': THEME['text']}
                        )
                    ]),
                    dbc.Col([
                        html.H3("旅館價格分佈與成本分析", style={'color': THEME['primary'], 'marginTop': '5px', 'fontWeight': 'bold'}),
                        dcc.Dropdown(
                            id='dropdown-box-1',
                            options=[{'label': i, 'value': i} for i in pd.concat([hotel_df['PostalAddress.City'], hotel_df['PostalAddress.Town']]).dropna().unique()],
                            value=DEFAULTS_hotel["box1_geo"],
                            placeholder='Select a City/Town',
                            style={'width': '50%', 'margin': '5px 0', 'display': 'inline-block', 'color': THEME['text']}
                        ),
                        dcc.Dropdown(
                            id='dropdown-box-2',
                            options=[
                                {'label': '旅館類別 (Class)', 'value': 'HotelClassName'},
                                {'label': '旅館星級 (Stars)', 'value': 'HotelStars'}, 
                            ],
                            value=DEFAULTS_hotel["box2_metric"],
                            placeholder='Select a value',
                            style={'width': '50%', 'margin': '5px 0', 'display': 'inline-block', 'color': THEME['text']}
                        )
                    ]),
                ]),
                dbc.Row([
                    dbc.Col([dcc.Loading([html.Div(id='tabs-content-3')], type='default', color=THEME['primary'])]),
                    dbc.Col([dcc.Loading([html.Div(id='tabs-content-4')], type='default', color=THEME['primary'])]),
                ]),

                # 第三排：餐廳數據
                dbc.Row([
                    dbc.Col([
                        html.H3("各縣市/鄉鎮的餐廳菜系分佈", style={'color': THEME['primary'], 'marginTop': '5px', 'fontWeight': 'bold'}),
                        dcc.Dropdown(
                            id='dropdown-pie-restaurant-geo',
                            options=[{'label': i, 'value': i} for i in pd.concat([restaurant_df['PostalAddress.City'], restaurant_df['PostalAddress.Town']]).dropna().unique()],
                            value=DEFAULTS_restaurant["pie_geo"],
                            placeholder='Select a City/Town',
                            style={'width': '50%', 'margin': '5px 0', 'display': 'inline-block', 'backgroundColor': 'white', 'color': THEME['text']}
                        ),
                        dcc.Dropdown(
                            id='dropdown-pie-restaurant-type',
                            options=[{'label': '食物類別 (Cuisine)', 'value': 'CuisineNames'}],
                            value='CuisineNames',
                            placeholder='Select Category',
                            style={'width': '50%', 'margin': '5px 0', 'display': 'inline-block', 'backgroundColor': 'white', 'color': THEME['text']}
                        ),
                    ], width=6),
                ]),
                dbc.Row([
                    dbc.Col([dcc.Loading([html.Div(id='tabs-content-5')], type='default', color=THEME['primary'])], width=6),
                    dbc.Col([html.Div(id='tabs-content-6')], width=6),
                ]),
            ])

        # ====== 頁面 2: Trip Planner (行程規劃) ======
        elif pathname == "/dashboard/planner":
            # 準備下拉選單的選項
            accommodation_types = sorted(hotel_df['HotelClassName'].dropna().unique().tolist())
            attraction_categories = sorted(attraction_df['PrimaryCategory'].dropna().unique().tolist())
            event_categories = get_exploded_categories(event_df, 'EventCategoryNames', separator=',')
            restaurant_cities = sorted(restaurant_df['PostalAddress.City'].dropna().unique().tolist())
            cuisine_names = get_exploded_categories(restaurant_df, 'CuisineNames', separator=',')
            initial_month = datetime.now().strftime('%Y-%m-%d')

            return html.Div([
                # 1. 頂部 Tabs 導航
                dbc.Tabs([
                    dbc.Tab(label="🎡 找景點", tab_id="tab-attraction", label_style={"fontWeight": "bold"}),
                    dbc.Tab(label="📅 找活動", tab_id="tab-event", label_style={"fontWeight": "bold"}),
                    dbc.Tab(label="🛏️ 找住宿", tab_id="tab-hotel", label_style={"fontWeight": "bold"}),
                    dbc.Tab(label="🍽️ 找餐廳", tab_id="tab-restaurant", label_style={"fontWeight": "bold"}),
                ], id="planner-tabs", active_tab="tab-attraction", style={"marginBottom": "20px"}),

                # 2. 橫向篩選列 (Horizontal Filter Bar)
                dbc.Card([
                    dbc.CardBody([
                        # --- 景點篩選器 (Attraction) ---
                        html.Div(id='filter-attraction', children=[
                            dbc.Row([
                                # Col 1: 預算
                                dbc.Col([
                                    html.Label("預算偏好", className="fw-bold text-muted small"),
                                    dcc.Checklist(
                                        id='planner-att-free',
                                        options=[{'label': ' 僅看免費', 'value': 'FREE'}],
                                        value=[],
                                        labelStyle={'display': 'inline-block', 'cursor': 'pointer'},
                                        inputStyle={'marginRight': '5px'}
                                    )
                                ], width=12, md=2, className="d-flex align-items-center"),

                                # Col 2: 主題
                                dbc.Col([
                                    html.Label("景點主題", className="fw-bold text-muted small"),
                                    dcc.Dropdown(
                                        id='planner-att-categories',
                                        options=[{'label': t, 'value': t} for t in attraction_categories],
                                        value=[], multi=True, placeholder="選擇主題..."
                                    )
                                ], width=12, md=6),

                                # Col 3: 服務
                                dbc.Col([
                                    html.Label("周邊服務", className="fw-bold text-muted small"),
                                    dcc.Dropdown(
                                        id='planner-att-traffic',
                                        options=[{'label': '有停車場', 'value': 'PARKING_EXIST'}, {'label': '有交通資訊', 'value': 'TRAFFIC_EXIST'}],
                                        value=[], multi=True, placeholder="選擇服務..."
                                    )
                                ], width=12, md=4),
                            ], align="end")
                        ]),

                        # --- 活動篩選器 (Event) ---
                        html.Div(id='filter-event', style={'display': 'none'}, children=[
                            dbc.Row([
                                dbc.Col([
                                    html.Label("活動日期", className="fw-bold text-muted small"),
                                    dcc.DatePickerRange(
                                        id='planner-event-date-range',
                                        min_date_allowed=event_df['StartDateTime'].min(),
                                        max_date_allowed=event_df['EndDateTime'].max(),
                                        initial_visible_month=initial_month,
                                        style={'width': '100%'}
                                    )
                                ], width=12, md=5),
                                dbc.Col([
                                    html.Label("活動主題", className="fw-bold text-muted small"),
                                    dcc.Dropdown(id='planner-event-categories', options=[{'label': c, 'value': c} for c in event_categories], value=[], multi=True, placeholder="選擇主題...")
                                ], width=12, md=7),
                            ], align="center")
                        ]),

                        # --- 住宿篩選器 (Hotel) ---
                        html.Div(id='filter-hotel', style={'display': 'none'}, children=[
                            dbc.Row([
                                dbc.Col([
                                    html.Label("每晚預算 (TWD)", className="fw-bold text-muted small"),
                                    dbc.InputGroup([
                                        dbc.Input(id='planner-cost-min', type='number', placeholder='Min'),
                                        dbc.InputGroupText("-"),
                                        dbc.Input(id='planner-cost-max', type='number', placeholder='Max'),
                                    ])
                                ], width=12, md=4),
                                dbc.Col([
                                    html.Label("住宿類型", className="fw-bold text-muted small"),
                                    dcc.Dropdown(id='planner-acc-types', options=[{'label': t, 'value': t} for t in accommodation_types], value=[], multi=True, placeholder="選擇類型...")
                                ], width=12, md=8),
                            ], align="end")
                        ]),

                        # --- 餐廳篩選器 (Restaurant) ---
                        html.Div(id='filter-restaurant', style={'display': 'none'}, children=[
                            dbc.Row([
                                dbc.Col([
                                    html.Label("選擇縣市", className="fw-bold text-muted small"),
                                    dcc.Dropdown(id='planner-restaurant-city', options=[{'label': c, 'value': c} for c in restaurant_cities], placeholder='全臺')
                                ], width=12, md=3),
                                dbc.Col([
                                    html.Label("菜系風格", className="fw-bold text-muted small"),
                                    dcc.Dropdown(id='planner-restaurant-cuisine', options=[{'label': c, 'value': c} for c in cuisine_names], value=[], multi=True, placeholder="選擇菜系...")
                                ], width=12, md=9),
                            ], align="end")
                        ]),

                    ])
                ], className="mb-4 shadow-sm", style={"border": "none", "borderRadius": "12px", "backgroundColor": "#fff"}), 

                # 3. 下方結果與分頁區
                dcc.Loading(type="default", color="#FFA97F", children=[
                    # A. 卡片顯示區
                    html.Div(id='result-attraction'),
                    html.Div(id='result-event', style={'display': 'none'}),
                    html.Div(id='result-hotel', style={'display': 'none'}),
                    html.Div(id='result-restaurant', style={'display': 'none'}),
                    
                    # B. 分頁控制區 (這裡放 4 個分頁元件)
                    
                    # 1. 景點分頁
                    html.Div(id='pagination-attraction-container', children=[
                        dbc.Button("◀", id="btn-prev-att", outline=True, color="primary", size="sm", className="me-2"),
                        html.Span("第", className="me-1"),
                        dcc.Input(id="input-page-att", type="number", min=1, value=1, step=1, debounce=True, style={'width': '60px', 'textAlign': 'center', 'border': '1px solid #ddd', 'borderRadius': '5px'}),
                        html.Span(id="label-total-att", children=" / 1 頁", className="ms-1 me-2"),
                        dbc.Button("▶", id="btn-next-att", outline=True, color="primary", size="sm"),
                    ]),
                    
                    # 2. 活動分頁
                    html.Div(id='pagination-event-container', style={'display': 'none'}, children=[
                        dbc.Button("◀", id="btn-prev-event", outline=True, color="primary", size="sm", className="me-2"),
                        html.Span("第", className="me-1"),
                        dcc.Input(id="input-page-event", type="number", min=1, value=1, step=1, debounce=True, style={'width': '60px', 'textAlign': 'center', 'border': '1px solid #ddd', 'borderRadius': '5px'}),
                        html.Span(id="label-total-event", children=" / 1 頁", className="ms-1 me-2"),
                        dbc.Button("▶", id="btn-next-event", outline=True, color="primary", size="sm"),
                    ]),
                    
                    # 3. 住宿分頁
                    html.Div(id='pagination-hotel-container', style={'display': 'none'}, children=[
                        dbc.Button("◀", id="btn-prev-hotel", outline=True, color="primary", size="sm", className="me-2"),
                        html.Span("第", className="me-1"),
                        dcc.Input(id="input-page-hotel", type="number", min=1, value=1, step=1, debounce=True, style={'width': '60px', 'textAlign': 'center', 'border': '1px solid #ddd', 'borderRadius': '5px'}),
                        html.Span(id="label-total-hotel", children=" / 1 頁", className="ms-1 me-2"),
                        dbc.Button("▶", id="btn-next-hotel", outline=True, color="primary", size="sm"),
                    ]),
                    
                    # 4. 餐廳分頁
                    html.Div(id='pagination-restaurant-container', style={'display': 'none'}, children=[
                        dbc.Button("◀", id="btn-prev-restaurant", outline=True, color="primary", size="sm", className="me-2"),
                        html.Span("第", className="me-1"),
                        dcc.Input(id="input-page-restaurant", type="number", min=1, value=1, step=1, debounce=True, style={'width': '60px', 'textAlign': 'center', 'border': '1px solid #ddd', 'borderRadius': '5px'}),
                        html.Span(id="label-total-restaurant", children=" / 1 頁", className="ms-1 me-2"),
                        dbc.Button("▶", id="btn-next-restaurant", outline=True, color="primary", size="sm"),
                    ]),
                ]),

                dbc.Modal([
                    dbc.ModalHeader(dbc.ModalTitle(id="modal-detail-title"), close_button=True),
                    dbc.ModalBody(id="modal-detail-body"),
                    dbc.ModalFooter(
                        dbc.Button("關閉", id="btn-close-modal", className="ms-auto", n_clicks=0)
                    ),
                ], id="modal-detail", size="lg", is_open=False, scrollable=True, centered=True),
            ])
        # ====== 頁面 3: Attractions (地圖瀏覽) ======
        elif pathname == "/dashboard/attractions":
            city_list = sorted(attraction_df['PostalAddress.City'].dropna().unique().tolist())
            category_options = [
                {'label': '景點 (Attractions)', 'value': 'attractions'},
                {'label': '活動 (Events)', 'value': 'events'},
                {'label': '住宿 (Hotels)', 'value': 'hotels'},
                {'label': '餐廳 (Restaurants)', 'value': 'restaurants'},
            ]
            
            return html.Div([
                html.H3("全臺 POI 地圖與周邊搜尋", style={'color': THEME['primary'], 'marginTop': '5px', 'fontWeight': 'bold'}),
                
                dbc.Card([
                    dbc.CardBody([
                        # 第一排：搜尋模式選擇
                        dbc.Row([
                            dbc.Col([
                                html.Label("搜尋模式", className="fw-bold"),
                                dcc.RadioItems(
                                    id='map-search-mode',
                                    options=[
                                        {'label': ' 依照縣市瀏覽', 'value': 'city'},
                                        {'label': ' 搜尋特定地點 (周邊)', 'value': 'keyword'}
                                    ],
                                    value='city',
                                    inline=True,
                                    inputStyle={"marginRight": "5px", "marginLeft": "10px"}
                                )
                            ], width=12, className="mb-3")
                        ]),

                        # 第二排：控制項 (根據模式顯示/隱藏)
                        dbc.Row([
                            # 模式 A: 縣市選擇
                            dbc.Col([
                                html.Label("選擇縣市", className="fw-bold"),
                                dcc.Dropdown(
                                    id='poi-city-dropdown',
                                    options=[{'label': city, 'value': city} for city in city_list],
                                    value=city_list[0] if city_list else None,
                                    placeholder="請選擇縣市"
                                )
                            ], width=4, id='container-city-select'),

                            # 模式 B: 關鍵字搜尋 (預設隱藏)
                            dbc.Col([
                                html.Label("輸入景點/地標名稱", className="fw-bold"),
                                dbc.InputGroup([
                                    dbc.Input(id='poi-search-input', placeholder="例如：台北101、赤崁樓...", type="text"),
                                    dbc.Button("搜尋", id='btn-keyword-search', color="primary", n_clicks=0)
                                ])
                            ], width=6, id='container-keyword-search', style={'display': 'none'}),

                            # 模式 B: 半徑選擇 (預設隱藏)
                            dbc.Col([
                                html.Label("搜尋半徑 (公里)", className="fw-bold"),
                                dcc.Slider(
                                    id='poi-radius-slider',
                                    min=1, max=20, step=1, value=5,
                                    marks={1: '1km', 5: '5km', 10: '10km', 20: '20km'},
                                    tooltip={"placement": "bottom", "always_visible": True}
                                )
                            ], width=6, id='container-radius-select', style={'display': 'none'}),
                        ], className="mb-3"),

                        # 第三排：類別選擇
                        dbc.Row([
                            dbc.Col([
                                html.Label("顯示類別 (可多選)", className="fw-bold"),
                                dcc.Dropdown(
                                    id='poi-category-multi',
                                    options=category_options,
                                    value=['attractions', 'hotels', 'restaurants'], # 預設不選 event 以免太亂
                                    multi=True
                                )
                            ], width=12)
                        ])
                    ])
                ], className="mb-4 shadow-sm"),

                # 更新按鈕 (僅在縣市模式使用，關鍵字模式用旁邊的搜尋鈕)
                html.Div(
                    dbc.Button("更新縣市地圖", id='poi-submit-button', color="primary", className="fw-bold"),
                    id='container-submit-btn'
                ),

                # 結果訊息 (例如：找到座標...)
                html.Div(id='map-message-output', className="mt-2 text-info fw-bold"),

                # 地圖容器
                dcc.Loading(
                    id="poi-loading", type="default", color=THEME['primary'], 
                    children=[
                        dcc.Graph(id='poi-map-graph', style={'height': '600px', 'marginTop': '16px', 'borderRadius': '12px'})
                    ]
                )
            ])

    # --------------------------------------------------------------------------------
    # 這裡開始是你所有的 Callbacks 
    # --------------------------------------------------------------------------------

    # 1. 長條圖 (Bar Chart)
    @app.callback(Output('tabs-content-1', 'children'), [Input('dropdown-bar-1', 'value'), Input('url', 'pathname')])
    def update_bar_chart(dropdown_value, pathname):
        if pathname != '/dashboard/overview': return no_update
        df = event_df
        geo = dropdown_value or DEFAULTS["bar1_geo"]
        fig = generate_bar(df, geo)
        fig.update_layout(**GRAPH_STYLE, colorway=[THEME['primary'], THEME['secondary']])
        return html.Div([dcc.Graph(figure=fig)])

    # 2. 圓餅圖 (Pie Chart)
    @app.callback(Output('tabs-content-2', 'children'), [Input('dropdown-pie-1', 'value'), Input('dropdown-pie-2', 'value'), Input('url', 'pathname')])
    def update_pie_chart(val1, val2, pathname):
        if pathname != '/dashboard/overview': return no_update
        df = event_df
        geo = val1 or DEFAULTS["pie1_geo"]
        field = val2 or DEFAULTS["pie2_field"]
        fig = generate_pie(df, geo, field)
        fig.update_layout(**GRAPH_STYLE, colorway=[THEME['primary'], THEME['secondary'], THEME['accent']])
        return html.Div([dcc.Graph(figure=fig)])

    # 3. 景點地圖 (Map Chart)
    @app.callback(Output('tabs-content-3', 'children'), [Input('dropdown-map-1', 'value'), Input('dropdown-map-2', 'value'), Input('url', 'pathname')])
    def update_attraction_map(city, metric, pathname):
        if pathname != '/dashboard/overview': return no_update
        df_filtered = attraction_df.copy()
        if city: df_filtered = df_filtered[(df_filtered['PostalAddress.City'] == city) | (df_filtered['PostalAddress.Town'] == city)]
        if df_filtered.empty: return html.Div("無數據", style={'color': THEME['danger']})
        metric = metric or DEFAULTS_attraction["map2_metric"]
        fig = generate_map(df=df_filtered, city=city or '臺灣', color_by_column=metric)
        fig.update_layout(paper_bgcolor=THEME['background'], font={'color': THEME['text']}, margin={"r":0,"t":30,"l":0,"b":0})
        return html.Div([dcc.Graph(figure=fig)], style={'width': '100%'})

    # 4. 箱型圖 (Box Chart)
    @app.callback(Output('tabs-content-4', 'children'), [Input('dropdown-box-1', 'value'), Input('dropdown-box-2', 'value'), Input('url', 'pathname')])
    def update_box_chart(geo, metric, pathname):
        if pathname != '/dashboard/overview': return no_update
        df = hotel_df.copy()
        metric = metric or DEFAULTS_hotel["box2_metric"]
        if geo: df = df[(df['PostalAddress.City'] == geo) | (df['PostalAddress.Town'] == geo)]
        if df.empty: return html.Div("無數據", style={'color': THEME['danger']})
        fig = generate_box(df=df, geo=geo, metric=metric)
        fig.update_layout(**GRAPH_STYLE)
        return html.Div([dcc.Graph(figure=fig)])

    # 5. 餐廳旭日圖 (Sunburst)
    @app.callback(Output('tabs-content-5', 'children'), [Input('dropdown-pie-restaurant-geo', 'value'), Input('dropdown-pie-restaurant-type', 'value'), Input('url', 'pathname')])
    def render_restaurant_sunburst(geo, field, pathname):
        if pathname != '/dashboard/overview': raise PreventUpdate
        if not geo or not field: return html.Div("請選擇條件")
        
        # 簡易處理資料 (複製原本邏輯)
        df_filtered = restaurant_df[(restaurant_df['PostalAddress.City'] == geo) | (restaurant_df['PostalAddress.Town'] == geo)].copy()
        if df_filtered.empty: return html.Div("無數據")
        
        # 扁平化處理
        try:
            if df_filtered[field].dtype == object and df_filtered[field].str.contains(';').any():
                df_filtered[field] = df_filtered[field].str.split(';')
                df_filtered = df_filtered.explode(field)
                df_filtered[field] = df_filtered[field].str.strip()
        except: pass

        if geo in restaurant_df['PostalAddress.City'].unique(): paths = ['PostalAddress.City', field]
        else: 
            df_filtered['Geo'] = geo
            paths = ['Geo', field]
            
        fig = px.sunburst(df_filtered, path=paths, values=df_filtered.index, title=f'{geo} 餐廳分佈')
        fig.update_layout(**GRAPH_STYLE)
        return dcc.Graph(figure=fig)

    # 共用表格樣式
    TABLE_HEADER_STYLE = {'backgroundColor': THEME['primary'], 'color': 'white', 'fontWeight': 'bold', 'border': 'none'}
    TABLE_CELL_STYLE = {'backgroundColor': 'white', 'color': THEME['text'], 'borderBottom': f'1px solid {THEME["secondary"]}'}
    

    # --------------------------------------------------------
    # 控制 Tabs 切換時，顯示/隱藏對應的區域
    # --------------------------------------------------------
    @app.callback(
        [Output('filter-attraction', 'style'), Output('result-attraction', 'style'), Output('pagination-attraction-container', 'style'),
         Output('filter-event', 'style'), Output('result-event', 'style'), Output('pagination-event-container', 'style'),
         Output('filter-hotel', 'style'), Output('result-hotel', 'style'), Output('pagination-hotel-container', 'style'),
         Output('filter-restaurant', 'style'), Output('result-restaurant', 'style'), Output('pagination-restaurant-container', 'style')],
        [Input('planner-tabs', 'active_tab')]
    )
    def switch_planner_tabs(tab):
        # 1. 定義隱藏樣式
        hide_style = {'display': 'none'}
        
        # 2. 定義一般區塊 (Filter, Result) 的顯示樣式
        show_block = {'display': 'block'}
        
        # 3. ⭐️ 定義分頁區塊的顯示樣式 (把原本寫在 className 的 flex 搬來這裡)
        # 這樣就能確保「要顯示時才置中」，「要隱藏時就真的消失」
        show_flex = {
            'display': 'flex', 
            'justifyContent': 'center', 
            'alignItems': 'center', 
            'marginTop': '1.5rem'
        }
        
        # 邏輯：(Filter, Result, Pagination)
        
        if tab == 'tab-attraction':
            return (show_block, show_block, show_flex,   # 顯示 Attraction
                    hide_style, hide_style, hide_style,  # 隱藏 Event
                    hide_style, hide_style, hide_style,  # 隱藏 Hotel
                    hide_style, hide_style, hide_style)  # 隱藏 Restaurant

        elif tab == 'tab-event':
            return (hide_style, hide_style, hide_style, 
                    show_block, show_block, show_flex,   # 顯示 Event
                    hide_style, hide_style, hide_style, 
                    hide_style, hide_style, hide_style)

        elif tab == 'tab-hotel':
            return (hide_style, hide_style, hide_style, 
                    hide_style, hide_style, hide_style, 
                    show_block, show_block, show_flex,   # 顯示 Hotel
                    hide_style, hide_style, hide_style)

        elif tab == 'tab-restaurant':
            return (hide_style, hide_style, hide_style, 
                    hide_style, hide_style, hide_style, 
                    hide_style, hide_style, hide_style, 
                    show_block, show_block, show_flex)   # 顯示 Restaurant
        
        # 預設
        return (show_block, show_block, show_flex, hide_style, hide_style, hide_style, hide_style, hide_style, hide_style, hide_style, hide_style, hide_style)

    # Trip Planner: 景點更新邏輯
    @app.callback(
        [Output('result-attraction', 'children'), 
         Output('label-total-att', 'children'),
         Output('input-page-att', 'value')],
        [Input('planner-att-free', 'value'), 
         Input('planner-att-categories', 'value'), 
         Input('planner-att-traffic', 'value'),
         Input('btn-prev-att', 'n_clicks'),
         Input('btn-next-att', 'n_clicks'),
         Input('input-page-att', 'value')]
    )
    def update_attraction_cards(is_free, cats, servs, btn_prev, btn_next, page_input):
        # ... (前面篩選邏輯省略，請保留原樣) ...
        df = preprocess_attraction_df(attraction_df).copy()
        
        # (這裡省略中間的篩選程式碼...)
        is_free = sanitize_list_input(is_free)
        if 'FREE' in is_free: df = df[(df['IsAccessibleForFree'] == True) | (df['FeeInfo'].isna())]
        cats = sanitize_list_input(cats)
        if cats: df = df[df['PrimaryCategory'].isin(cats)]
        servs = sanitize_list_input(servs)
        if servs:
            cond = pd.Series(True, index=df.index)
            if 'PARKING_EXIST' in servs: cond &= (df['ParkingInfo'].notna() & df['ParkingInfo'].astype(str).str.strip().ne(''))
            if 'TRAFFIC_EXIST' in servs: cond &= (df['TrafficInfo'].notna() & df['TrafficInfo'].astype(str).str.strip().ne(''))
            df = df[cond]

        # 分頁邏輯
        per_page = 15
        total_items = len(df)
        total_pages = math.ceil(total_items / per_page) or 1
        
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
        current_page = page_input or 1
        if trigger_id == 'btn-prev-att': current_page = max(1, current_page - 1)
        elif trigger_id == 'btn-next-att': current_page = min(total_pages, current_page + 1)
        elif trigger_id == 'input-page-att': current_page = max(1, min(total_pages, current_page))
        else: current_page = 1

        if df.empty: return html.Div("無符合資料", style={'textAlign': 'center', 'marginTop': '50px', 'color': '#888'}), " / 1 頁", 1

        start_idx = (current_page - 1) * per_page
        end_idx = current_page * per_page
        df_page = df.iloc[start_idx:end_idx]

        # ⭐️ 關鍵修改：撈取收藏 ID 並傳入 generate_trip_card
        user_favs = set()
        if current_user.is_authenticated:
            # 取得所有已收藏的 ID
            user_favs = {fav.item_id for fav in Favorite.query.filter_by(user_id=current_user.id).all()}

        # 傳入 user_favs
        cards = [generate_trip_card(row, "景點", user_favs) for _, row in df_page.iterrows()]
        
        return html.Div(cards, className="planner-grid"), f" / {total_pages} 頁", current_page
    
    # Trip Planner: 活動更新邏輯
    @app.callback(
        [Output('result-event', 'children'), 
         Output('label-total-event', 'children'),
         Output('input-page-event', 'value')],
        [Input('planner-event-date-range', 'start_date'), 
         Input('planner-event-date-range', 'end_date'), 
         Input('planner-event-categories', 'value'),
         Input('btn-prev-event', 'n_clicks'),
         Input('btn-next-event', 'n_clicks'),
         Input('input-page-event', 'value')]
    )
    def update_event_cards(start, end, cats, btn_prev, btn_next, page_input):
        # ... (前面邏輯省略，請保留原樣) ...
        df = preprocess_event_df(event_df).copy()
        cats = sanitize_list_input(cats)
        if cats: 
            pat = '|'.join(map(re.escape, cats))
            try: df = df[df['EventCategoryNames'].astype(str).str.contains(pat, na=False)]
            except: pass
        
        per_page = 15
        total_items = len(df)
        total_pages = math.ceil(total_items / per_page)
        if total_pages == 0: total_pages = 1
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
        current_page = page_input or 1
        if trigger_id == 'btn-prev-event': current_page = max(1, current_page - 1)
        elif trigger_id == 'btn-next-event': current_page = min(total_pages, current_page + 1)
        elif trigger_id == 'input-page-event': current_page = max(1, min(total_pages, current_page))
        else: current_page = 1

        if df.empty: return html.Div("無符合資料", style={'textAlign': 'center', 'marginTop': '50px', 'color': '#888'}), " / 1 頁", 1

        start_idx = (current_page - 1) * per_page
        end_idx = current_page * per_page
        df_page = df.iloc[start_idx:end_idx]
        
        # ⭐️ 新增：撈取收藏
        user_favs = set()
        if current_user.is_authenticated:
            user_favs = {fav.item_id for fav in Favorite.query.filter_by(user_id=current_user.id).all()}

        cards = [generate_trip_card(row, "活動", user_favs) for _, row in df_page.iterrows()]
        return html.Div(cards, className="planner-grid"), f" / {total_pages} 頁", current_page

    # Trip Planner: 住宿更新邏輯
    @app.callback(
        [Output('result-hotel', 'children'),
         Output('label-total-hotel', 'children'),
         Output('input-page-hotel', 'value')],
        [Input('planner-cost-min', 'value'), 
         Input('planner-cost-max', 'value'), 
         Input('planner-acc-types', 'value'),
         Input('btn-prev-hotel', 'n_clicks'),
         Input('btn-next-hotel', 'n_clicks'),
         Input('input-page-hotel', 'value')]
    )
    def update_hotel_cards(min_p, max_p, types, btn_prev, btn_next, page_input):
        # ... (前面邏輯省略) ...
        df = preprocess_hotel_df(hotel_df).copy()
        min_p, max_p = sanitize_cost_bounds(min_p, max_p)
        df = filter_by_cost_and_types(df, min_p, max_p, types)
        
        per_page = 15
        total_items = len(df)
        total_pages = math.ceil(total_items / per_page)
        if total_pages == 0: total_pages = 1
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
        current_page = page_input or 1
        if trigger_id == 'btn-prev-hotel': current_page = max(1, current_page - 1)
        elif trigger_id == 'btn-next-hotel': current_page = min(total_pages, current_page + 1)
        elif trigger_id == 'input-page-hotel': current_page = max(1, min(total_pages, current_page))
        else: current_page = 1
            
        if df.empty: return html.Div("無符合資料", style={'textAlign': 'center', 'marginTop': '50px', 'color': '#888'}), " / 1 頁", 1

        start_idx = (current_page - 1) * per_page
        end_idx = current_page * per_page
        df_page = df.iloc[start_idx:end_idx]
        
        # ⭐️ 新增：撈取收藏
        user_favs = set()
        if current_user.is_authenticated:
            user_favs = {fav.item_id for fav in Favorite.query.filter_by(user_id=current_user.id).all()}

        cards = [generate_trip_card(row, "住宿", user_favs) for _, row in df_page.iterrows()]
        return html.Div(cards, className="planner-grid"), f" / {total_pages} 頁", current_page

    # Trip Planner: 餐廳更新邏輯
    @app.callback(
        [Output('result-restaurant', 'children'),
         Output('label-total-restaurant', 'children'),
         Output('input-page-restaurant', 'value')],
        [Input('planner-restaurant-city', 'value'), 
         Input('planner-restaurant-cuisine', 'value'),
         Input('btn-prev-restaurant', 'n_clicks'),
         Input('btn-next-restaurant', 'n_clicks'),
         Input('input-page-restaurant', 'value')]
    )
    def update_restaurant_cards(city, cuisines, btn_prev, btn_next, page_input):
        # ... (前面邏輯省略) ...
        df = restaurant_df.copy()
        city_col = 'PostalAddress.City' if 'PostalAddress.City' in df.columns else 'City'
        if city and city_col in df.columns: df = df[df[city_col] == city]
        cuisines = sanitize_list_input(cuisines)
        if cuisines and 'CuisineNames' in df.columns:
            pat = '|'.join(map(re.escape, cuisines))
            try: df = df[df['CuisineNames'].astype(str).str.contains(pat, na=False)]
            except: pass
            
        per_page = 15
        total_items = len(df)
        total_pages = math.ceil(total_items / per_page)
        if total_pages == 0: total_pages = 1
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
        current_page = page_input or 1
        if trigger_id == 'btn-prev-restaurant': current_page = max(1, current_page - 1)
        elif trigger_id == 'btn-next-restaurant': current_page = min(total_pages, current_page + 1)
        elif trigger_id == 'input-page-restaurant': current_page = max(1, min(total_pages, current_page))
        else: current_page = 1
            
        if df.empty: return html.Div("無符合資料", style={'textAlign': 'center', 'marginTop': '50px', 'color': '#888'}), " / 1 頁", 1

        start_idx = (current_page - 1) * per_page
        end_idx = current_page * per_page
        df_page = df.iloc[start_idx:end_idx]
        
        # ⭐️ 新增：撈取收藏
        user_favs = set()
        if current_user.is_authenticated:
            user_favs = {fav.item_id for fav in Favorite.query.filter_by(user_id=current_user.id).all()}

        cards = [generate_trip_card(row, "餐廳", user_favs) for _, row in df_page.iterrows()]
        return html.Div(cards, className="planner-grid"), f" / {total_pages} 頁", current_page

    # 處理「加入/取消收藏」的邏輯 (最穩定版)
    @app.callback(
        Output({'type': 'btn-add-favorite', 'index': ALL, 'category': ALL}, 'style'),
        Input({'type': 'btn-add-favorite', 'index': ALL, 'category': ALL}, 'n_clicks'),
        prevent_initial_call=True
    )
    def toggle_favorite(n_clicks_list):
        # 1. 基本檢查
        if not current_user.is_authenticated:
            return [no_update] * len(ctx.outputs_list)

        trigger = ctx.triggered_id
        # 如果沒有 trigger (雖然理論上 prevent_initial_call 會擋掉，但保險起見)
        if not trigger:
            return [no_update] * len(ctx.outputs_list)

        # ⭐️ 2. 判斷是否為有效點擊
        # 我們不檢查 n_clicks 的值了，只要是由 btn-add-favorite 觸發的，就視為點擊
        # 這樣可以避免 n_clicks 初始化為 0 或 None 的問題
        if 'btn-add-favorite' not in str(trigger):
             return [no_update] * len(ctx.outputs_list)

        print(f"DEBUG: 觸發收藏按鈕! ID={trigger['index']}")

        # 3. 執行資料庫邏輯
        item_id = trigger['index']
        category = trigger['category']
        
        try:
            existing_fav = Favorite.query.filter_by(user_id=current_user.id, item_id=item_id).first()
            
            if existing_fav:
                db.session.delete(existing_fav)
                db.session.commit()
                print(f"DEBUG: 已刪除 {item_id}")
            else:
                row_data = None
                # (這裡省略撈資料代碼，請保留你原本的...)
                if category == "景點":
                    filtered = attraction_df[attraction_df['AttractionID'].astype(str) == item_id]
                    if not filtered.empty: row_data = filtered.iloc[0]
                elif category == "活動":
                    filtered = event_df[event_df['EventID'].astype(str) == item_id]
                    if not filtered.empty: row_data = filtered.iloc[0]
                elif category == "住宿":
                    filtered = hotel_df[hotel_df['HotelID'].astype(str) == item_id]
                    if not filtered.empty: row_data = filtered.iloc[0]
                elif category == "餐廳":
                    filtered = restaurant_df[restaurant_df['RestaurantID'].astype(str) == item_id]
                    if not filtered.empty: row_data = filtered.iloc[0]

                if row_data is not None:
                    name = row_data.get('AttractionName') or row_data.get('EventName') or row_data.get('HotelName') or row_data.get('RestaurantName')
                    img = row_data.get('ThumbnailURL') or row_data.get('Picture.PictureUrl1') or row_data.get('PictureUrl1') or "https://placehold.co/600x400/eee/999?text=No+Image"
                    city = row_data.get('PostalAddress.City') or row_data.get('City') or ""
                    
                    new_fav = Favorite(user_id=current_user.id, item_id=item_id, category=category, name=name, image_url=img, location=city)
                    db.session.add(new_fav)
                    db.session.commit()
                    print(f"DEBUG: 已新增 {name}")
                    
        except Exception as e:
            print(f"DEBUG: 資料庫錯誤: {e}")
            db.session.rollback()
            return [no_update] * len(ctx.outputs_list)

        # ⭐️ 4. 回傳樣式 (一次性查詢所有收藏，確保狀態同步)
        # 為了避免狀態不一致，我們重新撈一次使用者的所有收藏 ID
        current_fav_ids = {fav.item_id for fav in Favorite.query.filter_by(user_id=current_user.id).all()}
        
        results = []
        for output_spec in ctx.outputs_list:
            btn_id = output_spec['id']['index']
            if btn_id in current_fav_ids:
                results.append({'color': '#dc3545'}) # 紅色
            else:
                results.append({'color': 'white'})   # 白色
        
        return results

    # 控制詳情 Modal 開關與內容
    @app.callback(
        [Output("modal-detail", "is_open"),
         Output("modal-detail-title", "children"),
         Output("modal-detail-body", "children")],
        [Input({'type': 'btn-view-detail', 'index': ALL, 'category': ALL}, 'n_clicks'),
         Input("btn-close-modal", "n_clicks")],
        [State("modal-detail", "is_open")]
    )
    def toggle_detail_modal(n_clicks_detail, n_clicks_close, is_open):
        # 取得觸發 Callback 的來源
        trigger = ctx.triggered_id
        
        # 1. 如果沒觸發，或按了關閉 -> 關閉視窗
        if not trigger or (isinstance(trigger, str) and trigger == "btn-close-modal"):
            return False, "", ""

        # 2. 如果是點擊了「查看詳情」按鈕
        # trigger 會是一個字典: {'type': 'btn-view-detail', 'index': 'xxx', 'category': 'xxx'}
        if isinstance(trigger, dict) and trigger['type'] == 'btn-view-detail':
            # 檢查是否有任何按鈕被點擊 (n_clicks > 0)
            # 因為 ALL 屬性會回傳列表，我們要確認是否真的有有效點擊
            if not any(n for n in n_clicks_detail if n):
                return is_open, no_update, no_update

            target_id = trigger['index']
            category = trigger['category']
            
            # 根據類別去搜尋對應的 DataFrame
            row_data = None
            
            # 注意：這裡的 id 必須與 generate_trip_card 裡面的 raw_id 對應
            # 建議在讀檔時確保 AttractionID 等欄位都轉為字串以防萬一
            if category == "景點":
                # 嘗試找 ID
                filtered = attraction_df[attraction_df['AttractionID'].astype(str) == target_id]
                if not filtered.empty: row_data = filtered.iloc[0]
                
            elif category == "活動":
                filtered = event_df[event_df['EventID'].astype(str) == target_id]
                if not filtered.empty: row_data = filtered.iloc[0]
                
            elif category == "住宿":
                filtered = hotel_df[hotel_df['HotelID'].astype(str) == target_id]
                if not filtered.empty: row_data = filtered.iloc[0]
                
            elif category == "餐廳":
                filtered = restaurant_df[restaurant_df['RestaurantID'].astype(str) == target_id]
                if not filtered.empty: row_data = filtered.iloc[0]

            if row_data is not None:
                # 呼叫 helper 函數生成內容
                content = create_detail_content(row_data, category)
                title = row_data.get('AttractionName') or row_data.get('EventName') or row_data.get('HotelName') or row_data.get('RestaurantName')
                return True, title, content
            else:
                return True, "錯誤", "找不到該筆資料"

        return is_open, no_update, no_update

    # POI地圖
    # 1. 切換搜尋模式 (控制 UI 顯示)
    @app.callback(
        [Output('container-city-select', 'style'),
         Output('container-submit-btn', 'style'),
         Output('container-keyword-search', 'style'),
         Output('container-radius-select', 'style')],
        [Input('map-search-mode', 'value')]
    )
    def toggle_search_mode(mode):
        if mode == 'city':
            # 顯示縣市選單，隱藏關鍵字搜尋
            return {'display': 'block'}, {'display': 'block'}, {'display': 'none'}, {'display': 'none'}
        else:
            # 顯示關鍵字搜尋，隱藏縣市選單
            return {'display': 'none'}, {'display': 'none'}, {'display': 'block'}, {'display': 'block'}

    # 2. 核心地圖更新邏輯
    @app.callback(
        [Output('poi-map-graph', 'figure'),
         Output('map-message-output', 'children')],
        [Input('poi-submit-button', 'n_clicks'),
         Input('btn-keyword-search', 'n_clicks')],
        [State('map-search-mode', 'value'),
         State('poi-city-dropdown', 'value'),
         State('poi-search-input', 'value'),
         State('poi-radius-slider', 'value'),
         State('poi-category-multi', 'value')]
    )
    def update_enhanced_map(btn_city, btn_key, mode, city, keyword, radius, cats):
        ctx_id = ctx.triggered_id
        
        # 預設空地圖
        empty_fig = px.scatter_mapbox(lat=[23.5], lon=[121], zoom=6)
        empty_fig.update_layout(mapbox_style="carto-positron", margin={"r":0,"t":0,"l":0,"b":0})
        
        if not cats:
            return empty_fig, "請選擇至少一種 POI 類別"

        # 準備所有資料 (加上 Type 標籤)
        df_list = []
        if 'attractions' in cats: df_list.append(attraction_df.assign(Type='景點', Name=attraction_df['AttractionName']))
        if 'hotels' in cats: df_list.append(hotel_df.assign(Type='住宿', Name=hotel_df['HotelName']))
        if 'restaurants' in cats: df_list.append(restaurant_df.assign(Type='餐廳', Name=restaurant_df['RestaurantName']))
        if 'events' in cats: df_list.append(event_df.assign(Type='活動', Name=event_df['EventName']))
        
        if not df_list: return empty_fig, "無資料"
        
        full_df = pd.concat(df_list, ignore_index=True)
        # 確保經緯度是數字且去除空值
        full_df['Lat'] = pd.to_numeric(full_df['Lat'], errors='coerce')
        full_df['Lon'] = pd.to_numeric(full_df['Lon'], errors='coerce')
        full_df = full_df.dropna(subset=['Lat', 'Lon'])

        final_df = pd.DataFrame()
        center_lat, center_lon = 23.6, 120.9 # 預設台灣中心
        zoom_level = 7
        message = ""

        # --- 模式 A: 縣市瀏覽 ---
        if mode == 'city':
            if not city: return empty_fig, "請先選擇縣市"
            final_df = full_df[full_df['PostalAddress.City'] == city]
            message = f"顯示 {city} 的 {len(final_df)} 筆資料"
            if not final_df.empty:
                center_lat = final_df['Lat'].mean()
                center_lon = final_df['Lon'].mean()
                zoom_level = 10

        # --- 模式 B: 關鍵字周邊搜尋 ---
        elif mode == 'keyword':
            if not keyword: return empty_fig, "請輸入關鍵字"
            
            # 1. 先在資料庫裡找這個地點 (完全匹配或包含)
            # 優先搜尋景點
            target = attraction_df[attraction_df['AttractionName'].str.contains(keyword, case=False, na=False)]
            
            # 如果景點沒找到，找餐廳或飯店
            if target.empty:
                target = restaurant_df[restaurant_df['RestaurantName'].str.contains(keyword, case=False, na=False)]
            if target.empty:
                target = hotel_df[hotel_df['HotelName'].str.contains(keyword, case=False, na=False)]
                
            if target.empty:
                return empty_fig, f"找不到「{keyword}」，請嘗試輸入更精確的名稱。"
            
            # 取得目標點座標 (取第一筆符合的)
            target_row = target.iloc[0]
            center_lat = float(target_row['Lat'])
            center_lon = float(target_row['Lon'])
            target_name = target_row.get('AttractionName') or target_row.get('RestaurantName') or target_row.get('HotelName')
            
            # 2. 計算距離並篩選
            # 使用 apply 計算每個點到中心的距離
            # 注意：這裡資料量大時可能會慢，建議先用簡單的經緯度範圍(box)過濾一次再精算
            
            # 粗略過濾 (加速)：1度緯度約 111km，半徑 20km 大約是 0.2 度
            lat_range = radius / 110 
            lon_range = radius / 100 # 概抓
            
            rough_filter = full_df[
                (full_df['Lat'].between(center_lat - lat_range, center_lat + lat_range)) &
                (full_df['Lon'].between(center_lon - lon_range, center_lon + lon_range))
            ].copy()
            
            if rough_filter.empty:
                return empty_fig, "範圍內無資料"

            # 精確計算距離
            rough_filter['Distance'] = rough_filter.apply(
                lambda x: calculate_distance(center_lat, center_lon, x['Lat'], x['Lon']), axis=1
            )
            
            final_df = rough_filter[rough_filter['Distance'] <= radius]
            
            # 加上中心點本身 (標記為搜尋目標)
            # 我們可以手動加一筆資料代表「中心點」，用不同顏色表示
            center_point = pd.DataFrame([{
                'Name': f"📍 {target_name} (搜尋中心)", 
                'Lat': center_lat, 
                'Lon': center_lon, 
                'Type': '搜尋目標',
                'Distance': 0
            }])
            
            final_df = pd.concat([center_point, final_df], ignore_index=True)
            
            zoom_level = 13 if radius <= 5 else 11
            message = f"已定位「{target_name}」，並顯示周邊 {radius} 公里內的 {len(final_df)-1} 筆 POI。"

        # --- 繪圖 ---
        if final_df.empty: return empty_fig, "無符合資料"

        fig = px.scatter_mapbox(
            final_df, 
            lat="Lat", 
            lon="Lon", 
            color="Type", # 顏色區分
            hover_name="Name",
            zoom=zoom_level,
            center={"lat": center_lat, "lon": center_lon},
            color_discrete_map={
                "搜尋目標": "red",     # 紅色大圖釘
                "景點": "#2ecc71",    # 綠色
                "餐廳": "#e67e22",    # 橘色
                "住宿": "#9b59b6",    # 紫色
                "活動": "#3498db"     # 藍色
            },
            size=[14 if t == '搜尋目標' else 7 for t in final_df['Type']], 
            size_max=14 # 最大尺寸限制也跟著調整
        )
        
        fig.update_layout(
            mapbox_style="carto-positron",
            margin={"r":0,"t":0,"l":0,"b":0},
            legend_title_text='類別'
        )
        
        return fig, message

##########################
#### 4: 工廠模式 ####
##########################
def create_app():
    server = Flask(__name__)

    server.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:12345678@localhost:5432/slowdays_db'
    server.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    server.config['SECRET_KEY'] = 'my_secret_key_123'

    db.init_app(server)

    login_manager.init_app(server)
    login_manager.login_view = 'auth.login'
    
    with server.app_context():
        from .routes import auth_bp, member_bp
        server.register_blueprint(auth_bp)
        server.register_blueprint(member_bp)

        db.create_all()

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @server.route('/')
    def index():
        return redirect('/dashboard/')

    dash_app = Dash(
        __name__,
        server=server,
        url_base_pathname='/dashboard/',
        assets_folder='assets',   
        external_stylesheets=[dbc.themes.BOOTSTRAP],
        title='SlowDays', 
        suppress_callback_exceptions=True
    )

    # --- 動態生成 Sidebar (根據 Config) ---
    nav_components = []
    for item in SIDEBAR_ITEMS:
        if item["type"] == "header":
            # ... (標題部分保持不變) ...
            if item.get("margin_top"):
                nav_components.append(html.Div(item["label"], className="sidebar-sub-header"))
            else:
                nav_components.append(html.Div(item["label"], className="sidebar-header"))
                nav_components.append(html.Hr(style={'margin': '0 0 10px 0'}))
                
        elif item["type"] == "link":
            # 連結區塊
            nav_components.append(
                dbc.NavLink(
                    [html.Span(item["icon"], style={'marginRight':'8px'}), item["label"]],
                    href=item["href"],
                    active="exact",
                    className="nav-link",
                    external_link=True 
                )
            )

    # 組合 Sidebar
    sidebar = html.Div(
        [dbc.Nav(nav_components, vertical=True, pills=True)],
        className="custom-sidebar" # ⭐️ 對應 shared_style.css
    )

    # --- Serve Layout ---
    def serve_layout():
        # 登入按鈕邏輯 (保持不變)
        if current_user.is_authenticated:
            auth_component = html.Div([
                html.Span(f"Hi, {current_user.username}", style={'color': '#FFA97F', 'fontWeight': 'bold', 'marginRight': '15px'}),
                html.A("登出", href="/logout", className="btn-slow-primary") 
            ], style={'display': 'flex', 'alignItems': 'center'})
        else:
            auth_component = html.Div([
                html.A("登入", href="/login", className="btn-slow-outline")
            ])

        return html.Div([
            dcc.Location(id="url", refresh=False),

            # Header
            html.Div([
                # 左側：按鈕 + Logo
                html.Div([
                    # ⭐️ 新增：縮放按鈕
                    html.Button("☰", id="sidebar-toggle", className="toggle-btn"), 
                    html.Div("SlowDays Dashboard", className="header-logo"),
                ], className="header-left"), # 記得加這個 class (CSS有定義)
                
                # 右側：登入資訊
                auth_component
            ], className="custom-header"),

            # Sidebar
            sidebar,

            # Content
            html.Div(id="page-content", className="custom-content")

        ])

    dash_app.layout = serve_layout

    register_callbacks(dash_app)
    return server