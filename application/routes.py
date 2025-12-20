from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from . import db
from .models import User, Favorite
from .nav_config import SIDEBAR_ITEMS

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
# Member Blueprint（新增的）
# ======================
member_bp = Blueprint('member', __name__)

@member_bp.context_processor
def inject_common_vars():
    return dict(sidebar_items=SIDEBAR_ITEMS)

@member_bp.route('/member/preferences', methods=['GET', 'POST'])
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

@member_bp.route('/member/favorites')
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

@member_bp.route('/member/schedule')
@login_required
def schedule():
    schedules = [
        {"date": "2025-04-03", "trip": "金門慢活三日遊"},
        {"date": "2025-06-20", "trip": "台東藝文週末"},
    ]
    return render_template(
        'member/schedule.html',
        schedules=schedules
    )
