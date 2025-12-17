import os
import json
import re
from datetime import datetime

# Flask 與 Dash 核心
from flask import Flask, redirect
from dash import Dash, html, dcc, Input, State, Output, dash_table, no_update
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import dash_leaflet as dl
import plotly.express as px
import pandas as pd
import numpy as np
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from .utils.theme import THEME, TAB_STYLE, SIDEBAR_STYLE, CONTENT_STYLE, GRAPH_STYLE

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
            accommodation_types = sorted(hotel_df['HotelClassName'].dropna().unique().tolist())
            attraction_categories = sorted(attraction_df['PrimaryCategory'].dropna().unique().tolist())
            event_categories = get_exploded_categories(event_df, 'EventCategoryNames', separator=',')
            restaurant_cities = sorted(restaurant_df['PostalAddress.City'].dropna().unique().tolist())
            cuisine_names = get_exploded_categories(restaurant_df, 'CuisineNames', separator=',')
            initial_month = datetime.now().strftime('%Y-%m-%d')
            
            return html.Div([
                # 這裡要保留 Store，不然切換頁面後 filter 會失效
                dcc.Store(id='planner-selected-countries', data=[]),

                html.H3("Trip Planner：", style={'color': THEME['primary'], 'marginTop': '5px', 'fontWeight': 'bold'}),
                
                # --- 景點 ---
                html.H3("用預算與偏好找景點 (Attraction)", style={'color': THEME['primary'], 'marginTop': '20px', 'fontWeight': 'bold'}),
                dbc.Row([
                     dbc.Col([
                        html.Label("預算（免費）", style={'color': THEME['text'], 'fontWeight': 'bold'}),
                        dcc.Checklist(
                            id='planner-att-free',
                            options=[{'label': '  僅看免費景點', 'value': 'FREE'}],
                            value=[], inline=True, 
                            style={'color': THEME['text']} # 改成深灰字
                        )
                    ], width=3),
                    dbc.Col([
                        html.Label("景點主題（multi）", style={'color': THEME['text'], 'fontWeight': 'bold'}),
                        dcc.Dropdown(id='planner-att-categories', options=[{'label': t, 'value': t} for t in attraction_categories], value=[], multi=True, style={'backgroundColor': 'white', 'color': THEME['text']})
                    ], width=6),
                    dbc.Col([
                        html.Label("周邊服務（multi）", style={'color': THEME['text'], 'fontWeight': 'bold'}),
                        dcc.Dropdown(id='planner-att-traffic', options=[{'label': '有停車場', 'value': 'PARKING_EXIST'}, {'label': '有交通資訊', 'value': 'TRAFFIC_EXIST'}], value=[], multi=True, style={'backgroundColor': 'white', 'color': THEME['text']})
                    ], width=3),
                ]),
                html.H4("景點推薦結果", style={'color': THEME['primary'], 'marginTop': '15px'}),
                dcc.Loading([html.Div(id='planner-attraction-container')], type='default', color=THEME['primary']),
                html.Hr(style={'borderColor': THEME['primary']}),
                
                # --- 活動 ---
                html.H3("用時間與主題找活動 (Event)", style={'color': THEME['primary'], 'fontWeight': 'bold'}),
                dbc.Row([
                    dbc.Col([
                        dcc.DatePickerRange(id='planner-event-date-range', min_date_allowed=event_df['StartDateTime'].min(), max_date_allowed=event_df['EndDateTime'].max(), initial_visible_month=initial_month, style={'width': '100%'})
                    ], width=7),
                    dbc.Col([
                        dcc.Dropdown(id='planner-event-categories', options=[{'label': c, 'value': c} for c in event_categories], value=[], multi=True, style={'backgroundColor': 'white', 'color': THEME['text']})
                    ], width=5)
                ]),
                dcc.Loading([html.Div(id='planner-event-container')], type='default', color=THEME['primary']),
                html.Hr(style={'borderColor': THEME['primary']}),
                
                # --- 住宿 ---
                html.H3("用預算與偏好找住宿 (Hotel)", style={'color': THEME['primary'], 'fontWeight': 'bold'}),
                dbc.Row([
                    dbc.Col([dcc.Input(id='planner-cost-min', type='number', placeholder='min (TWD)', style={'width':'100%', 'borderRadius': '5px', 'border': '1px solid #ccc', 'padding': '5px'})], width=3),
                    dbc.Col([dcc.Input(id='planner-cost-max', type='number', placeholder='max (TWD)', style={'width':'100%', 'borderRadius': '5px', 'border': '1px solid #ccc', 'padding': '5px'})], width=3),
                    dbc.Col([dcc.Dropdown(id='planner-acc-types', options=[{'label': t, 'value': t} for t in accommodation_types], value=[], multi=True, style={'backgroundColor': 'white', 'color': THEME['text']})], width=6),
                ]),
                dcc.Loading([html.Div(id='planner-table-container')], type='default', color=THEME['primary']),
                html.Hr(style={'borderColor': THEME['primary']}),
                
                # --- 餐廳 ---
                html.H3("用位置與菜系找餐廳 (Restaurant)", style={'color': THEME['primary'], 'fontWeight': 'bold'}),
                dbc.Row([
                    dbc.Col([dcc.Dropdown(id='planner-restaurant-city', options=[{'label': c, 'value': c} for c in restaurant_cities], value=None, placeholder='Select City...', style={'backgroundColor': 'white', 'color': THEME['text']})], width=4),
                    dbc.Col([dcc.Dropdown(id='planner-restaurant-cuisine', options=[{'label': c, 'value': c} for c in cuisine_names], value=[], multi=True, style={'backgroundColor': 'white', 'color': THEME['text']})], width=8),
                ]),
                dcc.Loading([html.Div(id='planner-restaurant-container')], type='default', color=THEME['primary']),
                html.Hr(style={'borderColor': THEME['primary']}),
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
                html.H3("單縣市POI地圖瀏覽", style={'color': THEME['primary'], 'marginTop': '5px', 'fontWeight': 'bold'}),
                dbc.Row([
                    dbc.Col([
                        html.Label("選擇縣市", style={'color': THEME['text'], 'fontWeight': 'bold'}),
                        dcc.Dropdown(options=[{'label': city, 'value': city} for city in city_list], value=city_list[0] if city_list else None, id='poi-city-dropdown', style={'backgroundColor': 'white', 'color': THEME['text']}),
                    ], width=6),
                    dbc.Col([
                        html.Label("選擇要顯示的 POI 類別", style={'color': THEME['text'], 'fontWeight': 'bold'}),
                        dcc.Dropdown(options=category_options, value=['attractions', 'hotels', 'restaurants', 'events'], id='poi-category-multi', multi=True, style={'backgroundColor': 'white', 'color': THEME['text']}),
                    ], width=6),
                ]),
                html.Button("更新地圖", id='poi-submit-button', n_clicks=0, className="btn", 
                            style={'backgroundColor': THEME['primary'], 'color': 'white', 'fontWeight': 'bold', 'marginTop': '10px', 'padding': '8px 16px', 'borderRadius': '8px', 'border': 'none', 'cursor': 'pointer'}),
                dcc.Loading(id="poi-loading", type="circle", color=THEME['primary'], children=[html.Div(id='poi-map-container', style={'height': '600px', 'marginTop': '16px', 'borderRadius': '12px', 'overflow': 'hidden'})])
            ])
        
        # 404 處理
        return html.Div([
            html.H1("404: Not found", className="text-danger"),
            html.Hr(),
            html.P(f"無法找到頁面: {pathname}"),
            html.A("回到總覽", href="/dashboard/overview", className="btn btn-primary")
        ], className="p-3")

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
    

    # Trip Planner: 景點更新邏輯
    @app.callback(Output('planner-attraction-container', 'children'), 
                 [Input('planner-att-free', 'value'), Input('planner-att-categories', 'value'), Input('planner-att-traffic', 'value'), Input('url', 'pathname')])
    def update_planner_attraction(is_free, cats, servs, pathname):
        if pathname != '/dashboard/planner': raise PreventUpdate
        df = preprocess_attraction_df(attraction_df).copy()
        
        # 篩選邏輯
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
            
        if df.empty: return html.Div("無符合資料", style={'color': THEME['danger']})
        
        shown_cols = {'PostalAddress.City':'縣市', 'AttractionName':'名稱', 'PrimaryCategory':'分類', 'ServiceTimesSummary':'時間'}
        df_display = df[list(shown_cols.keys())].rename(columns=shown_cols).head(50)
        
        return dash_table.DataTable(
            columns=[{"name": i, "id": i} for i in df_display.columns],
            data=df_display.to_dict('records'),
            page_size=10,
            style_header=TABLE_HEADER_STYLE, style_data=TABLE_CELL_STYLE
        )

    # Trip Planner: 活動更新邏輯
    @app.callback(Output('planner-event-container', 'children'), 
                 [Input('planner-event-date-range', 'start_date'), Input('planner-event-date-range', 'end_date'), Input('planner-event-categories', 'value'), Input('url', 'pathname')])
    def update_planner_event(start, end, cats, pathname):
        if pathname != '/dashboard/planner': raise PreventUpdate
        df = preprocess_event_df(event_df).copy()
        
        # 簡單篩選 (完整邏輯請參考前幾輪回答)
        cats = sanitize_list_input(cats)
        if cats: 
            pat = '|'.join(map(re.escape, cats))
            try: df = df[df['EventCategoryNames'].astype(str).str.contains(pat, na=False)]
            except: pass
            
        if df.empty: return html.Div("無符合資料", style={'color': THEME['danger']})
        
        shown_cols = {'PostalAddress.City':'縣市', 'EventName':'名稱', 'EventCategoryNames':'主題', 'StartDateTime':'開始', 'EndDateTime':'結束'}
        df_display = df[list(shown_cols.keys())].rename(columns=shown_cols).head(50)
        return dash_table.DataTable(
            columns=[{"name": i, "id": i} for i in df_display.columns],
            data=df_display.to_dict('records'),
            page_size=10,
            style_header=TABLE_HEADER_STYLE, style_data=TABLE_CELL_STYLE
        )

    # Trip Planner: 住宿更新邏輯
    @app.callback([Output('planner-table-container', 'children'), Output('planner-selected-countries', 'data')],
                 [Input('planner-cost-min', 'value'), Input('planner-cost-max', 'value'), Input('planner-acc-types', 'value'), Input('url', 'pathname')])
    def update_planner_hotel(min_p, max_p, types, pathname):
        if pathname != '/dashboard/planner': return no_update, no_update
        df = preprocess_hotel_df(hotel_df).copy()
        min_p, max_p = sanitize_cost_bounds(min_p, max_p)
        df = filter_by_cost_and_types(df, min_p, max_p, types)
        
        if df.empty: return html.Div("無符合資料", style={'color': THEME['danger']}), []
        
        shown_cols = {'PostalAddress.City':'縣市', 'HotelName':'名稱', 'HotelClassName':'類型', 'LowestPrice':'最低價', 'HotelStars':'星級'}
        df_display = df[[c for c in shown_cols.keys() if c in df.columns]].rename(columns=shown_cols).head(50)
        
        table = dash_table.DataTable(
            columns=[{"name": i, "id": i} for i in df_display.columns],
            data=df_display.to_dict('records'),
            page_size=10,
            style_header=TABLE_HEADER_STYLE, style_data=TABLE_CELL_STYLE
        )
        return table, []

    # Trip Planner: 餐廳更新邏輯
    @app.callback(Output('planner-restaurant-container', 'children'),
                  [Input('planner-restaurant-city', 'value'), Input('planner-restaurant-cuisine', 'value'), Input('url', 'pathname')])
    def update_planner_restaurant(city, cuisines, pathname):
        if pathname != '/dashboard/planner': raise PreventUpdate
        if restaurant_df.empty: return html.Div("資料載入錯誤")
        
        df = restaurant_df.copy() # 使用原始資料
        city_col = 'PostalAddress.City' if 'PostalAddress.City' in df.columns else 'City'
        
        if city and city_col in df.columns: df = df[df[city_col] == city]
        
        cuisines = sanitize_list_input(cuisines)
        if cuisines and 'CuisineNames' in df.columns:
            pat = '|'.join(map(re.escape, cuisines))
            try: df = df[df['CuisineNames'].astype(str).str.contains(pat, na=False)]
            except: pass
            
        if df.empty: return html.Div("無符合資料", style={'color': THEME['danger']})
        
        col_map = {'餐廳名稱': 'RestaurantName', '縣市': city_col, '菜系': 'CuisineNames', '狀態': 'ServiceStatus'}
        display = pd.DataFrame()
        for d_name, db_col in col_map.items():
            if db_col in df.columns: display[d_name] = df[db_col]
            
        return dash_table.DataTable(
            columns=[{"name": i, "id": i} for i in display.columns],
            data=display.head(50).to_dict('records'),
            page_size=10,
            style_header=TABLE_HEADER_STYLE, style_data=TABLE_CELL_STYLE
        )

    # POI 地圖
    @app.callback(
        Output('poi-map-container', 'children'), 
        [Input('poi-submit-button', 'n_clicks')], 
        [State('poi-city-dropdown', 'value'), State('poi-category-multi', 'value')], 
        prevent_initial_call=True
    )
    def update_poi_map(n, city, cats):
        if not city or not cats: raise PreventUpdate
        all_pois = []
        # 合併邏輯 (簡化版，請用你完整的)
        LAT, LON = 'Lat', 'Lon'
        if 'attractions' in cats and LAT in attraction_df: all_pois.append(attraction_df[attraction_df['PostalAddress.City']==city].assign(Type='景點', Name=attraction_df['AttractionName']))
        if 'hotels' in cats and LAT in hotel_df: all_pois.append(hotel_df[hotel_df['PostalAddress.City']==city].assign(Type='住宿', Name=hotel_df['HotelName']))
        if 'restaurants' in cats and LAT in restaurant_df: all_pois.append(restaurant_df[restaurant_df['PostalAddress.City']==city].assign(Type='餐廳', Name=restaurant_df['RestaurantName']))
        if 'events' in cats and LAT in event_df: all_pois.append(event_df[event_df['PostalAddress.City']==city].assign(Type='活動', Name=event_df['EventName']))

        if not all_pois: return html.Div("無數據")
        
        df_all = pd.concat(all_pois, ignore_index=True).dropna(subset=[LAT, LON])
        if df_all.empty: return html.Div("無座標數據")

        fig = px.scatter_mapbox(df_all, lat=LAT, lon=LON, color='Type', hover_name='Name', zoom=10)
        fig.update_layout(
            mapbox_style="carto-positron", 
            margin={"r":0,"t":0,"l":0,"b":0},
            paper_bgcolor=THEME['background'],
            font={'color': THEME['text']}
        )
        return dcc.Graph(figure=fig, style={'height': '100%'})

##########################
#### 4: 工廠模式 ####
##########################
def create_app():
    server = Flask(__name__)
    
    with server.app_context():
        from .routes import auth_bp, member_bp
        server.register_blueprint(auth_bp)
        server.register_blueprint(member_bp)

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

    # --- 定義側邊欄組件 ---
    sidebar = html.Div(
        [
            html.H5("Dashboard", className="display-6", style={'fontSize': '18px', 'color': THEME['muted'], 'marginBottom': '20px'}),
            html.Hr(),
            
            # 導航連結
            dbc.Nav(
                [
                    # href 對應到網址路徑，active="exact" 會自動判斷是否為當前頁面並變色
                    dbc.NavLink([html.Span("📊 ", style={'marginRight':'8px'}), "數據總覽"], href="/dashboard/overview", active="exact"),
                    dbc.NavLink([html.Span("🗺️ ", style={'marginRight':'8px'}), "行程查詢"], href="/dashboard/planner", active="exact"),
                    dbc.NavLink([html.Span("🎡 ", style={'marginRight':'8px'}), "景點地圖"], href="/dashboard/attractions", active="exact"),
                ],
                vertical=True,
                pills=True, # 膠囊樣式
                style={'fontSize': '16px'} # 字體大小
            ),
            
            html.Hr(style={'margin': '20px 0'}),
            
            # --- 未來擴充區塊 (模擬登入後的功能) ---
            html.H5("會員專區", style={'fontSize': '16px', 'color': THEME['primary'], 'fontWeight': 'bold', 'marginTop': '20px'}),
            dbc.Nav(
                [
                    dbc.NavLink([html.Span("👤 ", style={'marginRight':'8px'}), "個人偏好設定"], href="/member/preferences",external_link=True),
                    dbc.NavLink([html.Span("❤️ ", style={'marginRight':'8px'}), "我的收藏行程"], href="/member/favorites",external_link=True),
                    dbc.NavLink([html.Span("📅 ", style={'marginRight':'8px'}), "行程排程管理"], href="/member/schedule",external_link=True),
                ],
                vertical=True,
                pills=True,
            ),
        ],
        style=SIDEBAR_STYLE,
    )

    # --- 設定整體 Layout ---
    dash_app.layout = html.Div([
        # 1. 網址監聽器 (這是路由的核心)
        dcc.Location(id="url", refresh=False),

        # 2. 頂部 Header
        html.Div([
            # 左側：文字 Logo
            html.Div("SlowDays Dashboard", style={
                'fontSize': '24px', 
                'fontWeight': 'bold', 
                'color': THEME['primary'], 
                'letterSpacing': '1px'
            }),
            
            # ⭐️ 右側：修改為「登入」按鈕
            html.Div([
                html.A("登入", href="/login", style={
                    'textDecoration': 'none', 
                    'color': THEME['primary'],              # 文字顏色：暖橘
                    'border': f'1.5px solid {THEME["primary"]}', # 邊框：暖橘
                    'padding': '8px 20px',                  # 內距：稍微加寬一點比較好按
                    'borderRadius': '8px',                  # 圓角
                    'fontWeight': '600',                    # 字體加粗
                    'backgroundColor': 'white',             # 背景：白
                    'transition': '0.2s',
                    'display': 'inline-block',
                    'cursor': 'pointer'
                })
            ])
        ], style={
            'display': 'flex', 
            'justifyContent': 'space-between', 
            'alignItems': 'center',
            'padding': '16px 24px', 
            'backgroundColor': THEME['secondary'], 
            'boxShadow': '0 2px 8px rgba(0,0,0,0.05)', 
            'position': 'fixed', 
            'top': 0, 
            'left': 0, 
            'right': 0, 
            'zIndex': 100, 
            'height': '70px'
        }),

        # 3. 側邊欄
        sidebar,

        # 4. 主要內容區 (Content)
        html.Div(id="page-content", style=CONTENT_STYLE)

    ], style={'backgroundColor': THEME['background'], 'minHeight': '100vh', 'fontFamily': '"Noto Sans TC", sans-serif'})

    register_callbacks(dash_app)
    return server