"""
Web 儀錶板路由 — 使用 Flask 提供管理介面
與 Telegram Bot 跑在同一個 process（背景執行緒）
"""

import time
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, request

import config
from services.settings_service import (
    get_gcal_calendar_id,
    get_google_drive_folder_id,
    get_gpt_model,
    get_timezone_name,
)

logger = logging.getLogger(__name__)

# 記錄 Flask 啟動時間（近似 Bot 啟動時間）
_start_time = time.time()


def create_flask_app() -> Flask:
    """建立並設定 Flask 應用程式"""
    app = Flask(__name__)
    app.json.ensure_ascii = False  # 讓 JSON 回傳正體中文，不轉義

    # ── 前端頁面 ──────────────────────────────────────────

    @app.route('/')
    def index():
        html_path = Path(__file__).parent / 'dashboard.html'
        content = html_path.read_text(encoding='utf-8')
        return content, 200, {'Content-Type': 'text/html; charset=utf-8'}

    # ── API：Bot 狀態 ─────────────────────────────────────

    @app.route('/api/status')
    def api_status():
        from models.database import _get_db
        db = _get_db()
        tz = ZoneInfo(get_timezone_name())
        today = datetime.now(tz).strftime('%Y-%m-%d')

        user_ids = db.get_all_user_ids()
        today_entries = sum(
            db.get_entry_count_by_date(uid, today) for uid in user_ids
        )

        with db._get_conn() as conn:
            total_diaries = conn.execute(
                'SELECT COUNT(*) AS cnt FROM generated_diaries'
            ).fetchone()['cnt']
            total_entries = conn.execute(
                'SELECT COUNT(*) AS cnt FROM entries'
            ).fetchone()['cnt']

        # Google Drive 狀態
        try:
            from services.gdrive_service import is_available as gdrive_is_available
            gdrive_ok = gdrive_is_available()
        except Exception:
            gdrive_ok = False

        gcal_ok = bool(get_gcal_calendar_id())

        uptime = int(time.time() - _start_time)

        return jsonify({
            'running': True,
            'uptime_seconds': uptime,
            'start_time': datetime.fromtimestamp(_start_time, tz=tz).isoformat(),
            'today': today,
            'today_entries': today_entries,
            'total_entries': total_entries,
            'total_diaries': total_diaries,
            'user_count': len(user_ids),
            'gdrive_available': gdrive_ok,
            'gcal_available': gcal_ok,
        })

    # ── API：設定讀取 ─────────────────────────────────────

    @app.route('/api/settings', methods=['GET'])
    def api_get_settings():
        from models.database import _get_db
        db = _get_db()

        reminder_hours_raw = db.get_setting('reminder_hours', '')
        if not reminder_hours_raw:
            reminder_hours_raw = ','.join(str(h) for h in config.REMINDER_HOURS)

        return jsonify({
            'reminder_hours': reminder_hours_raw,
            'survey_hour': db.get_setting('survey_hour', str(config.SURVEY_HOUR)),
            'diary_generation_hour': db.get_setting(
                'diary_generation_hour', str(config.DIARY_GENERATION_HOUR)
            ),
            'gpt_model': get_gpt_model(),
            'timezone': get_timezone_name(),
            'gcal_calendar_id': get_gcal_calendar_id(),
            'google_drive_folder_id': get_google_drive_folder_id(),
            'diary_template': db.get_setting('diary_template', ''),
        })

    # ── API：設定更新 ─────────────────────────────────────

    @app.route('/api/settings', methods=['POST'])
    def api_update_settings():
        from models.database import _get_db
        db = _get_db()
        data = request.get_json()

        if not data:
            return jsonify({'success': False, 'error': '無效的請求'}), 400

        allowed_keys = {
            'reminder_hours', 'survey_hour', 'diary_generation_hour',
            'gpt_model', 'timezone', 'gcal_calendar_id',
            'google_drive_folder_id', 'diary_template',
        }

        updated = []
        for key, value in data.items():
            if key in allowed_keys:
                db.set_setting(key, str(value))
                updated.append(key)

        logger.info(f'Web 儀錶板更新設定: {updated}')
        return jsonify({'success': True, 'updated': updated})

    # ── API：心情趨勢 ─────────────────────────────────────

    @app.route('/api/mood')
    def api_mood():
        from models.database import _get_db
        db = _get_db()
        days = min(int(request.args.get('days', 7)), 30)

        user_ids = db.get_all_user_ids()
        if not user_ids:
            return jsonify([])

        # 彙整所有使用者的心情分數（按日期取平均）
        all_moods: dict[str, list[float]] = {}
        for uid in user_ids:
            scores = db.get_mood_scores(uid, days)
            for s in scores:
                d = s['diary_date']
                score = s['mood_score']
                if score is not None:
                    all_moods.setdefault(d, []).append(float(score))

        result = [
            {
                'diary_date': d,
                'mood_score': round(sum(v) / len(v), 1),
            }
            for d, v in sorted(all_moods.items())
        ]

        return jsonify(result[-days:])

    return app
