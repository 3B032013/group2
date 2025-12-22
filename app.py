# app.py
from application import create_app

# 呼叫 application/__init__.py 裡面的 create_app 函式
app = create_app()

if __name__ == '__main__':
    # 這裡啟動 server，Debug 模式可開啟方便除錯
    app.run(debug=True, port=8000)