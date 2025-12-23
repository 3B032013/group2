from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from . import db
from .models import User, Favorite, Itinerary, ItineraryDetail
from .nav_config import SIDEBAR_ITEMS
from datetime import datetime, timedelta
from .utils.attraction_mapping import ATTRACTION_TYPE_MAPPING
from .utils.accommodation_mapping import ACCOMMODATION_TYPE_MAPPING
from .utils.restaurant_mapping import RESTAURANT_TYPE_MAPPING
import pandas as pd
import json
import os

# ======================
# Auth Blueprint
# ======================
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        user_exists = User.query.filter_by(email=email).first()
        if user_exists:
            flash('這個 Email 已經被註冊過了！')
            return redirect('/register')

        hashed_password = generate_password_hash(password, method='scrypt')
        new_user = User(username=username, email=email, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        return redirect('/login')
    return render_template('register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect('/dashboard/')
        flash('帳號或密碼錯誤')
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/login')

# ======================
# 資料載入與清理工具
# ======================
from .utils.data_clean import (
    load_and_merge_attractions_data,
    load_and_clean_event_data,
    load_and_clean_hotel_data,
    load_and_merge_restaurant_data
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

def get_data_path(filename):
    return os.path.join(DATA_DIR, filename)

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
# Member Blueprint
# ======================
member_bp = Blueprint('member', __name__)

@member_bp.context_processor
def inject_common_vars():
    return dict(sidebar_items=SIDEBAR_ITEMS)

@member_bp.route('/recommend')
@login_required
def recommend():
    preferences = session.get("preferences", {})
    content_types = preferences.get("content_types", [])
    attraction_types = preferences.get("attraction_types", [])
    accommodation_types = preferences.get("accommodation_types", [])
    food_types = preferences.get("food_types", [])

    recommended_attractions = []
    recommended_restaurants = []
    recommended_hotels = []

    # --- 景點篩選 ---
    if 'attractions' in content_types:
        filtered_df = attraction_df.copy()
        if "ThumbnailURL" in filtered_df.columns:
            filtered_df = filtered_df[filtered_df["ThumbnailURL"].notna() & (filtered_df["ThumbnailURL"] != "")]
        if attraction_types:
            allowed_classes = []
            for t in attraction_types:
                allowed_classes += ATTRACTION_TYPE_MAPPING.get(t, [])
            if "PrimaryCategory" in filtered_df.columns:
                filtered_df = filtered_df[filtered_df["PrimaryCategory"].isin(allowed_classes)]
        recommended_attractions = filtered_df.head(10).to_dict('records')

    # --- 餐廳篩選 ---
    if 'food' in content_types:
        food_df = restaurant_df.copy()
        def force_extract(row):
            cat_data = row.get('RestaurantCategoryName')
            category = "未分類"
            if isinstance(cat_data, list) and len(cat_data) > 0:
                category = cat_data[0].get('Name', '未分類') if isinstance(cat_data[0], dict) else category
            addr = row.get('PostalAddress')
            city = addr.get('City') if isinstance(addr, dict) else (row.get('City') or "台灣")
            pic = row.get('Picture')
            img = pic.get('PictureUrl1', '') if isinstance(pic, dict) else (row.get('ThumbnailURL') or "")
            return pd.Series([category, city, img], index=['RestaurantCategory', 'City', 'ThumbnailURL'])
        
        food_df[['RestaurantCategory', 'City', 'ThumbnailURL']] = food_df.apply(force_extract, axis=1)
        if food_types:
            allowed_cats = []
            for ft in food_types:
                allowed_cats += RESTAURANT_TYPE_MAPPING.get(ft, [])
            if allowed_cats:
                filtered_food = food_df[food_df["RestaurantCategory"].isin(allowed_cats)]
                if not filtered_food.empty: food_df = filtered_food
        food_df['has_img'] = food_df['ThumbnailURL'].apply(lambda x: 1 if x and str(x) != 'nan' and x != "" else 0)
        recommended_restaurants = food_df.sort_values(by='has_img', ascending=False).head(9).to_dict('records')

    # --- 住宿篩選 ---
    if 'accommodation' in content_types:
        filtered_hotel_df = hotel_df.copy()
        if accommodation_types:
            allowed_keywords = []
            for t in accommodation_types:
                allowed_keywords += ACCOMMODATION_TYPE_MAPPING.get(t, [])
            mask = filtered_hotel_df["HotelName"].astype(str).apply(lambda name: any(kw in name for kw in allowed_keywords))
            filtered_hotel_df = filtered_hotel_df[mask]
        filtered_hotel_df['has_img'] = filtered_hotel_df["ThumbnailURL"].apply(lambda x: 1 if x and str(x) != 'nan' and x != "" else 0)
        recommended_hotels = filtered_hotel_df.sort_values(by='has_img', ascending=False).head(50).to_dict('records')

    return render_template('member/recommend.html', attractions=recommended_attractions, restaurants=recommended_restaurants, hotels=recommended_hotels)

@member_bp.route('/preferences', methods=['GET', 'POST'])
@login_required
def preferences():
    if request.method == 'POST':
        preferences_data = {
            "content_types": request.form.getlist("content_types"),
            "attraction_types": request.form.getlist("attraction_types"),
            "accommodation_types": request.form.getlist("accommodation_types"),
            "food_types": request.form.getlist("food_types"),
            "travel_pace": request.form.get("travel_pace")
        }
        session["preferences"] = preferences_data
        session.modified = True
        flash('偏好已更新！', 'success')
        return redirect(url_for('member.recommend'))
    return render_template('member/preferences.html', preferences=session.get("preferences", {}))

# --- 收藏功能 ---
@member_bp.route('/favorites/add', methods=['POST'])
@login_required
def add_favorite():
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    category, item_id, name = request.form.get('category'), request.form.get('item_id'), request.form.get('name')
    
    if not category or not item_id or not name:
        return jsonify({'status': 'error', 'message': '資料不完整'}) if is_ajax else redirect(request.referrer)

    existed = Favorite.query.filter_by(user_id=current_user.id, item_id=item_id, category=category).first()
    if not existed:
        favorite = Favorite(
            user_id=current_user.id, item_id=item_id, category=category,
            name=name, image_url=request.form.get('image_url'), location=request.form.get('location')
        )
        db.session.add(favorite)
        db.session.commit()
    
    return jsonify({'status': 'success'}) if is_ajax else redirect(url_for('member.favorites'))

@member_bp.route('/favorites')
@login_required
def favorites():
    page = request.args.get('page', 1, type=int)
    category_filter = request.args.get('category', 'all')
    base_query = Favorite.query.filter_by(user_id=current_user.id).order_by(Favorite.created_at.desc())
    
    counts = {
        'all': base_query.count(),
        'attractions': base_query.filter_by(category='景點').count(),
        'events': base_query.filter_by(category='活動').count(),
        'hotels': base_query.filter_by(category='住宿').count(),
        'restaurants': base_query.filter_by(category='餐廳').count()
    }

    if category_filter != 'all':
        mapping = {'attractions': '景點', 'events': '活動', 'hotels': '住宿', 'restaurants': '餐廳'}
        base_query = base_query.filter_by(category=mapping.get(category_filter))

    pagination = base_query.paginate(page=page, per_page=15, error_out=False)
    itineraries = Itinerary.query.filter_by(user_id=current_user.id).order_by(Itinerary.created_at.desc()).all()

    return render_template('member/favorites.html', favorites=pagination.items, pagination=pagination, counts=counts, current_category=category_filter, itineraries=itineraries)

@member_bp.route('/favorites/remove/<int:fav_id>', methods=['POST'])
@login_required
def remove_favorite(fav_id):
    fav = Favorite.query.filter_by(id=fav_id, user_id=current_user.id).first()
    if fav:
        db.session.delete(fav)
        db.session.commit()
    return redirect(url_for('member.favorites'))

# --- 行程與分享功能 ---
@member_bp.route('/schedule')
@login_required
def schedule():
    itineraries = Itinerary.query.filter_by(user_id=current_user.id).order_by(Itinerary.created_at.desc()).all()
    return render_template('member/schedule.html', itineraries=itineraries, notes=session.get('itinerary_notes', {}))


# --- 行程管理 ---
@member_bp.route('/schedule/create', methods=['POST'])
@login_required
def create_itinerary():
    title = request.form.get('title')
    # 接收日期字串並轉為 Python date 物件
    start_date_str = request.form.get('start_date')
    end_date_str = request.form.get('end_date')
    
    if title and start_date_str and end_date_str:
        # 將字串轉換為 date 物件 (格式 YYYY-MM-DD)
        try:
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
            flash('行程建立成功！', 'success')
        except ValueError:
            flash('日期格式錯誤', 'danger')
            
    return redirect(url_for('member.schedule'))

@member_bp.route('/schedule/note/<int:itinerary_id>', methods=['POST'])
@login_required
def save_itinerary_note(itinerary_id):
    data = request.get_json() or {}
    notes = session.get('itinerary_notes', {})
    notes[str(itinerary_id)] = data.get('note', '').strip()
    session['itinerary_notes'] = notes
    session.modified = True
    return jsonify({'status': 'success'})

@member_bp.route('/share/<int:itinerary_id>')
def share_itinerary(itinerary_id):
    plan = Itinerary.query.get_or_404(itinerary_id)
    total_days = (plan.end_date - plan.start_date).days + 1 if plan.start_date and plan.end_date else 1
    return render_template('member/share_itinerary.html', plan=plan, total_days=total_days, timedelta=timedelta)

@member_bp.route('/schedule/add_from_favorite/<int:fav_id>', methods=['POST'])
@login_required
def add_from_favorite(fav_id):
    fav = Favorite.query.filter_by(id=fav_id, user_id=current_user.id).first_or_404()
    itinerary_id = request.form.get('itinerary_id')
    if not itinerary_id:
        flash('請選擇行程', 'warning')
        return redirect(url_for('member.favorites'))

    itinerary = Itinerary.query.filter_by(id=itinerary_id, user_id=current_user.id).first_or_404()
    existed = ItineraryDetail.query.filter_by(itinerary_id=itinerary.id, item_id=fav.item_id, category=fav.category).first()
    
    if not existed:
        last_item = ItineraryDetail.query.filter_by(itinerary_id=itinerary.id, day_number=0).order_by(ItineraryDetail.sort_order.desc()).first()
        new_detail = ItineraryDetail(
            itinerary_id=itinerary.id, item_id=fav.item_id, name=fav.name, category=fav.category,
            image_url=fav.image_url, location=fav.location, day_number=0, sort_order=(last_item.sort_order + 1 if last_item else 1)
        )
        db.session.add(new_detail)
        db.session.commit()
        flash(f'已加入 {itinerary.title}', 'success')
    else:
        flash('已在行程中', 'info')
    return redirect(url_for('member.schedule'))

# --- 編輯行程 (拖曳排序相關) ---
@member_bp.route('/schedule/edit/<int:itinerary_id>')
@login_required
def edit_schedule(itinerary_id):
    plan = Itinerary.query.get_or_404(itinerary_id)
    if plan.user_id != current_user.id: return "權限不足", 403
    total_days = (plan.end_date - plan.start_date).days + 1 if plan.start_date and plan.end_date else 1
    return render_template('member/edit_schedule.html', plan=plan, timedelta=timedelta, total_days=total_days)

@member_bp.route('/schedule/save_all', methods=['POST'])
@login_required
def save_all_schedule():
    data = request.get_json()
    try:
        for item in data.get('items', []):
            detail = ItineraryDetail.query.get(int(item['id']))
            if detail and detail.itinerary.user_id == current_user.id:
                detail.day_number = int(item['day_number'])
                detail.sort_order = int(item['sort_order'])
                detail.start_time = item.get('start_time')
                detail.end_time = item.get('end_time')
        db.session.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@member_bp.route('/schedule/delete/<int:itinerary_id>', methods=['POST'])
@login_required
def delete_itinerary(itinerary_id):
    plan = Itinerary.query.filter_by(id=itinerary_id, user_id=current_user.id).first_or_404()
    db.session.delete(plan)
    db.session.commit()
    return jsonify({'status': 'success'})

@member_bp.route('/schedule/map/<int:itinerary_id>')
@login_required
def schedule_map(itinerary_id):
    plan = Itinerary.query.filter_by(id=itinerary_id, user_id=current_user.id).first_or_404()
    daily_routes = {}
    
    def get_coords(item_id, category):
        df_map = {'景點': attraction_df, '餐飲': restaurant_df, '餐廳': restaurant_df, '住宿': hotel_df, '活動': event_df}
        id_col_map = {'景點': 'AttractionID', '餐飲': 'RestaurantID', '餐廳': 'RestaurantID', '住宿': 'HotelID', '活動': 'EventID'}
        df = df_map.get(category)
        if df is not None:
            row = df[df[id_col_map[category]].astype(str) == str(item_id)]
            if not row.empty:
                lat = row.iloc[0].get('Lat') or row.iloc[0].get('PositionLat')
                lon = row.iloc[0].get('Lon') or row.iloc[0].get('PositionLon')
                return lat, lon
        return None, None

    for detail in sorted(plan.details, key=lambda x: (x.day_number, x.start_time or '00:00')):
        if detail.day_number == 0: continue
        lat, lng = get_coords(detail.item_id, detail.category)
        if lat and lng and not pd.isna(lat):
            daily_routes.setdefault(detail.day_number, []).append({
                'name': detail.name, 'lat': float(lat), 'lng': float(lng),
                'time': f"{detail.start_time} - {detail.end_time}", 'category': detail.category
            })
    return render_template('member/schedule_map.html', plan=plan, daily_routes=daily_routes)