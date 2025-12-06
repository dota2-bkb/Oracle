import streamlit as st
from database import init_db
from views import input_page, match_list, analysis_page, settings_page, player_manager, patch_page

# Page Config
st.set_page_config(
    page_title="DOTA2 Analyst Tool",
    page_icon="🎮",
    layout="wide"
)

# Initialize DB
try:
    init_db()
except Exception as e:
    st.error(f"Database initialization failed: {e}")

def main():
    st.sidebar.title("DOTA2 Analyst Tool")
    
    pages = {
        "数据录入 (Input)": input_page,
        "比赛列表 (Match List)": match_list,
        "统计分析 (Analysis)": analysis_page,
        "选手管理 (Players)": player_manager,
        "版本管理 (Patches)": patch_page,
        "系统设置 (Settings)": settings_page
    }
    
    selection = st.sidebar.radio("导航 (Navigation)", list(pages.keys()))
    
    page = pages[selection]
    page.show()

if __name__ == "__main__":
    main()

