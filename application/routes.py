# application/routes.py
from flask import Blueprint, render_template

# 建立 Blueprint
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login')
def login():
    # Flask 會自動去 application/templates 找這個檔案
    return render_template('login.html')

@auth_bp.route('/register')
def register():
    return render_template('register.html')