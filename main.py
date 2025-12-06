import streamlit as st
from database import init_db
from views import input_page, match_list, analysis_page, settings_page, player_manager, patch_page, expert_mode

# Page Config
st.set_page_config(
    page_title="Sentry: DOTA2 分析工具",
    page_icon="🛡️",
    layout="wide"
)

# Initialize DB
try:
    init_db()
except Exception as e:
    st.error(f"数据库初始化失败: {e}")

def main():
    st.sidebar.title("Sentry 战术分析")
    
    pages = {
        "数据录入": input_page,
        "比赛列表": match_list,
        "统计分析": analysis_page,
        "选手管理": player_manager,
        "版本管理": patch_page,
        "专家模式": expert_mode,
        "系统设置": settings_page
    }
    
    selection = st.sidebar.radio("导航", list(pages.keys()))
    
    page = pages[selection]
    page.show()

if __name__ == "__main__":
    main()
