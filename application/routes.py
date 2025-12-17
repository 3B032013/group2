from flask import Blueprint, render_template, request, redirect, url_for

# ======================
# Auth Blueprint（原本的）
# ======================
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login')
def login():
    return render_template('login.html')

@auth_bp.route('/register')
def register():
    return render_template('register.html')


# ======================
# Member Blueprint（新增的）
# ======================
member_bp = Blueprint('member', __name__)

@member_bp.route('/member/preferences', methods=['GET', 'POST'])
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
def favorites():
    favorite_trips = [
        {"id": 1, "name": "金門慢活三日遊", "location": "金門縣", "days": 3},
        {"id": 2, "name": "台東藝文週末", "location": "台東縣", "days": 2},
    ]
    return render_template(
        'member/favorites.html',
        favorite_trips=favorite_trips
    )


@member_bp.route('/member/schedule')
def schedule():
    schedules = [
        {"date": "2025-04-03", "trip": "金門慢活三日遊"},
        {"date": "2025-06-20", "trip": "台東藝文週末"},
    ]
    return render_template(
        'member/schedule.html',
        schedules=schedules
    )
