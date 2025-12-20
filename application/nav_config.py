# application/nav_config.py

SIDEBAR_ITEMS = [
    # --- 第一區塊：Dashboard ---
    {
        "type": "header", 
        "label": "Dashboard"
    },
    {
        "type": "link", 
        "label": "數據總覽", 
        "href": "/dashboard/overview", 
        "icon": "📊 "
    },
    {
        "type": "link", 
        "label": "行程查詢", 
        "href": "/dashboard/planner", 
        "icon": "🗺️ "
    },
    {
        "type": "link", 
        "label": "景點地圖", 
        "href": "/dashboard/attractions", 
        "icon": "🎡 "
    },
    
    # --- 第二區塊：會員專區 ---
    {
        "type": "header", 
        "label": "會員專區", 
        "margin_top": True
    },
    {
        "type": "link", 
        "label": "個人偏好設定", 
        "href": "/member/preferences", 
        "icon": "👤 "
    },
    {
        "type": "link", 
        "label": "我的收藏行程", 
        "href": "/member/favorites", 
        "icon": "❤️ "
    },
    {
        "type": "link", 
        "label": "行程排程管理", 
        "href": "/member/schedule", 
        "icon": "📅 "
    },
]