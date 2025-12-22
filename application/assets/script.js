// application/assets/script.js

// 使用事件委派 (Event Delegation) 監聽 document
// 這樣可以確保 Dash 動態生成的按鈕也能被捕捉到
document.addEventListener('click', function(event) {
    
    // 檢查點擊的目標 (或是目標的父層) 是不是 #sidebar-toggle
    const toggleBtn = event.target.closest('#sidebar-toggle');

    if (toggleBtn) {
        // 切換 class
        document.body.classList.toggle('sidebar-collapsed');
        
        // 觸發視窗 resize 事件 (讓 Plotly 圖表重新計算寬度，不然圖表會跑版)
        setTimeout(() => {
            window.dispatchEvent(new Event('resize'));
        }, 300);

        // 記住狀態
        const isCollapsed = document.body.classList.contains('sidebar-collapsed');
        localStorage.setItem('sidebarState', isCollapsed ? 'collapsed' : 'expanded');
    }
});

// 頁面載入時恢復狀態
document.addEventListener('DOMContentLoaded', function() {
    const savedState = localStorage.getItem('sidebarState');
    if (savedState === 'collapsed') {
        document.body.classList.add('sidebar-collapsed');
    }
});