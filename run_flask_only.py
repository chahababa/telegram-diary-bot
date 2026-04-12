"""
只啟動 Flask 儀錶板，不啟動 Telegram Bot。
用於測試 Web 介面是否正常運作。
"""
import sys
from pathlib import Path

# 確保可以 import 專案模組
sys.path.insert(0, str(Path(__file__).parent))

from web.routes import create_flask_app

if __name__ == "__main__":
    app = create_flask_app()
    print("Flask 儀錶板啟動中：http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
