"""歷史紀錄頁面：查看每日 diary_entries"""

import sys
import os
from datetime import date
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from bot.db import supabase_client as db


def render():
    st.header("📝 歷史紀錄")

    # 日期選擇器
    selected_date = st.date_input("選擇日期", value=date.today())
    date_str = selected_date.strftime("%Y-%m-%d")

    # 讀取紀錄
    entries = db.get_entries_by_date(date_str)

    if not entries:
        st.info(f"📭 {date_str} 沒有任何紀錄。")
        return

    # 統計
    text_count = sum(1 for e in entries if e["source_type"] == "text")
    voice_count = sum(1 for e in entries if e["source_type"] == "voice")

    col1, col2, col3 = st.columns(3)
    col1.metric("總筆數", len(entries))
    col2.metric("📝 文字", text_count)
    col3.metric("🎤 語音", voice_count)

    st.divider()

    # 顯示紀錄
    for entry in entries:
        icon = "🎤" if entry["source_type"] == "voice" else "📝"
        time_str = entry["time"][:5]
        st.markdown(f"**{icon} [{time_str}]** {entry['content']}")
