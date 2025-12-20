from . import db
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