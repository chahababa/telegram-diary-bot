"""歷史日記頁面：查看 AI 日記、問卷回答、心情分數"""

import sys
import os
from datetime import date
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from bot.db import supabase_client as db


def render():
    st.header("📖 歷史日記")

    # 日期選擇器
    selected_date = st.date_input("選擇日期", value=date.today())
    date_str = selected_date.strftime("%Y-%m-%d")

    # 讀取 summary
    summary = db.get_summary(date_str)

    if not summary:
        st.info(f"📭 {date_str} 尚未有日記資料。")
        return

    # 心情分數
    mood = summary.get("mood_score")
    score_labels = {-2: "😢 很差", -1: "😕 不太好", 0: "😐 普通", 1: "🙂 不錯", 2: "😄 很好"}

    col1, col2 = st.columns(2)
    col1.metric("🎭 心情分數", score_labels.get(mood, "未設定") if mood is not None else "未設定")
    col2.metric("☁️ 上傳狀態", "✅ 已上傳" if summary.get("diary_uploaded") else "⬜ 未上傳")

    # 問卷回答
    answers = summary.get("questionnaire_answers", {}) or {}
    if answers:
        st.subheader("📋 問卷回答")
        for key, value in answers.items():
            if isinstance(value, list):
                st.markdown(f"**{key}**：{', '.join(str(v) for v in value)}")
            else:
                st.markdown(f"**{key}**：{value}")

    # AI 日記
    st.subheader("📖 AI 日記")
    diary = summary.get("diary_output")
    if diary:
        st.markdown(diary)
    else:
        st.info("尚未產出日記。")
