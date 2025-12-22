# application/utils/theme.py

# --- 🎨 SlowDays 主題配色定義 ---
THEME = {
    'primary': '#FFA97F',       # 主色 (按鈕、Header、Tab 選中) - 暖橘
    'secondary': '#FFE2CF',     # 次要色 (Tab 未選中、Header 背景) - 淺桃
    'background': '#FFF7F2',    # 網頁背景 - 極淺粉白
    'card_bg': '#FFFFFF',       # 卡片/區塊背景 - 純白
    'text': '#3C3C3C',          # 主要文字 - 深灰
    'accent': '#FFD1B3',        # 裝飾色
    'danger': '#FF6347',        # 錯誤/警告紅
    'muted': '#999999'          # 弱化文字
}

# --- Tab 分頁樣式 ---
TAB_STYLE = {
    'idle': {
        'padding': '12px',
        'fontWeight': 'bold',
        'backgroundColor': THEME['secondary'],
        'color': THEME['text'],
        'border': 'none',
        'borderRadius': '10px 10px 0 0',
        'marginRight': '5px',
        'cursor': 'pointer'
    },
    'active': {
        'padding': '12px',
        'fontWeight': 'bold',
        'backgroundColor': THEME['primary'],
        'color': 'white', 
        'border': 'none',
        'borderRadius': '10px 10px 0 0',
        'borderBottom': f'3px solid {THEME["text"]}', 
        'marginRight': '5px',
        'cursor': 'pointer'
    }
}

# --- 圖表共用樣式 (可選，讓你的程式碼更乾淨) ---
GRAPH_STYLE = {
    'paper_bgcolor': THEME['background'],
    'plot_bgcolor': THEME['background'],
    'font': {'color': THEME['text']}
}

# --- 側邊欄與內容區塊樣式 ---
SIDEBAR_STYLE = {
    "position": "fixed",
    "top": "70px",          # 預留 Header 的高度
    "left": 0,
    "bottom": 0,
    "width": "16rem",       # 側邊欄寬度
    "padding": "2rem 1rem", # 內距
    "backgroundColor": "#FFFFFF", # 白底
    "boxShadow": "2px 0 5px rgba(0,0,0,0.05)", # 右側陰影
    "overflowY": "auto",    # 內容太長時可捲動
    "zIndex": 50            # 確保在內容之上
}

CONTENT_STYLE = {
    "marginLeft": "16rem",  # 左邊留給 Sidebar
    "marginRight": "0",
    "padding": "2rem",      # 內距
    "paddingTop": "100px",  # ⭐️ 關鍵修正：上方留白加大 (原本可能是 2rem，改成 100px 避開 Header)
    "transition": "margin-left .3s",
}