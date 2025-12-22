from .extensions import db
from flask_login import UserMixin
from datetime import datetime

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

    favorites = db.relationship('Favorite', backref='user', lazy=True)

    def __repr__(self):
        return f'<User {self.username}>'
    
class Favorite(db.Model):
    __tablename__ = 'favorites' # 建議明確定義表名，保持風格一致
    
    id = db.Column(db.Integer, primary_key=True)
    
    # ⭐️ 修正這裡：要對應 User 的 __tablename__ ('users')
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # 儲存景點/活動的原始 ID 和類別
    item_id = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False) 
    
    # 快照資訊
    name = db.Column(db.String(255), nullable=False)
    image_url = db.Column(db.Text)
    location = db.Column(db.String(100))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Favorite {self.name}>'
    
class CartItem(db.Model):
    __tablename__ = 'cart_items'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    item_id = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50))
    name = db.Column(db.String(255), nullable=False)
    image_url = db.Column(db.Text)
    location = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Itinerary(db.Model):
    __tablename__ = 'itineraries'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)   
    title = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    details = db.relationship('ItineraryDetail', backref='itinerary', lazy=True, cascade="all, delete-orphan")

class ItineraryDetail(db.Model):
    __tablename__ = 'itinerary_details'
    id = db.Column(db.Integer, primary_key=True)
    itinerary_id = db.Column(db.Integer, db.ForeignKey('itineraries.id'), nullable=False)
    day_number = db.Column(db.Integer, default=1)
    item_id = db.Column(db.String(100))
    name = db.Column(db.String(255))
    category = db.Column(db.String(50))
    image_url = db.Column(db.Text)
    location = db.Column(db.String(100))
    sort_order = db.Column(db.Integer, default=0)
    start_time = db.Column(db.String(10)) # 例如 "09:00"
    end_time = db.Column(db.String(10))   # 例如 "11:30"