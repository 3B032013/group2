from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from . import db
from .models import User, Favorite, Itinerary, ItineraryDetail
from .nav_config import SIDEBAR_ITEMS
from datetime import datetime
import pandas as pd
import json
import os

# ======================
# Auth Blueprint（原本的）
# ======================
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # 1. 從前端表單抓取資料 (對應 input 的 name)
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        # 2. 檢查是否已經被註冊過
        user_exists = User.query.filter_by(email=email).first()
        if user_exists:
            flash('這個 Email 已經被註冊過了！')
            return redirect('/register')

        # 3. 建立新使用者 (密碼記得加密，不要存明碼)
        hashed_password = generate_password_hash(password, method='scrypt')
        new_user = User(username=username, email=email, password=hashed_password)

        # 4. 寫入資料庫
        db.session.add(new_user)
        db.session.commit()

        # 5. 註冊成功，導向登入頁
        return redirect('/login')

    return render_template('register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        print(f"DEBUG: 收到登入請求 - Email: {email}, Password: {password}")

        # 1. 找使用者
        user = User.query.filter_by(email=email).first()
        
        if user:
            print(f"DEBUG: 找到使用者 ID: {user.id}, 名稱: {user.username}")
            print(f"DEBUG: 資料庫內的密碼 Hash: {user.password}")
            
            # 2. 驗證密碼
            is_password_correct = check_password_hash(user.password, password)
            print(f"DEBUG: 密碼驗證結果: {is_password_correct}")

            if is_password_correct:
                print("DEBUG: 登入成功！執行 login_user...")
                login_user(user)
                return redirect('/dashboard/')
            else:
                print("DEBUG: 密碼錯誤！(應該要擋住)")
                flash('密碼錯誤')
        else:
            print("DEBUG: 找不到此 Email (應該要擋住)")
            flash('找不到此帳號')
    
    # 登入失敗或 GET 請求，都會回到登入頁
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required # 保護這個路由，只有登入者能訪問
def logout():
    logout_user() # 清除 session
    return redirect('/login')


# ======================
# 引入你的資料處理工具 (確保這些函式能被引用)
from .utils.data_clean import (
    load_and_merge_attractions_data,
    load_and_clean_event_data,
    load_and_clean_hotel_data,
    load_and_merge_restaurant_data
)

# 設定資料路徑 (自動抓取上一層的 data 資料夾)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

def get_data_path(filename):
    return os.path.join(DATA_DIR, filename)

print("正在 routes.py 中載入地圖資料庫...")

# 載入 4 大資料表 (這樣 routes.py 就能直接使用這些變數)
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
# ======================

# ======================
# Member Blueprint（新增的）
# ======================
member_bp = Blueprint('member', __name__)

@member_bp.context_processor
def inject_common_vars():
    return dict(sidebar_items=SIDEBAR_ITEMS)

@member_bp.route('/preferences', methods=['GET', 'POST'])
@login_required
def preferences():
    if request.method == 'POST':
        preferences = {
            "activity_types": request.form.getlist("activity_type"),
            "travel_pace": request.form.get("travel_pace"),
            "season": request.form.getlist("season")
        }
        print(preferences)  # 示意用
        return redirect(url_for('member.preferences'))

    return render_template('member/preferences.html')

@member_bp.route('/favorites')
@login_required
def favorites():
    # 1. 取得 URL 參數 (預設第 1 頁，預設類別 'all')
    page = request.args.get('page', 1, type=int)
    category_filter = request.args.get('category', 'all')
    per_page = 15  # 一頁 15 筆

    # 2. 基礎查詢 (只查當前使用者)
    base_query = Favorite.query.filter_by(user_id=current_user.id).order_by(Favorite.created_at.desc())

    # 3. 計算各分類的數量 (用於 Tabs 顯示數字)
    # 這裡做個別查詢，確保數字準確
    counts = {
        'all': base_query.count(),
        'attractions': base_query.filter_by(category='景點').count(),
        'events': base_query.filter_by(category='活動').count(),
        'hotels': base_query.filter_by(category='住宿').count(),
        'restaurants': base_query.filter_by(category='餐廳').count()
    }

    # 4. 根據選擇的類別進行篩選
    if category_filter == 'attractions':
        base_query = base_query.filter_by(category='景點')
    elif category_filter == 'events':
        base_query = base_query.filter_by(category='活動')
    elif category_filter == 'hotels':
        base_query = base_query.filter_by(category='住宿')
    elif category_filter == 'restaurants':
        base_query = base_query.filter_by(category='餐廳')

    # 5. 執行分頁 (Flask-SQLAlchemy 的 paginate 方法)
    pagination = base_query.paginate(page=page, per_page=per_page, error_out=False)
    favorites_list = pagination.items

    # 6. 資料清理 (處理 NaN 圖片)
    valid_favorites = []
    for fav in favorites_list:
        if not fav.image_url or str(fav.image_url).lower() == 'nan':
            fav.image_url = "https://placehold.co/600x400/eee/999?text=No+Image"
        if not fav.location or str(fav.location).lower() == 'nan':
            fav.location = "台灣"
        valid_favorites.append(fav)

    # 7. 回傳模板
    return render_template(
        'member/favorites.html', 
        favorites=valid_favorites, 
        pagination=pagination,
        counts=counts,
        current_category=category_filter
    )

@member_bp.route('/favorites/remove/<int:fav_id>', methods=['POST'])
@login_required
def remove_favorite(fav_id):
    fav = Favorite.query.filter_by(id=fav_id, user_id=current_user.id).first()
    if fav:
        db.session.delete(fav)
        db.session.commit()
    return redirect(url_for('member.favorites'))

@member_bp.route('/schedule')
@login_required
def schedule():
    # 讀取該會員的所有行程專案
    itineraries = Itinerary.query.filter_by(user_id=current_user.id).order_by(Itinerary.created_at.desc()).all()
    return render_template('member/schedule.html', itineraries=itineraries)

@member_bp.route('/schedule/create', methods=['POST'])
@login_required
def create_itinerary():
    title = request.form.get('title')
    # 接收日期字串並轉為 Python date 物件
    start_date_str = request.form.get('start_date')
    end_date_str = request.form.get('end_date')
    
    if title and start_date_str and end_date_str:
        # 將字串轉換為 date 物件 (格式 YYYY-MM-DD)
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
        new_plan = Itinerary(
            user_id=current_user.id, 
            title=title,
            start_date=start_date,
            end_date=end_date
        )
        db.session.add(new_plan)
        db.session.commit()
        
    return redirect(url_for('member.schedule'))

# 這個是之後要做的「拖曳排程」詳細頁面
@member_bp.route('/schedule/edit/<int:itinerary_id>')
@login_required
def edit_schedule(itinerary_id):
    from datetime import timedelta
    plan = Itinerary.query.get_or_404(itinerary_id)
    if plan.user_id != current_user.id:
        return "權限不足", 403
    
    # ⭐️ 核心修正：在後端先計算好總天數
    if plan.start_date and plan.end_date:
        total_days = (plan.end_date - plan.start_date).days + 1
    else:
        total_days = 1 # 防呆，若沒設定日期預設為 1 天

    return render_template(
        'member/edit_schedule.html', 
        plan=plan, 
        timedelta=timedelta, 
        total_days=total_days
    )

# 1. 儲存拖曳後的排序與抵達時間
@member_bp.route('/schedule/save_all', methods=['POST'])
@login_required
def save_all_schedule():
    data = request.get_json()
    items = data.get('items', [])
    try:
        for item in items:
            # 確保傳入的 ID 是整數
            detail_id = int(item['id'])
            detail = ItineraryDetail.query.get(detail_id)
            
            if detail and detail.itinerary.user_id == current_user.id:
                # ⭐️ 更新所有欄位
                detail.day_number = int(item['day_number'])
                detail.sort_order = int(item['sort_order'])
                
                # 如果在 day 0 (池子)，時間可以存 null
                detail.start_time = item.get('start_time')
                detail.end_time = item.get('end_time')
                
        db.session.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        db.session.rollback()
        print(f"DEBUG Save Error: {e}") # 方便你排錯
        return jsonify({'status': 'error', 'message': str(e)}), 500

@member_bp.route('/schedule/rename/<int:itinerary_id>', methods=['POST'])
@login_required
def rename_itinerary(itinerary_id):
    # 驗證權限
    plan = Itinerary.query.filter_by(id=itinerary_id, user_id=current_user.id).first_or_404()
    
    data = request.get_json()
    new_title = data.get('title', '').strip()
    
    if not new_title:
        return jsonify({'status': 'error', 'message': '標題不能為空'}), 400
        
    try:
        plan.title = new_title
        db.session.commit()
        return jsonify({'status': 'success', 'message': '標題已更新'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

# 2. 刪除單一地點
@member_bp.route('/schedule/delete/<int:itinerary_id>', methods=['POST'])
@login_required
def delete_itinerary(itinerary_id):
    # 1. 搜尋該行程，並確保是當前使用者的
    plan = Itinerary.query.filter_by(id=itinerary_id, user_id=current_user.id).first_or_404()
    
    try:
        # 2. 刪除行程 (SQLAlchemy 會自動刪除關聯的 details，如果有關聯設定的話)
        # 如果沒有設定 cascade，這裡可能需要手動刪除 details，但通常 Itinerary 刪除就好
        db.session.delete(plan)
        db.session.commit()
        return jsonify({'status': 'success', 'message': '行程已刪除'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
@member_bp.route('/schedule/detail/delete/<int:detail_id>', methods=['POST'])
@login_required
def delete_itinerary_detail(detail_id):
    # 搜尋該細節，並透過 join 確保它屬於當前使用者的行程
    detail = ItineraryDetail.query.join(Itinerary).filter(
        ItineraryDetail.id == detail_id,
        Itinerary.user_id == current_user.id
    ).first_or_404()
    
    try:
        db.session.delete(detail)
        db.session.commit()
        return jsonify({'status': 'success', 'message': '項目已刪除'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
@member_bp.route('/schedule/map/<int:itinerary_id>')
@login_required
def schedule_map(itinerary_id):
    plan = Itinerary.query.filter_by(id=itinerary_id, user_id=current_user.id).first_or_404()
    
    daily_routes = {}
    
    # ⭐️ 移除這一行，因為我們已經在上面定義全域變數了
    # from .app import attraction_df, restaurant_df... (這行刪掉)

    # 建立查找 Helper
    def get_coords(item_id, category):
        row = None
        # 注意：這裡直接使用全域變數 attraction_df 等
        if category == '景點':
            row = attraction_df[attraction_df['AttractionID'].astype(str) == str(item_id)]
        elif category == '餐飲' or category == '餐廳':
            row = restaurant_df[restaurant_df['RestaurantID'].astype(str) == str(item_id)]
        elif category == '住宿':
            row = hotel_df[hotel_df['HotelID'].astype(str) == str(item_id)]
        elif category == '活動':
            row = event_df[event_df['EventID'].astype(str) == str(item_id)]
            
        if row is not None and not row.empty:
            # 兼容不同的欄位名稱 (有些資料可能是 PositionLat，有些是 Lat)
            lat = row.iloc[0].get('Lat')
            lon = row.iloc[0].get('Lon')
            
            # 如果是 NaN，嘗試讀取 PositionLat
            if pd.isna(lat): lat = row.iloc[0].get('PositionLat')
            if pd.isna(lon): lon = row.iloc[0].get('PositionLon')
                
            return lat, lon
        return None, None

    # 整理資料
    sorted_details = sorted(plan.details, key=lambda x: (x.day_number, x.start_time or '00:00'))
    
    for detail in sorted_details:
        if detail.day_number == 0: continue 
        
        lat, lng = get_coords(detail.item_id, detail.category)
        
        if lat and lng and not pd.isna(lat) and not pd.isna(lng):
            if detail.day_number not in daily_routes:
                daily_routes[detail.day_number] = []
            
            daily_routes[detail.day_number].append({
                'name': detail.name,
                'lat': float(lat),
                'lng': float(lng),
                'time': f"{detail.start_time} - {detail.end_time}",
                'category': detail.category
            })

    return render_template('member/schedule_map.html', plan=plan, daily_routes=daily_routes)