"""📔 日記助理管理後台 — Streamlit 入口"""

import streamlit as st

st.set_page_config(page_title="日記助理管理後台", page_icon="📔", layout="wide")

st.sidebar.title("📔 日記助理管理後台")
page = st.sidebar.radio("頁面導覽", ["⚙️ 設定", "📝 歷史紀錄", "📖 歷史日記"])

if page == "⚙️ 設定":
    from pages import settings
    settings.render()
elif page == "📝 歷史紀錄":
    from pages import entries
    entries.render()
elif page == "📖 歷史日記":
    from pages import diaries
    diaries.render()
