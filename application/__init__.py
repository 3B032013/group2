import os
import json
import re
from datetime import datetime
import math

#以圖搜圖
from PIL import Image
import base64
from io import BytesIO
from .utils.image_search import search_similar_images

# Flask 與 Dash 核心
from flask import Flask, redirect
from .extensions import db, login_manager
from flask_login import current_user
from dash import Dash, html, dcc, Input, State, Output, dash_table, no_update, ctx, ALL, set_props
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import dash_leaflet as dl
import plotly.express as px
import pandas as pd
import numpy as np

# 你的專案模組
from .utils.theme import THEME, TAB_STYLE, SIDEBAR_STYLE, CONTENT_STYLE, GRAPH_STYLE
from .nav_config import SIDEBAR_ITEMS
from .models import User, Favorite, CartItem, Itinerary, ItineraryDetail
from .utils.const import get_constants, get_constants_event, get_constants_hotel, get_constants_restaurant
from .utils.data_clean import load_and_merge_attractions_data, load_and_clean_event_data, load_and_clean_hotel_data, load_and_merge_restaurant_data
from .utils.data_transform import (
    get_dashboard_default_values,
    get_dashboard_default_attraction_values,
    get_dashboard_default_hotel_values,
    get_dashboard_default_restaurant_values,
    get_exploded_categories,
    sanitize_list_input,
    sanitize_cost_bounds,
    preprocess_attraction_df,
    preprocess_event_df,
    preprocess_hotel_df,
)
from .utils.visualization import generate_stats_card, generate_bar, generate_pie, generate_map, generate_box


# ==========================================
# 1. 資料載入 (Global Scope)
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

def get_data_path(filename):
    return os.path.join(DATA_DIR, filename)

print(f"Loading data from: {DATA_DIR}")

attraction_df = load_and_merge_attractions_data(
    attraction_path=get_data_path('AttractionList.json'),
    fee_path=get_data_path('AttractionFeeList.json'),
    service_time_path=get_data_path('AttractionServiceTimeList.json')
)
event_df = load_and_clean_event_data(get_data_path('EventList.json'))
hotel_df = load_and_clean_hotel_data(get_data_path('HotelList.json'))
restaurant_df = load_and_merge_restaurant_data(
    restaurant_path=get_data_path('RestaurantList.json'),
    service_time_path=get_data_path('RestaurantServiceTimeList.json')
)

# 統計常數
num_of_city, num_of_town, nums_of_name = get_constants(attraction_df)
nums_of_event_name = get_constants_event(event_df)
nums_of_hotel_name = get_constants_hotel(hotel_df)
nums_of_restaurant_name = get_constants_restaurant(restaurant_df)

# 預設值
DEFAULTS = get_dashboard_default_values(event_df)
DEFAULTS_attraction = get_dashboard_default_attraction_values(attraction_df)
DEFAULTS_hotel = get_dashboard_default_hotel_values(hotel_df)
DEFAULTS_restaurant = get_dashboard_default_restaurant_values(restaurant_df)


# ==========================================
# 2. 輔助函式 (Helper Functions)
# ==========================================
def generate_trip_card(row, type_tag, user_favs=None):
    if user_favs is None: user_favs = set()
    
    # 圖片處理
    img_url = row.get('ThumbnailURL') or row.get('Picture.PictureUrl1') or row.get('PictureUrl1')
    if not img_url or pd.isna(img_url): img_url = "https://placehold.co/600x400/f5f5f5/999?text=No+Image"

    name = row.get('AttractionName') or row.get('EventName') or row.get('HotelName') or row.get('RestaurantName') or '未命名'
    city = row.get('PostalAddress.City') or row.get('City') or ''
    
    # ID 處理
    raw_id = row.get('AttractionID') or row.get('HotelID') or row.get('RestaurantID') or row.get('EventID')
    item_id = str(raw_id) if (raw_id is not None and pd.notna(raw_id)) else f"idx-{row.name}"
    
    initial_color = '#dc3545' if item_id in user_favs else 'white'

    return html.Div(
        className="trip-card",
        children=[
            html.Div([
                html.Img(src=img_url, className="trip-card-img"),
                dbc.Button(
                    html.Span("❤", style={'fontSize': '24px', 'color': 'inherit'}),
                    id={'type': 'btn-add-favorite', 'index': item_id, 'category': type_tag},
                    className="btn-favorite-overlay",
                    style={'color': initial_color},
                    n_clicks=0
                )
            ], className="trip-card-img-container"),
            html.Div(className="trip-card-body", children=[
                html.Div([
                    html.Span(city, className="trip-location"),
                    html.Span(" • ", style={'margin': '0 5px', 'color': '#ccc'}),
                    html.Span(type_tag, style={'color': '#888'})
                ], className="trip-tag-line"),
                html.Div(name, className="trip-card-title", title=name),
                html.Div([
                    dbc.Button("詳情 >", id={'type': 'btn-view-detail', 'index': item_id, 'category': type_tag}, color="link", className="p-0 text-decoration-none fw-bold"),
                    dbc.Button([html.I(className="bi bi-cart-plus me-1"), "加入行程"], id={'type': 'btn-add-cart', 'index': item_id, 'category': type_tag}, color="success", size="sm", className="rounded-pill px-3 shadow-sm", style={'fontSize': '0.8rem'})
                ], className="d-flex justify-content-between align-items-center mt-3")
            ])
        ]
    )

def create_detail_content(row, category):
    name = row.get('AttractionName') or row.get('EventName') or row.get('HotelName') or row.get('RestaurantName') or "未命名"
    desc = row.get('Description') or row.get('DescriptionSummary') or "暫無詳細介紹"
    
    # 地址清理
    city = str(row.get('PostalAddress.City', '')).replace('nan', '')
    town = str(row.get('PostalAddress.Town', '')).replace('nan', '')
    street = str(row.get('PostalAddress.StreetAddress', '')).replace('nan', '')
    full_address = f"{city}{town}{street}"
    if not full_address: full_address = row.get('Address') or row.get('Location') or "暫無地址資訊"

    tel = row.get('Telephones.Tel') or row.get('Phone') or row.get('MainTelephone') or '無電話資訊'
    website = row.get('WebsiteUrl') or row.get('Url')
    
    img_url = row.get('ThumbnailURL') or row.get('Picture.PictureUrl1') or row.get('PictureUrl1')
    if not img_url or pd.isna(img_url): img_url = "https://placehold.co/800x400/f5f5f5/999?text=No+Image"

    lat = row.get('Lat') or row.get('PositionLat')
    lon = row.get('Lon') or row.get('PositionLon')

    # 動態資訊塊
    specs = []
    cat_colors = {"景點": "info", "活動": "primary", "住宿": "warning", "餐廳": "success"}
    cat_color = cat_colors.get(category, "secondary")

    if category == "活動":
        start = str(row.get('StartDateTime', '')).split('T')[0]
        end = str(row.get('EndDateTime', '')).split('T')[0]
        specs.append(html.Div([html.I(className="bi bi-calendar-event-fill me-2 text-primary"), html.Span(f"活動期間：{start} 至 {end}", className="fw-bold")], className="mb-2"))
    elif category == "住宿":
        grade = row.get('HotelStars')
        if grade and pd.notna(grade): specs.append(html.Div([html.I(className="bi bi-star-fill me-2 text-warning"), html.Span(f"評等：{grade} 星級飯店", className="fw-bold")], className="mb-2"))
    elif category == "餐廳":
        cuisine = row.get('CuisineNames')
        if cuisine: specs.append(html.Div([html.I(className="bi bi-egg-fried me-2 text-success"), html.Span(f"料理種類：{cuisine}", className="fw-bold")], className="mb-2"))

    map_component = html.Div([html.I(className="bi bi-geo-alt me-2"), "暫無座標資訊"], className="text-muted p-4 text-center border rounded")
    if pd.notna(lat) and pd.notna(lon):
        try:
            map_component = dl.Map(center=[float(lat), float(lon)], zoom=15, children=[
                dl.TileLayer(), dl.Marker(position=[float(lat), float(lon)], children=dl.Tooltip(name))
            ], style={'width': '100%', 'height': '300px', 'borderRadius': '12px'})
        except: pass

    return html.Div([
        html.Div(style={'backgroundImage': f'url({img_url})', 'backgroundSize': 'cover', 'backgroundPosition': 'center', 'height': '350px', 'borderRadius': '12px', 'position': 'relative', 'marginBottom': '24px'}, children=[
            html.Span(category, className=f"badge bg-{cat_color} position-absolute", style={'top': '20px', 'left': '20px', 'padding': '8px 16px'})
        ]),
        html.H2(name, className="fw-bold mb-3", style={'color': '#2c3e50'}),
        dbc.Row([
            dbc.Col([dbc.Card([dbc.CardBody([
                html.H6("📍 聯絡與地點", className="fw-bold border-bottom pb-2 mb-3"),
                html.P([html.I(className="bi bi-geo-alt-fill text-danger me-2"), full_address], className="small mb-2"),
                html.P([html.I(className="bi bi-telephone-fill text-primary me-2"), tel], className="small mb-3"),
                dbc.ButtonGroup([
                    dbc.Button([html.I(className="bi bi-google me-2"), "Google 地圖"], href=f"https://www.google.com/maps/search/?api=1&query={name}+{full_address}", target="_blank", color="outline-success", size="sm"),
                    dbc.Button([html.I(className="bi bi-globe me-2"), "官方網站"], href=website if website else "#", disabled=not website, target="_blank", color="outline-primary", size="sm"),
                ], className="w-100")
            ])], className="border-0 shadow-sm h-100")], width=12, lg=5),
            dbc.Col([dbc.Card([dbc.CardBody([
                html.H6("ℹ️ 詳細資訊", className="fw-bold border-bottom pb-2 mb-3"),
                html.Div(specs if specs else "暫無更多規格資訊", className="small")
            ])], className="border-0 shadow-sm h-100")], width=12, lg=7),
        ], className="g-3 mb-4"),
        html.Div([html.H5("💬 關於這裡", className="fw-bold mb-3 mt-4"), html.P(desc, style={'lineHeight': '1.8', 'color': '#444', 'whiteSpace': 'pre-wrap', 'backgroundColor': '#f9f9f9', 'padding': '20px', 'borderRadius': '8px'})]),
        html.Div([html.H5("🗺️ 地理位置", className="fw-bold mb-3 mt-4"), map_component], className="mb-5")
    ], className="p-2")

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# ==========================================
# new. 首頁 UI 生成函式
# ==========================================
def generate_home_page():
    return html.Div([
        # --- 1. 標題區 ---
        html.Div([
            html.H1("探索 SlowDays", className="text-center mb-2 animate-fade-up", 
                    style={"color": "#FFA97F", "fontWeight": "bold", "fontSize": "3.2rem"}),
            html.P("整合全台旅遊數據，規劃您的專屬節奏", className="text-center text-muted animate-fade-up", 
                   style={"animationDelay": "0.1s"}),
        ], style={"padding": "40px 0 30px"}),

        # --- 2. 第一層：行程規劃 (左) 與 數據統計 (右) ---
        dbc.Row([
            # 左側：開始規劃行程 (加入 animate-fade-up)
            dbc.Col(
                html.A([
                    html.Div([
                        html.Div([
                            html.H2("開始規劃行程", className="fw-bold mb-2", style={"color": "#2c3e50"}),
                            html.P("隨心所欲，為收藏的風景排好專屬節奏", style={"color": "#5d6d7e", "margin": "0"})
                        ], style={
                            "backgroundColor": "rgba(255, 255, 255, 0.75)", 
                            "padding": "30px 40px", "borderRadius": "20px",
                            "backdropFilter": "blur(8px)", "textAlign": "center"
                        })
                    ], style={
                        "backgroundImage": "url('https://images.unsplash.com/photo-1488190211105-8b0e65b80b4e?auto=format&fit=crop&w=800&q=80')",
                        "backgroundSize": "cover", "backgroundPosition": "center",
                        "height": "100%", "display": "flex", "alignItems": "center",
                        "justifyContent": "center", "borderRadius": "25px", "minHeight": "ˇ200px"
                    })
                ], href="/dashboard/planner", className="quick-link-card animate-fade-up", 
                   style={"textDecoration": "none", "display": "block", "height": "100%", "animationDelay": "0.2s"}),
                width=12, lg=7, className="equal-height-col" # 調整比例為 6:6 或 7:5
            ),
            
            # 右側：三個數據統計方框 (活動、景點、餐廳)
            dbc.Col(
                html.Div([
                    html.Div(generate_stats_card("目前活動總數", nums_of_event_name, "assets/calendar.svg"), 
                             className="animate-fade-up", style={"animationDelay": "0.3s"}),
                    html.Div(generate_stats_card("目前景點總數", nums_of_name, "assets/landmark.png"), 
                             className="animate-fade-up", style={"animationDelay": "0.4s"}),
                    html.Div(generate_stats_card("目前餐廳總數", nums_of_restaurant_name, "assets/dinner.png"), 
                             className="animate-fade-up", style={"animationDelay": "0.5s"}),
                ], className="stats-container"),
                width=12, lg=5, className="equal-height-col"
            )
        ], className="mb-5 g-4 equal-height-row"),

        # --- 3. 第二層：快速入口 (修正訂機票圖片) ---
        html.H5("🚀 找尋靈感", className="mb-4 fw-bold px-2", style={"color": "#4A4A4A"}),
        dbc.Row([
            generate_quick_entry("找飯店", "精選全台風格旅宿", 
                                "https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=600&q=80", 
                                "https://www.booking.com"),
            
            # 修正：更換為航空攝影主題，並確保解析度參數正確
            generate_quick_entry("訂機票", "全球航線輕鬆比價", 
                                "https://images.pexels.com/photos/46148/aircraft-jet-landing-cloud-46148.jpeg?auto=compress&cs=tinysrgb&w=600", 
                                "https://www.eztravel.com.tw"),
            
            generate_quick_entry("買門票", "在地體驗與優惠票券", 
                                "https://images.unsplash.com/photo-1533174072545-7a4b6ad7a6c3?auto=format&fit=crop&w=600&q=80", 
                                "https://www.klook.com"),
        ], className="g-4 mb-5"),
    ], className="custom-home-container", style={"padding": "0 80px", "minHeight": "100vh"})

# ⭐️ 這是你漏掉的輔助函式，請務必貼上
def generate_quick_entry(title, sub, img_url, link):
    return dbc.Col(
        html.A([
            html.Div([
                # 圖片層：加入 className="entry-img"
                html.Div(style={
                    "backgroundImage": f"url('{img_url}')", # 加上單引號保護 URL
                    "backgroundSize": "cover",
                    "backgroundPosition": "center",
                    "height": "160px",
                    "transition": "transform 0.5s ease"
                }, className="entry-img"),
                
                # 文字層
                html.Div([
                    html.H6(title, className="fw-bold mb-1 text-dark"),
                    html.Small(sub, className="text-muted")
                ], style={"padding": "20px", "textAlign": "center", "backgroundColor": "white"})
            ], style={
                "borderRadius": "25px", 
                "overflow": "hidden", 
                "boxShadow": "0 4px 15px rgba(0,0,0,0.05)",
                "border": "1px solid rgba(0,0,0,0.05)"
            }, className="quick-link-card-inner")
        ], href=link, target="_blank", style={"textDecoration": "none"}, className="quick-link-card"),
        width=12, md=4
    )
# ==========================================
# 3. Create App & Callbacks
# ==========================================
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
        suppress_callback_exceptions=True,
    )

    # Sidebar Construction
    nav_components = []
    for item in SIDEBAR_ITEMS:
        if item["type"] == "header":
            if item.get("margin_top"): nav_components.append(html.Div(item["label"], className="sidebar-sub-header"))
            else:
                nav_components.append(html.Div(item["label"], className="sidebar-header"))
                nav_components.append(html.Hr(style={'margin': '0 0 10px 0'}))
        elif item["type"] == "link":
            nav_components.append(dbc.NavLink([html.Span(item["icon"], style={'marginRight':'8px'}), item["label"]], href=item["href"], active="exact", className="nav-link", external_link=True))

    sidebar = html.Div([dbc.Nav(nav_components, vertical=True, pills=True)], className="custom-sidebar")

    # Serve Layout
    def serve_layout():
        auth_component = html.Div([html.Span(f"Hi, {current_user.username}", style={'color': '#FFA97F', 'fontWeight': 'bold', 'marginRight': '15px'}), html.A("登出", href="/logout", className="btn-slow-primary")], style={'display': 'flex', 'alignItems': 'center'}) if current_user.is_authenticated else html.Div([html.A("登入", href="/login", className="btn-slow-outline")])
        
        cart_btn_style = {'position': 'fixed', 'bottom': '30px', 'right': '30px', 'width': '60px', 'height': '60px', 'zIndex': '1000', 'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center'}

        return html.Div([
            dcc.Location(id="url", refresh=False),
            dcc.Location(id="redirect-login", refresh=True),
            html.Div([
            html.Div([
                html.Button("☰", id="sidebar-toggle", className="toggle-btn"), 
                # 使用 dcc.Link 確保在 Dash 頁面切換時不重整
                dcc.Link(
                    "SlowDays",href="/dashboard/home", className="header-logo",style={"textDecoration": "none","color": "#FFA97F", "fontWeight": "800","fontSize": "1.8rem","letterSpacing": "1px"}
                )
            ], className="header-left"),auth_component
        ], className="custom-header"),
        
        sidebar,
        html.Div(id="page-content", className="custom-content"),

            
            # 全域行程籃子按鈕
            html.Button([
                # 加入購物車圖示 (bi-cart-fill)
                html.I(className="bi bi-cart-fill me-2", style={'fontSize': '1.3rem'}), 
                html.Span("行程籃子", className="fw-bold"),
                # 數量小紅點
                html.Span("", id="cart-badge", className="position-absolute top-0 start-100 translate-middle badge rounded-pill bg-danger")
            ], id="btn-open-cart", 
            # 使用 rounded-pill 呈現長橢圓膠囊狀
            className="btn btn-primary rounded-pill shadow-lg px-4 d-flex align-items-center", 
            style={
                'position': 'fixed', 
                'bottom': '30px', 
                'right': '30px', 
                'height': '50px', 
                'zIndex': '1000', 
                'border': 'none'
            }),
            
            # 全域購物車側邊欄
            dbc.Offcanvas(id="itinerary-cart-sidebar", title="🗓️ 分配景點至行程", is_open=False, placement="end", children=[
                html.Div([
                    html.Label("1. 選擇目標行程專案", className="fw-bold small mb-1"),
                    dcc.Dropdown(id="select-target-itinerary", placeholder="--- 請選擇行程 ---", className="mb-3"),
                    html.Hr(),
                    html.Label("2. 待分配的項目", className="fw-bold small mb-1"),
                    html.Div(id="cart-items-content"),
                    dbc.Button("確認存入選定行程", id="btn-save-to-itinerary", color="primary", className="w-100 mt-4 rounded-pill"),
                    html.Div(id="save-status-message", className="mt-2 small text-center")
                ], className="p-2")
            ]),
            
            # 全域詳情 Modal (讓地圖和列表共用)
            dbc.Modal([
                dbc.ModalHeader(dbc.ModalTitle(id="modal-detail-title"), close_button=True),
                dbc.ModalBody(id="modal-detail-body"),
                dbc.ModalFooter([html.Div(id="map-modal-footer-action"), dbc.Button("關閉", id="btn-close-modal", className="ms-auto", n_clicks=0)]),
            ], id="modal-detail", size="lg", is_open=False, scrollable=True, centered=True)
        ])

    dash_app.layout = serve_layout
    register_callbacks(dash_app)
    return server

# ==========================================
# 4. Callbacks Definition
# ==========================================
def register_callbacks(app):
    
    # --------------------------------------------------------------------------------
    # 1. 頁面路由與內容渲染
    # --------------------------------------------------------------------------------
    @app.callback(Output('page-content', 'children'), [Input('url', 'pathname')])
    def render_page_content(pathname):
        # 修改預設路徑為 home
        if pathname in ["/dashboard/", "/dashboard", "/dashboard/home"]: 
            return generate_home_page() # 呼叫下方定義的首頁生成函式

        elif pathname == "/dashboard/overview":
            return html.Div([
                dbc.Row([
                    dbc.Col(generate_stats_card("縣市總數", num_of_city, "assets/earth.svg"), width=4),
                    dbc.Col(generate_stats_card("鄉鎮總數", num_of_town, "assets/village.png"), width=4),
                    dbc.Col(generate_stats_card("景點總數", nums_of_name, "assets/landmark.png"), width=4),
                ], style={'marginBottom': '5px'}),
                dbc.Row([
                    dbc.Col(generate_stats_card("活動總數", nums_of_event_name, "assets/calendar.svg"), width=4),
                    dbc.Col(generate_stats_card("住宿總數", nums_of_hotel_name, "assets/bed.png"), width=4),
                    dbc.Col(generate_stats_card("餐廳總數", nums_of_restaurant_name, "assets/dinner.png"), width=4),
                ], style={'marginBottom': '5px'}),
                dbc.Row([
                    dbc.Col([html.H3("各縣市/鄉鎮每個月份活動數", style={'color': THEME['primary']}), dcc.Dropdown(id='dropdown-bar-1', options=[{'label': i, 'value': i}for i in pd.concat([event_df['PostalAddress.City'], event_df['PostalAddress.Town']]).dropna().unique()], value=DEFAULTS['bar1_geo'], placeholder='Select a City/Town', style={'width': '90%'})]),
                    dbc.Col([html.H3("各縣市/鄉鎮的活動種類分佈", style={'color': THEME['primary']}), dcc.Dropdown(id='dropdown-pie-1', options=[{'label': i, 'value': i}for i in pd.concat([event_df['PostalAddress.City'], event_df['PostalAddress.Town']]).dropna().unique()], value=DEFAULTS['pie1_geo'], placeholder='Select a City/Town', style={'width': '50%', 'display': 'inline-block'}), dcc.Dropdown(id='dropdown-pie-2', options=[{'label': '活動類別', 'value': 'EventCategoryNames'}], value=DEFAULTS["pie2_field"], placeholder='Select a value', style={'width': '50%', 'display': 'inline-block'})]),
                ]),
                dbc.Row([dbc.Col([dcc.Loading([html.Div(id='tabs-content-1')], type='default')]), dbc.Col([dcc.Loading([html.Div(id='tabs-content-2')], type='default')])]),
                dbc.Row([
                    dbc.Col([html.H3("景點地理分佈與分類", style={'color': THEME['primary']}), dcc.Dropdown(id='dropdown-map-1', options=[{'label': 'All', 'value': ""}] + [{'label': str(i), 'value': str(i)} for i in pd.concat([attraction_df['PostalAddress.City'], attraction_df['PostalAddress.Town']]).dropna().unique().tolist()], value=DEFAULTS_attraction["map1_geo"], style={'width': '50%', 'display': 'inline-block'}), dcc.Dropdown(id='dropdown-map-2', options=[{'label': '景點類別', 'value': 'PrimaryCategory'}, {'label': '是否免費', 'value': 'IsAccessibleForFree'}], value=DEFAULTS_attraction["map2_metric"], style={'width': '50%', 'display': 'inline-block'})]),
                    dbc.Col([html.H3("旅館價格分佈", style={'color': THEME['primary']}), dcc.Dropdown(id='dropdown-box-1', options=[{'label': i, 'value': i} for i in pd.concat([hotel_df['PostalAddress.City'], hotel_df['PostalAddress.Town']]).dropna().unique()], value=DEFAULTS_hotel["box1_geo"], style={'width': '50%', 'display': 'inline-block'}), dcc.Dropdown(id='dropdown-box-2', options=[{'label': '旅館類別', 'value': 'HotelClassName'}, {'label': '旅館星級', 'value': 'HotelStars'}], value=DEFAULTS_hotel["box2_metric"], style={'width': '50%', 'display': 'inline-block'})]),
                ]),
                dbc.Row([dbc.Col([dcc.Loading([html.Div(id='tabs-content-3')], type='default')]), dbc.Col([dcc.Loading([html.Div(id='tabs-content-4')], type='default')])]),
                dbc.Row([dbc.Col([html.H3("餐廳菜系分佈", style={'color': THEME['primary']}), dcc.Dropdown(id='dropdown-pie-restaurant-geo', options=[{'label': i, 'value': i} for i in pd.concat([restaurant_df['PostalAddress.City'], restaurant_df['PostalAddress.Town']]).dropna().unique()], value=DEFAULTS_restaurant["pie_geo"], style={'width': '50%', 'display': 'inline-block'}), dcc.Dropdown(id='dropdown-pie-restaurant-type', options=[{'label': '食物類別', 'value': 'CuisineNames'}], value='CuisineNames', style={'width': '50%', 'display': 'inline-block'})], width=6)]),
                dbc.Row([dbc.Col([dcc.Loading([html.Div(id='tabs-content-5')], type='default')], width=6), dbc.Col([html.Div(id='tabs-content-6')], width=6)]),
            ])

        elif pathname == "/dashboard/planner":
            all_cities = sorted(pd.concat([attraction_df['PostalAddress.City'], hotel_df['PostalAddress.City'], restaurant_df['PostalAddress.City']]).dropna().unique().tolist())
            hotel_types = sorted(hotel_df['HotelClassName'].dropna().unique().tolist())
            hotel_stars = [5, 4, 3, 2, 1] 
            att_categories = sorted(attraction_df['PrimaryCategory'].dropna().unique().tolist())
            evt_categories = get_exploded_categories(event_df, 'EventCategoryNames', separator=',')
            rest_cuisines = get_exploded_categories(restaurant_df, 'CuisineNames', separator=',')
            initial_month = datetime.now().strftime('%Y-%m-%d')

            return html.Div([
                dbc.Tabs([
                    dbc.Tab(label="🎡 找景點", tab_id="tab-attraction", label_style={"fontWeight": "bold"}),
                    dbc.Tab(label="📅 找活動", tab_id="tab-event", label_style={"fontWeight": "bold"}),
                    dbc.Tab(label="🛏️ 找住宿", tab_id="tab-hotel", label_style={"fontWeight": "bold"}),
                    dbc.Tab(label="🍽️ 找餐廳", tab_id="tab-restaurant", label_style={"fontWeight": "bold"}),
                ], id="planner-tabs", active_tab="tab-attraction", style={"marginBottom": "20px"}),

                dbc.Card([dbc.CardBody([
                    html.Div(id='filter-attraction', children=[
                        dbc.Row([
                            dbc.Col([html.Label("選擇縣市", className="fw-bold small"), dcc.Dropdown(id='planner-att-city', options=[{'label': c, 'value': c} for c in all_cities], placeholder="全臺")], width=6, md=3),
                            dbc.Col([html.Label("鄉鎮市區", className="fw-bold small"), dcc.Dropdown(id='planner-att-town', placeholder="請先選縣市")], width=6, md=3),
                            dbc.Col([html.Label("景點主題", className="fw-bold small"), dcc.Dropdown(id='planner-att-categories', options=[{'label': t, 'value': t} for t in att_categories], multi=True, placeholder="選擇主題...")], width=12, md=6),
                        ]),
                        dbc.Row([dbc.Col([html.Label("其他條件", className="fw-bold small"), dbc.Checklist(id='planner-att-filters', options=[{'label': ' 免費參觀', 'value': 'FREE'}, {'label': ' 有停車場', 'value': 'PARKING'}], inline=True)], width=12)]),
                        dbc.Row([
                            dbc.Col([
                                dbc.Button(
                                    [html.I(className="bi bi-image me-2"), "用圖片找景點"],
                                    id="btn-open-image-search",
                                    color="outline-secondary",
                                    className="rounded-pill px-4",
                                )
                            ], width=12, className="mt-3 text-end")
                        ])
                    ]),
                    html.Div(id='filter-event', style={'display': 'none'}, children=[
                        dbc.Row([
                            dbc.Col([html.Label("📆 活動期間", className="fw-bold small"), dcc.DatePickerRange(id='planner-event-date-range', min_date_allowed=event_df['StartDateTime'].min(), max_date_allowed=event_df['EndDateTime'].max(), initial_visible_month=initial_month, style={'width': '100%'})], width=12, md=5),
                            dbc.Col([html.Label("地點", className="fw-bold small"), dcc.Dropdown(id='planner-event-city', options=[{'label': c, 'value': c} for c in all_cities], placeholder="選擇縣市")], width=6, md=3),
                            dbc.Col([html.Label("類型", className="fw-bold small"), dcc.Dropdown(id='planner-event-categories', options=[{'label': c, 'value': c} for c in evt_categories], multi=True)], width=6, md=4),
                        ])
                    ]),
                    html.Div(id='filter-hotel', style={'display': 'none'}, children=[
                        dbc.Row([
                            dbc.Col([html.Label("地區", className="fw-bold small"), dcc.Dropdown(id='planner-hotel-city', options=[{'label': c, 'value': c} for c in all_cities], placeholder="縣市")], width=6, md=3),
                            dbc.Col([html.Label("預算", className="fw-bold small"), dbc.InputGroup([dbc.Input(id='planner-cost-min', type='number', placeholder='Min'), dbc.InputGroupText("~"), dbc.Input(id='planner-cost-max', type='number', placeholder='Max')])], width=6, md=4),
                            dbc.Col([html.Label("星級與類型", className="fw-bold small"), dcc.Dropdown(id='planner-hotel-stars', options=[{'label': f"{s} 星級", 'value': s} for s in hotel_stars] + [{'label': t, 'value': t} for t in hotel_types], multi=True)], width=12, md=5),
                        ])
                    ]),
                    html.Div(id='filter-restaurant', style={'display': 'none'}, children=[
                        dbc.Row([
                            dbc.Col([html.Label("地點", className="fw-bold small"), dcc.Dropdown(id='planner-restaurant-city', options=[{'label': c, 'value': c} for c in all_cities], placeholder='全臺')], width=6, md=3),
                            dbc.Col([html.Label("菜系", className="fw-bold small"), dcc.Dropdown(id='planner-restaurant-cuisine', options=[{'label': c, 'value': c} for c in rest_cuisines], multi=True)], width=6, md=9),
                        ])
                    ]),
                ])], className="mb-4 shadow-sm", style={"border": "none", "borderRadius": "12px", "backgroundColor": "#fff"}),

                dcc.Store(id="attraction-view-mode", data="default"),
                dcc.Store(id="image-search-results", data=None),
                html.Div(
                    id="image-search-banner",
                    style={
                        "display": "none",
                        "backgroundColor": "#fff3cd",
                        "border": "1px solid #ffeeba",
                        "borderRadius": "8px",
                        "padding": "12px 16px",
                        "marginBottom": "12px"
                    }
                ),

                dcc.Loading(type="default", color="#FFA97F", children=[
                    html.Div(id='result-attraction'), html.Div(id='result-event', style={'display': 'none'}), html.Div(id='result-hotel', style={'display': 'none'}), html.Div(id='result-restaurant', style={'display': 'none'}),
                    html.Div(id='pagination-attraction-container', children=[dbc.Button("◀", id="btn-prev-att", outline=True, size="sm"), html.Span("第", className="mx-1"), dcc.Input(id="input-page-att", type="number", min=1, value=1, style={'width': '50px'}), html.Span(id="label-total-att", className="mx-1"), dbc.Button("▶", id="btn-next-att", outline=True, size="sm")]),
                    html.Div(id='pagination-event-container', style={'display': 'none'}, children=[dbc.Button("◀", id="btn-prev-event", outline=True, size="sm"), html.Span("第", className="mx-1"), dcc.Input(id="input-page-event", type="number", min=1, value=1, style={'width': '50px'}), html.Span(id="label-total-event", className="mx-1"), dbc.Button("▶", id="btn-next-event", outline=True, size="sm")]),
                    html.Div(id='pagination-hotel-container', style={'display': 'none'}, children=[dbc.Button("◀", id="btn-prev-hotel", outline=True, size="sm"), html.Span("第", className="mx-1"), dcc.Input(id="input-page-hotel", type="number", min=1, value=1, style={'width': '50px'}), html.Span(id="label-total-hotel", className="mx-1"), dbc.Button("▶", id="btn-next-hotel", outline=True, size="sm")]),
                    html.Div(id='pagination-restaurant-container', style={'display': 'none'}, children=[dbc.Button("◀", id="btn-prev-restaurant", outline=True, size="sm"), html.Span("第", className="mx-1"), dcc.Input(id="input-page-restaurant", type="number", min=1, value=1, style={'width': '50px'}), html.Span(id="label-total-restaurant", className="mx-1"), dbc.Button("▶", id="btn-next-restaurant", outline=True, size="sm")]),
                ]),

                dbc.Modal([
                    dbc.ModalHeader(dbc.ModalTitle(id="modal-detail-title"), close_button=True),
                    dbc.ModalBody(id="modal-detail-body"),
                    dbc.ModalFooter(
                    children=[
                        html.Div(id="map-modal-footer-action", className="me-auto"),
                        dbc.Button("關閉", id="btn-close-modal", className="ms-auto", n_clicks=0)
                    ],
                )
                ], id="modal-detail", size="lg", is_open=False, scrollable=True, centered=True),
                dbc.Modal(
                    [
                        dbc.ModalHeader(
                            dbc.ModalTitle("🖼️ 用圖片搜尋相似景點"),
                            close_button=True
                        ),
                        dbc.ModalBody([
                            html.P(
                                "上傳你看過的旅遊照片，SlowDays 會幫你找出相似的景點。",
                                className="text-muted small"
                            ),
                            dcc.Upload(
                                id="image-search-upload",
                                children=html.Div([
                                    html.I(className="bi bi-cloud-upload fs-1"),
                                    html.P("拖曳圖片或點擊上傳")
                                ]),
                                style={
                                    'width': '100%',
                                    'height': '200px',
                                    'lineHeight': '200px',
                                    'borderWidth': '2px',
                                    'borderStyle': 'dashed',
                                    'borderRadius': '12px',
                                    'textAlign': 'center',
                                    'cursor': 'pointer'
                                },
                                accept="image/*",
                                multiple=False
                            ),
                            html.Div(id="image-search-preview", className="mt-3"),
                        ]),
                        dbc.ModalFooter([
                            dbc.Button("開始搜尋", id="btn-run-image-search", color="primary"),
                            dbc.Button("取消", id="btn-close-image-search", color="secondary")
                        ])
                    ],
                    id="modal-image-search",
                    is_open=False,
                    centered=True,
                )

            ])

        elif pathname == "/dashboard/attractions":
            city_list = sorted(attraction_df['PostalAddress.City'].dropna().unique().tolist())
            return html.Div([
                html.H3("全臺 POI 地圖與周邊搜尋", style={'color': THEME['primary'], 'marginTop': '5px', 'fontWeight': 'bold'}),
                dbc.Card([dbc.CardBody([
                    dbc.Row([dbc.Col([html.Label("搜尋模式", className="fw-bold"), dcc.RadioItems(id='map-search-mode', options=[{'label': ' 依照縣市瀏覽', 'value': 'city'}, {'label': ' 搜尋特定地點 (周邊)', 'value': 'keyword'}], value='city', inline=True)], width=12, className="mb-3")]),
                    dbc.Row([
                        dbc.Col([html.Label("選擇縣市", className="fw-bold"), dcc.Dropdown(id='poi-city-dropdown', options=[{'label': c, 'value': c} for c in city_list], value=city_list[0] if city_list else None, placeholder="請選擇縣市")], width=4, id='container-city-select'),
                        dbc.Col([html.Label("輸入關鍵字", className="fw-bold"), dbc.InputGroup([dbc.Input(id='poi-search-input', placeholder="台北101...", type="text"), dbc.Button("搜尋", id='btn-keyword-search', color="primary")])], width=6, id='container-keyword-search', style={'display': 'none'}),
                        dbc.Col([html.Label("半徑(km)", className="fw-bold"), dcc.Slider(id='poi-radius-slider', min=1, max=20, step=1, value=5, marks={1:'1', 5:'5', 10:'10', 20:'20'})], width=6, id='container-radius-select', style={'display': 'none'}),
                    ], className="mb-3"),
                    dbc.Row([dbc.Col([html.Label("顯示類別", className="fw-bold"), dcc.Dropdown(id='poi-category-multi', options=[{'label': '景點', 'value': 'attractions'}, {'label': '活動', 'value': 'events'}, {'label': '住宿', 'value': 'hotels'}, {'label': '餐廳', 'value': 'restaurants'}], value=['attractions', 'hotels', 'restaurants'], multi=True)], width=12)])
                ])], className="mb-4 shadow-sm"),
                html.Div(dbc.Button("更新地圖", id='poi-submit-button', color="primary", className="fw-bold"), id='container-submit-btn'),
                html.Div(id='map-message-output', className="mt-2 text-info fw-bold"),
                dcc.Loading(id="poi-loading", type="default", color=THEME['primary'], children=[dcc.Graph(id='poi-map-graph', style={'height': '600px', 'borderRadius': '12px'})]),

                # ⭐️ 新增：全域共用的 Modal (ID 必須與 toggle_detail_modal callback 一致)
                dbc.Modal([
                    dbc.ModalHeader(dbc.ModalTitle(id="modal-detail-title"), close_button=True),
                    dbc.ModalBody(id="modal-detail-body"),
                    dbc.ModalFooter([html.Div(id="map-modal-footer-action"), dbc.Button("關閉", id="btn-close-modal", className="ms-auto", n_clicks=0)]),
                ], id="modal-detail", size="lg", is_open=False, scrollable=True, centered=True),
                
                # ⭐️ 新增：購物車按鈕 (ID 必須與 init_and_control_cart callback 一致)
                html.Button([html.I(className="bi bi-calendar-week", style={'fontSize': '1.5rem'}), html.Span("", id="cart-badge", className="position-absolute top-0 start-100 translate-middle badge rounded-pill bg-danger")], id="btn-open-cart", className="btn btn-primary rounded-circle shadow-lg", style={'position': 'fixed', 'bottom': '30px', 'right': '30px', 'width': '60px', 'height': '60px', 'zIndex': '1000', 'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center'}),
                
                dbc.Offcanvas(id="itinerary-cart-sidebar", title="🗓️ 分配景點至行程", is_open=False, placement="end", children=[html.Div([html.Label("1. 選擇目標行程專案", className="fw-bold small mb-1"), dcc.Dropdown(id="select-target-itinerary", placeholder="--- 請選擇行程 ---", className="mb-3"), html.Hr(), html.Label("2. 待分配的項目", className="fw-bold small mb-1"), html.Div(id="cart-items-content"), dbc.Button("確認存入選定行程", id="btn-save-to-itinerary", color="primary", className="w-100 mt-4 rounded-pill"), html.Div(id="save-status-message", className="mt-2 small text-center")], className="p-2")]),
            ])

    # --------------------------------------------------------------------------------
    # 2. 圖表更新 (Overview)
    # --------------------------------------------------------------------------------
    @app.callback(Output('tabs-content-1', 'children'), [Input('dropdown-bar-1', 'value')])
    def update_bar_chart(dropdown_value):
        geo = dropdown_value or DEFAULTS["bar1_geo"]
        fig = generate_bar(event_df, geo)
        return html.Div([dcc.Graph(figure=fig)])

    @app.callback(Output('tabs-content-2', 'children'), [Input('dropdown-pie-1', 'value'), Input('dropdown-pie-2', 'value')])
    def update_pie_chart(val1, val2):
        geo = val1 or DEFAULTS["pie1_geo"]
        field = val2 or DEFAULTS["pie2_field"]
        fig = generate_pie(event_df, geo, field)
        return html.Div([dcc.Graph(figure=fig)])

    @app.callback(Output('tabs-content-3', 'children'), [Input('dropdown-map-1', 'value'), Input('dropdown-map-2', 'value')])
    def update_attraction_map(city, metric):
        df_f = attraction_df.copy()
        if city: df_f = df_f[(df_f['PostalAddress.City'] == city) | (df_f['PostalAddress.Town'] == city)]
        metric = metric or DEFAULTS_attraction["map2_metric"]
        fig = generate_map(df=df_f, city=city or '臺灣', color_by_column=metric)
        return html.Div([dcc.Graph(figure=fig)], style={'width': '100%'})

    @app.callback(Output('tabs-content-4', 'children'), [Input('dropdown-box-1', 'value'), Input('dropdown-box-2', 'value')])
    def update_box_chart(geo, metric):
        metric = metric or DEFAULTS_hotel["box2_metric"]
        df_f = hotel_df.copy()
        if geo: df_f = df_f[(df_f['PostalAddress.City'] == geo) | (df_f['PostalAddress.Town'] == geo)]
        if df_f.empty: return html.Div("無數據")
        fig = generate_box(df=df_f, geo=geo, metric=metric)
        return html.Div([dcc.Graph(figure=fig)])

    @app.callback(Output('tabs-content-5', 'children'), [Input('dropdown-pie-restaurant-geo', 'value'), Input('dropdown-pie-restaurant-type', 'value')])
    def render_restaurant_sunburst(geo, field):
        if not geo or not field: return html.Div("請選擇條件")
        df_f = restaurant_df[(restaurant_df['PostalAddress.City'] == geo) | (restaurant_df['PostalAddress.Town'] == geo)].copy()
        if df_f.empty: return html.Div("無數據")
        try:
            if df_f[field].dtype == object and df_f[field].str.contains(';').any():
                df_f[field] = df_f[field].str.split(';')
                df_f = df_f.explode(field)
                df_f[field] = df_f[field].str.strip()
        except: pass
        path = ['PostalAddress.City', field] if geo in restaurant_df['PostalAddress.City'].unique() else ['Geo', field]
        if 'Geo' in path: df_f['Geo'] = geo
        fig = px.sunburst(df_f, path=path, values=df_f.index, title=f'{geo} 餐廳分佈')
        return dcc.Graph(figure=fig)

    # --------------------------------------------------------------------------------
    # 3. 頁面切換與篩選 (Planner)
    # --------------------------------------------------------------------------------
    @app.callback(
        [Output('filter-attraction', 'style'), Output('result-attraction', 'style'), Output('pagination-attraction-container', 'style'),
         Output('filter-event', 'style'), Output('result-event', 'style'), Output('pagination-event-container', 'style'),
         Output('filter-hotel', 'style'), Output('result-hotel', 'style'), Output('pagination-hotel-container', 'style'),
         Output('filter-restaurant', 'style'), Output('result-restaurant', 'style'), Output('pagination-restaurant-container', 'style')],
        [Input('planner-tabs', 'active_tab')]
    )
    def switch_planner_tabs(tab):
        hide, show = {'display': 'none'}, {'display': 'block'}
        flex = {'display': 'flex', 'justifyContent': 'center', 'alignItems': 'center', 'marginTop': '1.5rem'}
        if tab == 'tab-attraction': return (show, show, flex, hide, hide, hide, hide, hide, hide, hide, hide, hide)
        if tab == 'tab-event': return (hide, hide, hide, show, show, flex, hide, hide, hide, hide, hide, hide)
        if tab == 'tab-hotel': return (hide, hide, hide, hide, hide, hide, show, show, flex, hide, hide, hide)
        if tab == 'tab-restaurant': return (hide, hide, hide, hide, hide, hide, hide, hide, hide, show, show, flex)
        return (show, show, flex, hide, hide, hide, hide, hide, hide, hide, hide, hide)

    @app.callback(Output('planner-att-town', 'options'), Input('planner-att-city', 'value'))
    def update_town_options(selected_city):
        if not selected_city: return []
        towns = sorted(attraction_df[attraction_df['PostalAddress.City'] == selected_city]['PostalAddress.Town'].dropna().unique().tolist())
        return [{'label': t, 'value': t} for t in towns]

    # --------------------------------------------------------------------------------
    # 4. 卡片列表更新邏輯 (Attraction, Event, Hotel, Restaurant)
    # --------------------------------------------------------------------------------
    @app.callback(
        [Output('result-attraction', 'children'), Output('label-total-att', 'children'), Output('input-page-att', 'value')],
        [Input('planner-att-city', 'value'), Input('planner-att-town', 'value'), Input('planner-att-categories', 'value'), 
         Input('planner-att-filters', 'value'), Input('btn-prev-att', 'n_clicks'), Input('btn-next-att', 'n_clicks'), Input('input-page-att', 'value')],
        [State("attraction-view-mode", "data"), State("image-search-results", "data")]
    )
    def update_attraction_cards(city, town, cats, filters, btn_prev, btn_next, page_input, view_mode, image_results):
        trigger = ctx.triggered_id
        
        # 決定基礎資料來源：如果是圖片模式且有結果，就顯示相似景點
        if view_mode == "image" and image_results:
            df = attraction_df[attraction_df['AttractionID'].isin(image_results)].copy()
            df['AttractionID'] = pd.Categorical(df['AttractionID'], categories=image_results, ordered=True)
            df = df.sort_values('AttractionID')
        else:
            df = preprocess_attraction_df(attraction_df).copy()

        # 執行過濾 (讓結果可連動縣市下拉選單)
        if city: df = df[df['PostalAddress.City'] == city]
        if town: df = df[df['PostalAddress.Town'] == town]
        cats = sanitize_list_input(cats)
        if cats: df = df[df['PrimaryCategory'].isin(cats)]
        
        # 分頁邏輯
        per_page = 15
        pages = math.ceil(len(df) / per_page) or 1
        if trigger == 'btn-prev-att': curr = max(1, (page_input or 1) - 1)
        elif trigger == 'btn-next-att': curr = min(pages, (page_input or 1) + 1)
        elif trigger == 'input-page-att': curr = max(1, min(pages, page_input or 1))
        else: curr = 1

        if df.empty: return html.Div("無符合資料", className="text-center mt-5 text-muted"), " / 1 頁", 1
        df_p = df.iloc[(curr-1)*per_page : curr*per_page]
        favs = {fav.item_id for fav in Favorite.query.filter_by(user_id=current_user.id).all()} if current_user.is_authenticated else set()
        cards = [generate_trip_card(row, "景點", favs) for _, row in df_p.iterrows()]
        return html.Div(cards, className="planner-grid"), f" / {pages} 頁", curr
    # --------------------------------------------------------------------------------
    # 4-A. 以圖搜圖 Modal 開關
    # --------------------------------------------------------------------------------    
    @app.callback(
        Output("modal-image-search", "is_open"),
        [
            Input("btn-open-image-search", "n_clicks"),
            Input("btn-close-image-search", "n_clicks"),
        ],
        State("modal-image-search", "is_open"),
        prevent_initial_call=True
    )
    def toggle_image_search_modal(open_click, close_click, is_open):
        if ctx.triggered_id in ["btn-open-image-search", "btn-close-image-search"]:
            return not is_open
        return is_open

    # --------------------------------------------------------------------------------
    # 4-B. 以圖搜圖 圖片預覽
    # --------------------------------------------------------------------------------    
    @app.callback(
        Output("image-search-preview", "children"),
        Input("image-search-upload", "contents"),
        State("image-search-upload", "filename"),
        prevent_initial_call=True
    )
    def preview_uploaded_image(contents, filename):
        if not contents:
            return no_update

        return html.Div([
            html.P(f"已上傳：{filename}", className="small text-muted"),
            html.Img(
                src=contents,
                style={
                    'maxWidth': '100%',
                    'borderRadius': '8px',
                    'marginTop': '10px'
                }
            )
        ])
    # --------------------------------------------------------------------------------
    # 4-C. 圖片 → 相似景點卡片
    # --------------------------------------------------------------------------------    
    @app.callback(
        [Output("result-attraction", "children", allow_duplicate=True),
         Output("attraction-view-mode", "data"),
         Output("image-search-banner", "children"),
         Output("image-search-banner", "style"),
         Output("image-search-results", "data"),
         Output("modal-image-search", "is_open", allow_duplicate=True)],
        Input("btn-run-image-search", "n_clicks"),
        State("image-search-upload", "contents"),
        prevent_initial_call=True
    )
    def run_image_search(n, contents):
        if not contents or n is None: raise PreventUpdate
        try:
            content_type, content_string = contents.split(',')
            img_bytes = base64.b64decode(content_string)
            img = Image.open(BytesIO(img_bytes)).convert("RGB") 

            # 呼叫 ResNet-50 搜尋
            results = search_similar_images(img, index_path=get_data_path("attraction_image_index.npy"), top_k=20)
            valid_ids = [r["index"] for r in results if r["index"] in attraction_df['AttractionID'].values]
            
            if not valid_ids: return no_update, "default", "搜尋結果為空", {"display": "block"}, None, False

            df_p = attraction_df[attraction_df['AttractionID'].isin(valid_ids)].copy()
            df_p['AttractionID'] = pd.Categorical(df_p['AttractionID'], categories=valid_ids, ordered=True)
            df_p = df_p.sort_values('AttractionID')
            
            suggested_cat = df_p['PrimaryCategory'].mode()[0] if not df_p.empty else "未知"
            favs = {fav.item_id for fav in Favorite.query.filter_by(user_id=current_user.id).all()} if current_user.is_authenticated else set()
            cards = [generate_trip_card(row, "景點", favs) for _, row in df_p.iterrows()]
            
            # 生成含有「清除按鈕」的橫幅
            banner = html.Div([
                html.Div([
                    html.Span("🖼️ 以圖搜圖結果 ", className="fw-bold"),
                    html.Span(f"( AI 辨識類別：{suggested_cat} )", className="ms-2 small"),
                    dbc.Badge("不準？點此搜自然風景", id="btn-fix-category", color="warning", className="ms-2", style={"cursor": "pointer"})
                ]),
                dbc.Button("❌ 清除圖片條件", id="btn-back-to-normal", color="danger", size="sm", className="rounded-pill")
            ], className="d-flex justify-content-between align-items-center w-100")

            return html.Div(cards, className="planner-grid"), "image", banner, {"display": "block", "backgroundColor": "#e3f2fd", "padding": "12px", "borderRadius": "8px", "marginBottom": "15px"}, valid_ids, False
        except Exception as e: return no_update, no_update, f"搜尋出錯: {str(e)}", {"display": "block", "color": "red"}, None, False
    # --------------------------------------------------------------------------------
    # 4-D 清空搜尋結果(重置按鈕)
    # --------------------------------------------------------------------------------
    @app.callback(
        [Output("attraction-view-mode", "data", allow_duplicate=True),
         Output("image-search-results", "data", allow_duplicate=True),
         Output("image-search-banner", "style", allow_duplicate=True),
         Output("input-page-att", "value", allow_duplicate=True),
         Output("image-search-upload", "contents")],
        Input("btn-back-to-normal", "n_clicks"),
        prevent_initial_call=True
    )
    def back_to_normal_logic(n):
        if n: return "default", None, {"display": "none"}, 1, None
        return no_update
    # --------------------------------------------------------------------------------
    # 4-E 以圖搜圖類別不準的挽救
    # --------------------------------------------------------------------------------
    @app.callback(
        [Output('planner-att-categories', 'value'), Output('btn-run-image-search', 'n_clicks')],
        Input('btn-fix-category', 'n_clicks'),
        State('btn-run-image-search', 'n_clicks'),
        prevent_initial_call=True
    )
    def fix_category_search(n, run_clicks):
        if n: return ["自然風景類"], (run_clicks or 0) + 1
        return no_update
    # --------------------------------------------------------------------------------
    # 5. 互動功能 (收藏, Modal, 購物車)
    # --------------------------------------------------------------------------------
    @app.callback(Output({'type': 'btn-add-favorite', 'index': ALL, 'category': ALL}, 'style'), Input({'type': 'btn-add-favorite', 'index': ALL, 'category': ALL}, 'n_clicks'), prevent_initial_call=True)
    def toggle_favorite(n_clicks_list):
        if not current_user.is_authenticated: return [no_update] * len(ctx.outputs_list)
        trigger = ctx.triggered_id
        if not trigger or 'btn-add-favorite' not in str(trigger): return [no_update] * len(ctx.outputs_list)
        item_id, category = trigger['index'], trigger['category']
        try:
            exists = Favorite.query.filter_by(user_id=current_user.id, item_id=item_id).first()
            if exists:
                db.session.delete(exists)
            else:
                row_data = None
                if category == "景點": 
                    t = attraction_df[attraction_df['AttractionID'].astype(str) == str(item_id)]
                    if not t.empty: row_data = t.iloc[0]
                elif category == "活動": 
                    t = event_df[event_df['EventID'].astype(str) == str(item_id)]
                    if not t.empty: row_data = t.iloc[0]
                elif category == "住宿": 
                    t = hotel_df[hotel_df['HotelID'].astype(str) == str(item_id)]
                    if not t.empty: row_data = t.iloc[0]
                elif category == "餐廳": 
                    t = restaurant_df[restaurant_df['RestaurantID'].astype(str) == str(item_id)]
                    if not t.empty: row_data = t.iloc[0]
                
                if row_data is not None:
                    name = row_data.get('AttractionName') or row_data.get('EventName') or row_data.get('HotelName') or row_data.get('RestaurantName')
                    img = row_data.get('ThumbnailURL') or row_data.get('Picture.PictureUrl1') or row_data.get('PictureUrl1')
                    city = row_data.get('PostalAddress.City') or row_data.get('City')
                    db.session.add(Favorite(user_id=current_user.id, item_id=item_id, category=category, name=name, image_url=img, location=city))
            db.session.commit()
        except: db.session.rollback()
        
        current_fav_ids = {f.item_id for f in Favorite.query.filter_by(user_id=current_user.id).all()}
        return [{'color': '#dc3545' if i['id']['index'] in current_fav_ids else 'white'} for i in ctx.outputs_list]

    # ==============================================================================
    # 6-A. 詳情 Modal - 來自「列表按鈕」 (Planner)
    # ==============================================================================
    # --- [Helper] 通用資料查詢函式 (給列表和地圖共用) ---
    def get_data_by_id(target_id, category):
        target_id = str(target_id)
        row = None
        if category == "景點": 
            t = attraction_df[attraction_df['AttractionID'].astype(str) == target_id]
            if not t.empty: row = t.iloc[0]
        elif category == "住宿": 
            t = hotel_df[hotel_df['HotelID'].astype(str) == target_id]
            if not t.empty: row = t.iloc[0]
        elif category == "活動": 
            t = event_df[event_df['EventID'].astype(str) == target_id]
            if not t.empty: row = t.iloc[0]
        elif category in ["餐廳", "餐飲"]: 
            t = restaurant_df[restaurant_df['RestaurantID'].astype(str) == target_id]
            if not t.empty: row = t.iloc[0]
        return row

    # --- [Helper] 生成 Modal 內容 ---
    def generate_modal_content(target_id, category):
        row = get_data_by_id(target_id, category)
        if row is None:
            return "錯誤", html.Div("找不到該筆資料"), None
            
        content = create_detail_content(row, category)
        title = row.get('AttractionName') or row.get('EventName') or row.get('HotelName') or row.get('RestaurantName') or "詳情"
        
        # 生成加入按鈕
        add_btn = dbc.Button(
            [html.I(className="bi bi-cart-plus me-2"), "加入行程"],
            id={'type': 'btn-add-cart', 'index': str(target_id), 'category': category},
            color="success",
            className="rounded-pill"
        )
        return title, content, add_btn
    

    @app.callback(
        [Output("modal-detail", "is_open", allow_duplicate=True),
        Output("modal-detail-title", "children", allow_duplicate=True),
        Output("modal-detail-body", "children", allow_duplicate=True),
        Output("map-modal-footer-action", "children", allow_duplicate=True)], 
        [Input({'type': 'btn-view-detail', 'index': ALL, 'category': ALL}, 'n_clicks'),
        Input("btn-close-modal", "n_clicks")],
        [State("modal-detail", "is_open")],
        prevent_initial_call=True
    )
    def open_modal_from_list(n_clicks_list, n_close, is_open):
        import dash
        print("Callback 被呼叫了！")
        print(f"Triggered ID: {dash.ctx.triggered_id}")

        trigger = ctx.triggered_id
        
        # Debug 訊息
        print(f"Callback 被觸發! Trigger ID: {trigger}")

        if trigger == "btn-close-modal":
            return False, "", "", ""
        
        if isinstance(trigger, dict) and trigger.get('type') == 'btn-view-detail':
            if not n_clicks_list or all((c is None or c == 0) for c in n_clicks_list):
                print("DEBUG: 按鈕剛生成 (Ghost Fire)，忽略執行。")
                return is_open, no_update, no_update, no_update
        
            target_id = trigger['index']
            category = trigger['category']
            
            print(f"DEBUG: 準備查詢詳情 - ID={target_id}, 類別={category}")
            
            try:
                # 這裡是最容易出錯的地方，加上 try-except 保護
                title, content, btn = generate_modal_content(target_id, category)
                print("DEBUG: 內容生成成功，準備開啟 Modal")
                return True, title, content, btn
            except Exception as e:
                import traceback
                print("ERROR: 產生 Modal 內容時發生錯誤:")
                print(traceback.format_exc()) # 這會把完整錯誤訊息印在終端機
                return no_update, no_update, no_update, no_update

        return is_open, no_update, no_update, no_update
    
    # ==============================================================================
    # 6-B. 詳情 Modal - 來自「地圖點擊」 (Attractions)
    # ==============================================================================
    @app.callback(
        [Output("modal-detail", "is_open", allow_duplicate=True),
         Output("modal-detail-title", "children", allow_duplicate=True),
         Output("modal-detail-body", "children", allow_duplicate=True),
         Output("map-modal-footer-action", "children", allow_duplicate=True)], 
        [Input('poi-map-graph', 'clickData'),
         Input("btn-close-modal", "n_clicks")],
        [State("modal-detail", "is_open")],
        prevent_initial_call=True
    )
    def open_modal_from_map(click_data, n_close, is_open):
        trigger = ctx.triggered_id
        
        # 1. 處理關閉
        if trigger == "btn-close-modal":
            return False, "", "", ""

        # 2. 處理地圖點擊
        if not click_data:
            raise PreventUpdate

        try:
            # 從 custom_data 解析 [ID, Category]
            p = click_data['points'][0]['customdata']
            if not p or len(p) < 2:
                raise PreventUpdate
                
            target_id = str(p[0])
            category = str(p[1])
            
            print(f"DEBUG: 地圖被點擊! ID={target_id}, 類別={category}") # 檢查這裡
            
            title, content, btn = generate_modal_content(target_id, category)
            return True, title, content, btn
            
        except Exception as e:
            print(f"Map Click Error: {e}")
            return is_open, no_update, no_update, no_update

    @app.callback(
        [Output({'type': 'btn-add-cart', 'index': ALL, 'category': ALL}, 'children'), 
        Output({'type': 'btn-add-cart', 'index': ALL, 'category': ALL}, 'color'), 
        Output("cart-items-content", "children", allow_duplicate=True), 
        Output("cart-badge", "children", allow_duplicate=True), 
        Output("itinerary-cart-sidebar", "is_open", allow_duplicate=True)],
        [Input({'type': 'btn-add-cart', 'index': ALL, 'category': ALL}, 'n_clicks')], 
        prevent_initial_call=True
    )
    def add_to_cart_global(n_clicks_list):
        trigger = ctx.triggered_id
        
        # 初始化：全部 no_update
        no_updates_list = [no_update] * len(n_clicks_list)
        
        # 1. 防止 Ghost Fire (剛載入頁面時的自動觸發)
        if not trigger or not any(n for n in n_clicks_list if n): 
            return no_updates_list, no_updates_list, no_update, no_update, no_update

        # 2. 【安全檢查】確認是否登入
        # 如果沒登入，直接結束函式，不做任何動作 (避免讀取 current_user.id 導致崩潰)
        if not current_user.is_authenticated:
            print("使用者未登入，忽略加入行程操作")
            return no_updates_list, no_updates_list, no_update, no_update, no_update

        # --- 以下是已登入才會執行的區域 ---

        target_id = str(trigger['index'])
        category = trigger['category']
        
        try:
            # 3. 寫入資料庫邏輯
            if not CartItem.query.filter_by(user_id=current_user.id, item_id=target_id).first():
                row = get_data_by_id(target_id, category)
                if row is not None:
                    name_col = 'AttractionName' if category == '景點' else 'EventName' if category == '活動' else 'HotelName' if category == '住宿' else 'RestaurantName'
                    img = row.get('ThumbnailURL') or row.get('Picture.PictureUrl1') or row.get('PictureUrl1') or "https://placehold.co/100"
                    loc = row.get('PostalAddress.City') or row.get('City') or "台灣"
                    
                    db.session.add(CartItem(user_id=current_user.id, item_id=target_id, category=category, name=row.get(name_col, '未命名'), image_url=img, location=loc))
                    db.session.commit()
        except Exception as e: 
            print(f"Database Error: {e}")
            db.session.rollback()
        
        # 4. 更新 UI 邏輯
        curr_ids = {str(c.item_id) for c in CartItem.query.filter_by(user_id=current_user.id).all()}
        
        children, colors = [], []
        for inp in ctx.inputs_list[0]:
            if str(inp['id']['index']) in curr_ids:
                children.append([html.I(className="bi bi-check-circle-fill me-1"), "已加入"])
                colors.append("secondary")
            else:
                children.append([html.I(className="bi bi-cart-plus me-1"), "加入行程"])
                colors.append("success")
        
        cart_html, badge = generate_cart_html()
        
        return children, colors, cart_html, badge, no_update

    @app.callback(
        [Output("cart-items-content", "children", allow_duplicate=True), 
         Output("cart-badge", "children", allow_duplicate=True)], 
        [Input({'type': 'btn-delete-cart-item', 'index': ALL}, 'n_clicks')], 
        prevent_initial_call=True
    )
    def delete_cart_item(n_clicks_list):
        trigger = ctx.triggered_id
        if not trigger or not any(n_clicks_list): raise PreventUpdate
        try:
            CartItem.query.filter_by(user_id=current_user.id, item_id=trigger['index']).delete()
            db.session.commit()
        except: db.session.rollback()
        return generate_cart_html()

    def generate_cart_html():
        if not current_user.is_authenticated: return html.P("請先登入"), ""
        items = CartItem.query.filter_by(user_id=current_user.id).order_by(CartItem.created_at.desc()).all()
        count = len(items)
        if not items: return html.P("籃子目前是空的", className="text-center mt-5 text-muted"), ""
        
        cart_html = [
            html.Div([
                html.Div([
                    html.Img(src=i.image_url, style={'width': '50px', 'height': '50px', 'objectFit': 'cover', 'borderRadius': '5px'}),
                    html.Div([
                        html.Div(i.name, className="fw-bold small text-truncate", style={'maxWidth': '140px'}),
                        html.Small(i.category, className="text-muted")
                    ], className="ms-3 flex-grow-1")
                ], className="d-flex align-items-center"),
                # ⭐️ 使用 Emoji 確保顯示
                dbc.Button("🗑️", id={'type': 'btn-delete-cart-item', 'index': str(i.item_id)}, 
                           color="light", size="sm", className="text-danger border-0 fs-5 px-2")
            ], className="d-flex justify-content-between align-items-center mb-2 border-bottom pb-2") for i in items
        ]
        return cart_html, str(count) if count > 0 else ""

    @app.callback(
        [Output("btn-open-cart", "style"), 
        Output("cart-badge", "children"), 
        Output("cart-items-content", "children")], 
        [Input("url", "pathname")]
    )
    def init_and_control_cart(pathname):
        # 僅在特定路徑顯示籃子按鈕
        if pathname not in ["/dashboard/planner", "/dashboard/attractions"]: 
            return {'display': 'none'}, "", ""
        
        cart_html, badge = generate_cart_html()
        
        # 確保回傳的樣式支持長橢圓形與內部對齊
        return {
            'position': 'fixed', 
            'bottom': '30px', 
            'right': '30px', 
            'height': '50px', 
            'zIndex': '1000', 
            'display': 'flex', 
            'alignItems': 'center', 
            'justifyContent': 'center',
            'border': 'none'
        }, badge, cart_html

    @app.callback(Output("itinerary-cart-sidebar", "is_open", allow_duplicate=True), [Input("btn-open-cart", "n_clicks")], [State("itinerary-cart-sidebar", "is_open")], prevent_initial_call=True)
    def toggle_sidebar(n, is_open): return not is_open if n else is_open

    @app.callback(Output("select-target-itinerary", "options"), [Input("itinerary-cart-sidebar", "is_open")])
    def load_plans(is_open):
        if is_open and current_user.is_authenticated:
            return [{'label': p.title, 'value': p.id} for p in Itinerary.query.filter_by(user_id=current_user.id).all()]
        return []

    @app.callback([Output("cart-items-content", "children", allow_duplicate=True), Output("cart-badge", "children", allow_duplicate=True), Output("save-status-message", "children")], [Input("btn-save-to-itinerary", "n_clicks")], [State("select-target-itinerary", "value")], prevent_initial_call=True)
    def save_to_plan(n, plan_id):
        if not n or not plan_id: raise PreventUpdate
        try:
            items = CartItem.query.filter_by(user_id=current_user.id).all()
            for i in items:
                db.session.add(ItineraryDetail(itinerary_id=plan_id, item_id=i.item_id, name=i.name, category=i.category, image_url=i.image_url, location=i.location, day_number=0, sort_order=0))
                db.session.delete(i)
            db.session.commit()
            return generate_cart_html()[0], "", "✅ 存入成功！"
        except: db.session.rollback(); return no_update, no_update, "❌ 錯誤"

    @app.callback([Output('poi-map-graph', 'figure'), Output('map-message-output', 'children')], [Input('poi-submit-button', 'n_clicks'), Input('btn-keyword-search', 'n_clicks')], [State('map-search-mode', 'value'), State('poi-city-dropdown', 'value'), State('poi-search-input', 'value'), State('poi-radius-slider', 'value'), State('poi-category-multi', 'value')])
    def update_map(btn1, btn2, mode, city, key, rad, cats):
        fig = px.scatter_mapbox(lat=[23.5], lon=[121], zoom=6); fig.update_layout(mapbox_style="carto-positron", margin={"r":0,"t":0,"l":0,"b":0})
        if not cats: return fig, "請選擇類別"
        
        dfs = []
        # ⭐️ 強制轉型 ID 為 str 以確保後續比對正確
        if 'attractions' in cats: dfs.append(attraction_df.assign(Type='景點', Name=attraction_df['AttractionName'], ID=attraction_df['AttractionID'].astype(str)))
        if 'hotels' in cats: dfs.append(hotel_df.assign(Type='住宿', Name=hotel_df['HotelName'], ID=hotel_df['HotelID'].astype(str)))
        if 'restaurants' in cats: dfs.append(restaurant_df.assign(Type='餐廳', Name=restaurant_df['RestaurantName'], ID=restaurant_df['RestaurantID'].astype(str)))
        if 'events' in cats: dfs.append(event_df.assign(Type='活動', Name=event_df['EventName'], ID=event_df['EventID'].astype(str)))
        
        if not dfs: return fig, "無資料"
        full_df = pd.concat(dfs, ignore_index=True)
        full_df['Lat'] = pd.to_numeric(full_df['Lat'], errors='coerce')
        full_df['Lon'] = pd.to_numeric(full_df['Lon'], errors='coerce')
        full_df = full_df.dropna(subset=['Lat', 'Lon'])
        
        final_df, center_lat, center_lon, zoom = pd.DataFrame(), 23.6, 120.9, 7
        if mode == 'city' and city:
            final_df = full_df[full_df['PostalAddress.City'] == city]
            if not final_df.empty: center_lat, center_lon, zoom = final_df['Lat'].mean(), final_df['Lon'].mean(), 10
        elif mode == 'keyword' and key:
            target = full_df[full_df['Name'].str.contains(key, case=False, na=False)]
            if not target.empty:
                t = target.iloc[0]
                center_lat, center_lon = t['Lat'], t['Lon']
                full_df['Dist'] = full_df.apply(lambda x: calculate_distance(center_lat, center_lon, x['Lat'], x['Lon']), axis=1)
                final_df = full_df[full_df['Dist'] <= rad]
                zoom = 13 if rad <= 5 else 11
        
        if final_df.empty: return fig, "無符合資料"
        
        fig = px.scatter_mapbox(final_df, lat="Lat", lon="Lon", color="Type", hover_name="Name", zoom=zoom, center={"lat": center_lat, "lon": center_lon}, size_max=15, custom_data=['ID', 'Type'])
        fig.update_layout(mapbox_style="carto-positron", margin={"r":0,"t":0,"l":0,"b":0}, clickmode='event+select')
        return fig, f"顯示 {len(final_df)} 筆資料"

    @app.callback([Output('container-city-select', 'style'), Output('container-submit-btn', 'style'), Output('container-keyword-search', 'style'), Output('container-radius-select', 'style')], [Input('map-search-mode', 'value')])
    def toggle_mode(mode):
        show, hide = {'display': 'block'}, {'display': 'none'}
        return (show, show, hide, hide) if mode == 'city' else (hide, hide, show, show)
    
    @app.callback(
        Output("login-warning-dialog", "displayed"), 
        Input({'type': 'btn-add-cart', 'index': ALL, 'category': ALL}, 'n_clicks'),
        # 💡 移除原本的 State("user-login-store", "data")
        prevent_initial_call=True
    )
    def add_to_itinerary(n_clicks_list): # 💡 參數減少一個
        trigger = ctx.triggered_id

        # 1. 防止 Ghost Fire (剛載入頁面時的自動觸發)
        if not n_clicks_list or all((c is None or c == 0) for c in n_clicks_list):
            return False

        # 2. 確認是點擊「加入行程」按鈕
        if isinstance(trigger, dict) and trigger.get('type') == 'btn-add-cart':
            
            # 💡 關鍵修正：直接利用 Flask-Login 的 current_user 物件判斷
            # 這是在後端運行的，最準確且不需要組件 ID
            if not current_user.is_authenticated:
                print(f"擋下操作：使用者未登入 (ID: {trigger['index']})")
                return True # 顯示警告視窗
            
            # 如果已登入，這裡可以放其他邏輯（或單純回傳 False 不顯示警告）
            return False

        return False

