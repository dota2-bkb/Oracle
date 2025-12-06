import streamlit as st
from database import get_db
from models import Match, League
import pandas as pd

def show():
    st.title("专家管理 / Expert Mode")
    st.warning("⚠️ 这里的操作会永久删除数据，请谨慎操作。")
    
    db = next(get_db())
    
    tab1, tab2 = st.tabs(["比赛管理 (Matches)", "高级设置 (Advanced)"])
    
    with tab1:
        st.subheader("管理比赛记录")
        
        # Filter
        col1, col2 = st.columns(2)
        search = col1.text_input("搜索 Match ID / 队伍名")
        
        query = db.query(Match)
        if search:
            from sqlalchemy import or_
            query = query.filter(or_(
                Match.match_id.contains(search),
                Match.team_name.contains(search),
                Match.opponent_name.contains(search)
            ))
            
        matches = query.order_by(Match.match_time.desc()).limit(50).all()
        
        if matches:
            st.write(f"找到 {len(matches)} 条记录:")
            
            # List with delete button
            for m in matches:
                c1, c2, c3, c4 = st.columns([4, 2, 2, 1])
                with c1:
                    st.write(f"**{m.team_name}** vs **{m.opponent_name}**")
                    st.caption(f"ID: {m.match_id} | Time: {m.match_time}")
                with c2:
                    st.write("Win" if m.win else "Loss")
                with c3:
                    st.write("Radiant" if m.is_radiant else "Dire")
                with c4:
                    if st.button("🗑️", key=f"del_{m.id}"):
                        db.delete(m)
                        db.commit()
                        st.rerun()
                st.divider()
        else:
            st.info("没有找到记录")

    with tab2:
        st.write("数据库统计:")
        count = db.query(Match).count()
        st.write(f"Total Matches: {count}")
        
        if st.button("清空所有比赛数据 (Reset All Matches)"):
            if st.checkbox("确认清空?"):
                db.query(Match).delete()
                db.commit()
                st.success("Done.")
                st.rerun()

    db.close()

