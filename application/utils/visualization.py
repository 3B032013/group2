import plotly.graph_objects as go
import numpy as np
import pandas as pd
from dash import html, dash_table
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.colors as colors
from .data_validation import fmt
import plotly.express as px
from typing import Literal

def build_compare_figure(df_result, chart_type, title):
    metric_columns = [col for col in df_result.columns if col != 'Country']
    fig = go.Figure()

    if not metric_columns:
        fig.update_layout(
            template='plotly_dark', font=dict(color='#deb522'), title=title,
            annotations=[dict(text='沒有可比較的指標', x=0.5, y=0.5, showarrow=False, font=dict(color='#deb522'))]
        )
        return fig

    df_numeric = df_result.copy()
    for col in metric_columns:
        df_numeric[col] = pd.to_numeric(df_numeric[col], errors='coerce')

    if chart_type == 'radar':
        df_normalized = df_numeric.copy()
        for col in metric_columns:
            series = df_numeric[col]
            if series.dropna().empty:
                df_normalized[col] = np.nan
                continue
            min_val, max_val = series.min(), series.max()
            if max_val > min_val:
                df_normalized[col] = 100 * (series - min_val) / (max_val - min_val)
            else:
                df_normalized[col] = 50

        for _, row in df_normalized.iterrows():
            values = [row[col] if pd.notna(row[col]) else 0 for col in metric_columns]
            if values:
                values.append(values[0])
            theta = metric_columns + [metric_columns[0]] if metric_columns else metric_columns
            fig.add_trace(go.Scatterpolar(r=values, theta=theta, fill='toself', name=row['Country']))

        fig.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
            template='plotly_dark', font=dict(color='#deb522'), title=title, height=600
        )

    elif chart_type == 'bar':
        for col in metric_columns:
            fig.add_trace(go.Bar(
                name=col, x=df_result['Country'], y=df_numeric[col],
                text=df_numeric[col].round(2), textposition='auto'
            ))
        fig.update_layout(
            barmode='group', template='plotly_dark', font=dict(color='#deb522'), title=title,
            xaxis_title='Country', yaxis_title='Value', height=600
        )

    else:  # line
        for col in metric_columns:
            fig.add_trace(go.Scatter(
                x=df_result['Country'], y=df_numeric[col], mode='lines+markers+text',
                name=col, text=df_numeric[col].round(2), textposition='top center'
            ))
        fig.update_layout(
            template='plotly_dark', font=dict(color='#deb522'), title=title,
            xaxis_title='Country', yaxis_title='Value', height=600
        )

    return fig

def generate_stats_card(title, value, icon_path):
    """
    生成現代風格的數據統計卡片 (Modern Stat Card)
    """
    return dbc.Card(
        dbc.CardBody([
            # 1. 版面配置：圖示在右，數據在左
            html.Div([
                # 左側：數據與標題
                html.Div([
                    html.H3(
                        f"{value:,}",  # 自動加千分位逗號 (例如 1,524)
                        style={
                            'color': '#FFA97F', # 主色 (暖橘)
                            'fontWeight': 'bold',
                            'fontSize': '32px',
                            'marginBottom': '0px'
                        }
                    ),
                    html.P(
                        title,
                        style={
                            'color': '#888888', # 標題用灰色，不搶眼
                            'fontSize': '15px',
                            'fontWeight': '500',
                            'marginBottom': '0'
                        }
                    ),
                ]),
                
                # 右側：圖示 (加上淡色背景圓圈，更精緻)
                html.Div([
                    html.Img(src=icon_path, style={'height': '32px', 'width': '32px'})
                ], style={
                    'backgroundColor': '#FFF0E6', # 極淺的橘色背景
                    'borderRadius': '50%',        # 圓形
                    'width': '60px',
                    'height': '60px',
                    'display': 'flex',
                    'alignItems': 'center',
                    'justifyContent': 'center'
                })
            ], style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center'})
        ]),
        style={
            'border': 'none',                 # 去除邊框
            'borderRadius': '16px',           # 較大的圓角
            'backgroundColor': 'white',       # 白底
            'boxShadow': '0 4px 20px rgba(0,0,0,0.05)', # 質感陰影 (浮起來的感覺)
            'cursor': 'default',
            'transition': 'transform 0.2s',   # (選用) 滑鼠移過去微微上浮
        },
        className="mb-4" # Bootstrap margin-bottom
    )

def build_table_component(out):
    """整理欄位格式與樣式，輸出 Dash DataTable 元件"""
    shown_cols = [
        'Country', 'Score', 'Safety Index', 'Travel Alert', 'CPI', 'PCE', 'Visa_exempt_entry',
        'trips', 'median_daily_acc_cost', 'adj_daily_acc_cost', 'median_trip_acc_cost'
    ]
    available_cols = [c for c in shown_cols if c in out.columns]
    out_display = out[available_cols].copy()

    # 格式化分數與金額
    if 'Score' in out_display:
        out_display['Score'] = out_display['Score'].apply(lambda v: fmt(v, 0))
    for c in ['median_daily_acc_cost', 'adj_daily_acc_cost', 'median_trip_acc_cost']:
        if c in out_display:
            out_display[c] = out_display[c].apply(lambda v: fmt(v, 0))

    table = dash_table.DataTable(
        data=out_display.to_dict('records'),
        page_size=10,
        export_format='csv',
        sort_action='native',
        filter_action='native',
        style_data={'backgroundColor': '#deb522', 'color': 'black'},
        style_header={'backgroundColor': 'black', 'color': '#deb522', 'fontWeight': 'bold'},
        style_table={'overflowX': 'auto'},
        columns=[{'name': col, 'id': col} for col in available_cols]
    )
    return table    


# 長條圖
def generate_bar(df: pd.DataFrame, dropdown_value: str):
    if not dropdown_value:
        fig_bar = px.bar(title="請選擇有效的選項")
        fig_bar.update_layout(template='plotly_dark', font=dict(color='#deb522'))
        return fig_bar

    # --- 1. 過濾資料 (包含縣市或鄉鎮) ---
    df_group = df[
        (df['PostalAddress.City'] == dropdown_value) | 
        (df['PostalAddress.Town'] == dropdown_value)
    ].copy() 

    if df_group.empty:
        fig_bar = px.bar(title=f"在 {dropdown_value} 找不到活動數據")
        fig_bar.update_layout(template='plotly_dark', font=dict(color='#deb522'))
        return fig_bar

    # --- 2. 提取月份並分組計數 (核心邏輯) ---
    # 創建排序欄位：使用數字前綴確保排序正確 (例如 '01 - Jan')
    df_group['Start month'] = df_group['StartDateTime'].dt.strftime('%m - %b')
    
    # 分組計數
    month_counts_series = df_group.groupby('Start month')['EventID'].count()
    
    # 關鍵步驟：定義 1-12 月的完整格式，用於 reindex
    full_month_order = [pd.to_datetime(f'2025-{m}-01').strftime('%m - %b') for m in range(1, 13)]
    
    # 確保顯示 1 月到 12 月：使用 reindex 補齊數據為 0 的月份
    month_counts = month_counts_series.reindex(full_month_order, fill_value=0).reset_index()
    month_counts.columns = ['Start month', 'Count'] # 統一欄位名稱

    # --- 3. 計算百分比 ---
    total_count = month_counts['Count'].sum()
    month_counts['Percentage'] = (month_counts['Count'] / total_count) * 100

    # --- 4. 繪製長條圖 ---
    # 移除衝突的排序邏輯，直接依賴 '01 - Jan' 格式和 Plotly 的 categoryorder
    
    fig_bar = px.bar(
        month_counts, 
        x='Start month', 
        y='Count', # 使用統一的 'Count' 欄位名稱
        color='Count', 
        text='Percentage',
        title=f'{dropdown_value} - 各月份活動數量分佈', # 修正標題
        labels={'Count': '活動數量', 'Start month': '月份', 'Percentage': '百分比'},
        color_continuous_scale='Viridis'
    )
    
    # --- 5. 更新樣式和排序 ---
    fig_bar.update_traces(texttemplate='%{text:.2f}%', textposition='outside')
    
    # 使用 categoryorder='array' 並傳遞我們定義的完整月份順序
    fig_bar.update_layout(
        template='plotly_dark', 
        font=dict(color='#deb522'),
        # 依賴 full_month_order 確保 1-12 月的順序正確
        xaxis={'categoryorder':'array', 'categoryarray': full_month_order} 
    )

    return fig_bar

def generate_pie(df: pd.DataFrame, dropdown_value_1: str, dropdown_value_2: str):
    """
    生成活動類別分佈圓餅圖，自動將子類別歸併到主類別中，
    並處理多重分類的活動。

    Args:
        df: 活動數據 DataFrame (event_df)。
        dropdown_value_1: 縣市或鄉鎮的選擇值。
        dropdown_value_2: 分類欄位名稱 (應為 'EventCategoryNames')。
    """
    
    if not dropdown_value_1 or not dropdown_value_2:
        # 回傳一個空的圖表，或在這裡設置一個預設訊息
        fig_pie = px.pie(title="請選擇有效的縣市/鄉鎮與分類欄位")
        fig_pie.update_layout(template='plotly_dark', font=dict(color='#deb522'))
        return fig_pie
    
    # 1. 過濾出符合縣市/鄉鎮的資料
    # 確保篩選包含 City 或 Town
    df_group = df[(df['PostalAddress.City'] == dropdown_value_1) | 
                  (df['PostalAddress.Town'] == dropdown_value_1)].copy()
    
    if df_group.empty:
        fig_pie = px.pie(title=f"在 {dropdown_value_1} 找不到活動數據")
        fig_pie.update_layout(template='plotly_dark', font=dict(color='#deb522'))
        return fig_pie

    # --- 2. 類別拆分、歸併與計數 (核心修正邏輯) ---
    
    # 假設類別以 ", " 分隔 (請根據您的實際數據確認分隔符)
    category_separator = ', '
    
    # 關鍵步驟 A: 拆分並攤平多個類別
    # 確保欄位是字串，並用分隔符號拆分，然後將列表中的每個元素展開成獨立的行
    category_series = df_group[dropdown_value_2].astype(str).str.split(category_separator).explode()
    category_series = category_series.str.strip() # 清理多餘空格

    # 關鍵步驟 B: 定義映射函式
    def map_to_primary_category(category_name):
        """將子類別名稱歸併到其主類別名稱。"""
        if not category_name or category_name == 'nan':
            return '其他' # 將無效或空的類別歸為「其他」
        
        PRIMARY_CATEGORIES = [
            "節慶活動",
            "藝文活動",
            "年度活動",
            "遊憩活動",
            "地方社區型活動",
            "其他活動（Other）"
        ]
        
        # 檢查字串是否以任何一個主類別開頭
        for primary in PRIMARY_CATEGORIES:
            if category_name.startswith(primary):
                return primary # 找到主類別就回傳主類別名稱
        
        # 如果不屬於任何已知主類別
        return '其他'

    # 關鍵步驟 C: 應用映射，進行數據降級
    category_series_reduced = category_series.apply(map_to_primary_category)

    # 關鍵步驟 D: 對歸併後的 Series 進行計數
    category_counts = category_series_reduced.value_counts().reset_index(name='count')
    category_counts.columns = ['CategoryName', 'count'] # 使用固定名稱方便繪圖

    # 過濾掉可能存在的 'nan' 或空字串計數（儘管在 map_to_primary_category 中已經處理）
    df_counts = category_counts[category_counts['CategoryName'] != 'nan']
    
    # --- 3. 建立圓餅圖 ---
    fig_pie = px.pie(
        df_counts, 
        names='CategoryName',      # 圓餅圖的標籤欄位使用歸併後的主類別
        values='count',            # 圓餅圖的數值欄位
        title=f'{dropdown_value_1} - 活動主類別分佈', 
        hole=0.3, # 甜甜圈圖
        color_discrete_sequence=px.colors.sequential.YlOrRd # 使用色板
    )
        
    # 更新圖表樣式
    fig_pie.update_layout(
        template='plotly_dark', 
        font=dict(color='#deb522'),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)'
    )
    
    # 顯示百分比和標籤
    fig_pie.update_traces(textinfo='percent+label')

    return fig_pie

def generate_map(df: pd.DataFrame, city: str, color_by_column: str):
    """
    生成景點地圖（Scatter Mapbox），顯示經緯度點位分佈。
    
    Args:
        df: 已經過縣市/鄉鎮篩選的景點 DataFrame (attraction_df)。
        city: 用於圖表標題的縣市名稱（例如：'臺北市'）。
        color_by_column: 用於決定地圖上點顏色的欄位名稱（例如 'AttractionCategory'）。
    """
    
    # ⭐️ 最佳實踐：明確複製 DataFrame 以避免 SettingWithCopyWarning
    df_plot = df.copy() 

    # 確保有數據且有經緯度欄位
    if df_plot.empty or 'Lat' not in df_plot.columns or 'Lon' not in df_plot.columns:
        fig = px.scatter_mapbox(title=f"景點地圖：無數據或數據錯誤")
        fig.update_layout(template='plotly_dark')
        return fig

    # 確保經緯度是數值型，以便計算中心點 (如果數據處理階段沒做)
    df_plot['Lat'] = pd.to_numeric(df_plot['Lat'], errors='coerce')
    df_plot['Lon'] = pd.to_numeric(df_plot['Lon'], errors='coerce')

    # 確保顏色欄位存在 (如果不存在，則預設使用類別)
    if color_by_column not in df_plot.columns:
        color_by_column = 'AttractionCategory' 
        
    # 創建懸停資訊 (Hover Text)
    df_plot['HoverText'] = (
        '<b>' + df_plot['AttractionName'] + '</b><br>' + 
        '分類: ' + df_plot[color_by_column].astype(str).fillna('N/A') + '<br>' +
        '費用摘要: ' + df_plot['FeesSummary'].fillna('無')
    )

    # 確定地圖中心點和縮放級別 (忽略 NaN 值)
    center_lat = df_plot['Lat'].mean(skipna=True)
    center_lon = df_plot['Lon'].mean(skipna=True)
    # 縮放級別：臺灣範圍約 6-7，單一縣市約 10-11
    zoom_level = 10 if city and city != '臺灣' else 6 
    
    # 如果中心點為 NaN (可能所有經緯度都是空)，則使用臺灣中心點
    if pd.isna(center_lat) or pd.isna(center_lon):
        center_lat, center_lon = 23.6, 120.9  # 臺灣大致中心點
        zoom_level = 6

    # 繪製地圖
    fig_map = px.scatter_mapbox(
        df_plot,
        lat="Lat",
        lon="Lon",
        color=color_by_column,  # 根據下拉選單選擇的欄位著色
        hover_name="AttractionName",
        hover_data={"HoverText": True, "Lat": False, "Lon": False, color_by_column: True}, # 自定義懸停顯示
        center={"lat": center_lat, "lon": center_lon}, 
        zoom=zoom_level, 
        mapbox_style="carto-positron", # 淺色地圖樣式，最穩定且免費
        title=f'{city} 景點分佈圖 - 按 {color_by_column} 分類',
        height=600
    )

    # 設置深色佈局
    fig_map.update_layout(
        # ⭐️ 關鍵修正：確保這裡使用免費樣式，並可以覆寫 px.scatter_mapbox 的設置
        mapbox_style="carto-darkmatter", # 另一個免費的深色樣式
        
        template='plotly_dark',
        font=dict(color='#FFFFFF'),
        margin={"r":0,"t":40,"l":0,"b":0},
        legend_title_text=color_by_column,
        # 統一所有地圖配置，避免衝突
        mapbox={
            "center": {"lat": center_lat, "lon": center_lon},
            "zoom": zoom_level,
        }
    )

    return fig_map

PRICE_COLUMN = 'LowestPrice' 
def generate_box(df: pd.DataFrame, geo: str | None, metric: str):
    # ⭐️ 確保使用副本操作
    df_plot = df.copy()

    # 1. 檢查必要的欄位和數據
    if df_plot.empty or PRICE_COLUMN not in df_plot.columns or metric not in df_plot.columns:
        # 這裡應該不會再跳出錯誤，除非 metric 欄位不存在
        fig_boxplot = px.box(title="數據不完整或價格欄位不存在")
        fig_boxplot.update_layout(template='plotly_dark')
        return fig_boxplot

    # 2. 確保價格欄位是數值類型，並去除無效價格的行
    # 將 LowestPrice 轉換為數值
    df_plot[PRICE_COLUMN] = pd.to_numeric(df_plot[PRICE_COLUMN], errors='coerce')
    
    # 移除價格為 NaN 或分類欄位為空值的行
    df_plot.dropna(subset=[PRICE_COLUMN, metric], inplace=True) 
    
    # 移除價格為 0 的資料，通常代表價格未填
    df_plot = df_plot[df_plot[PRICE_COLUMN] > 0]
    
    if df_plot.empty:
        fig_boxplot = px.box(title="無有效價格數據可供分析")
        fig_boxplot.update_layout(template='plotly_dark')
        return fig_boxplot
    
    # 3. 繪製箱型圖
    title_geo = geo if geo else "臺灣全區"
    title_text = f'{title_geo} 旅館價格分佈 (最低價) - 按 {metric} 分類'
    
    fig_boxplot = px.box(
        df_plot, 
        x=metric,            # X 軸：分類依據 (例如 HotelStarsName)
        y=PRICE_COLUMN,      # Y 軸：數值價格
        color=metric,        # 使用 metric 進行顏色區分
        hover_name="HotelName", 
        title=title_text
    )
    
    # 4. 設置深色佈局
    fig_boxplot.update_traces(marker=dict(color='#deb522'))
    fig_boxplot.update_layout(
        template='plotly_dark', 
        font=dict(color='#FFFFFF'),
        yaxis_title="每晚最低價格",
        xaxis_title=metric,
        showlegend=False # 如果 x 軸就是 color，可以關閉圖例
    )

    return fig_boxplot