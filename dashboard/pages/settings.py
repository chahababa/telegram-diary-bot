"""設定頁面：提醒時段、問卷範本、GPT 模型、常用字管理"""

import sys
import os
import streamlit as st

# 讓 dashboard 能 import bot 模組
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from bot.db import supabase_client as db


def render():
    st.header("⚙️ 設定")

    # 讀取目前設定
    settings = db.get_settings()
    if not settings:
        st.error("無法讀取設定，請確認 Supabase 連線。")
        return

    # === 提醒時段 ===
    st.subheader("🔔 提醒時段")
    current_hours = settings.get("reminder_hours", [9, 12, 15, 18, 21])
    cols = st.columns(8)
    selected_hours = []
    for i in range(24):
        col = cols[i % 8]
        if col.checkbox(f"{i:02d}:00", value=(i in current_hours), key=f"hour_{i}"):
            selected_hours.append(i)

    # === 問卷觸發時間 ===
    st.subheader("📋 問卷與日記時間")
    col1, col2 = st.columns(2)
    questionnaire_hour = col1.selectbox(
        "問卷觸發時間",
        options=list(range(24)),
        index=settings.get("questionnaire_hour", 23),
        format_func=lambda x: f"{x:02d}:00",
    )
    diary_hour = col2.selectbox(
        "日記產出時間",
        options=list(range(24)),
        index=settings.get("diary_generation_hour", 0),
        format_func=lambda x: f"{x:02d}:00",
    )

    # === GPT 模型 ===
    st.subheader("🤖 GPT 模型")
    models = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]
    current_model = settings.get("gpt_model", "gpt-4o")
    model_index = models.index(current_model) if current_model in models else 0
    gpt_model = st.selectbox("選擇模型", models, index=model_index)

    # === 問卷範本 ===
    st.subheader("📋 問卷範本")
    template = settings.get("questionnaire_template", [])
    edited_template = st.data_editor(
        template,
        column_config={
            "key": st.column_config.TextColumn("Key（英文代號）", width="medium"),
            "question": st.column_config.TextColumn("問題內容", width="large"),
            "type": st.column_config.SelectboxColumn("類型", options=["text", "list", "score"], width="small"),
        },
        num_rows="dynamic",
        use_container_width=True,
    )

    # === 日記 Prompt 範本 ===
    st.subheader("📝 日記 Prompt 範本")
    current_prompt = settings.get("diary_prompt_template", "")
    diary_prompt = st.text_area(
        "Prompt 範本（留空則使用預設）",
        value=current_prompt if current_prompt else "",
        height=200,
    )

    # === 常用字管理 ===
    st.subheader("🗣️ 常用字（語音辨識用）")
    st.caption("輸入你的常用詞彙（人名、地名、店名等），Whisper 語音辨識時會優先往這些字靠。")
    current_vocab = settings.get("custom_vocabulary") or []

    # 顯示目前的常用字清單
    vocab_text = st.text_area(
        "每行一個詞彙",
        value="\n".join(current_vocab),
        height=150,
        placeholder="例如：\n曉明\n雅庭\n好初早餐\n板橋",
    )
    # 解析文字為清單
    new_vocab = [w.strip() for w in vocab_text.split("\n") if w.strip()]

    # === 儲存按鈕 ===
    st.divider()
    if st.button("💾 儲存設定", type="primary", use_container_width=True):
        update_data = {
            "reminder_hours": selected_hours,
            "questionnaire_hour": questionnaire_hour,
            "diary_generation_hour": diary_hour,
            "gpt_model": gpt_model,
            "questionnaire_template": edited_template,
            "diary_prompt_template": diary_prompt if diary_prompt else None,
            "custom_vocabulary": new_vocab,
        }
        try:
            client = db.get_client()
            client.table("bot_settings").update(update_data).eq("id", 1).execute()
            st.success("✅ 設定已儲存！Bot 會在下次排程檢查時讀取新設定。")
        except Exception as e:
            st.error(f"❌ 儲存失敗：{e}")
