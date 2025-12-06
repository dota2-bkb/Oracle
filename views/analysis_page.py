import streamlit as st
from database import get_db
from models import Match, Team, PlayerPerformance, Player, PickBan
from services.hero_manager import HeroManager
from services.patch_manager import PatchManager
from sqlalchemy import desc, func
import pandas as pd
from datetime import datetime, timedelta

def show():
    st.title("统计分析 / Analysis")
    
    db = next(get_db())
    hm = HeroManager()
    pm = PatchManager()
    
    # --- Sidebar Filters ---
    st.sidebar.header("分析配置")
    
    teams = [r[0] for r in db.query(Match.team_name).distinct().all()]
    selected_team = st.sidebar.selectbox("目标战队 (Target Team)", options=teams)
    
    if not selected_team:
        st.info("请先选择战队。")
        db.close()
        return
    
    patches = pm.get_all_patches()
    filter_mode = st.sidebar.radio("时间范围模式", ["按版本 (Patch)", "按日期 (Date)"])
    
    start_date = None
    if filter_mode == "按版本 (Patch)":
        selected_patch = st.sidebar.selectbox("选择版本", patches)
        if selected_patch:
            start_date = pm.get_patch_date(selected_patch)
            st.sidebar.caption(f"起始日期: {start_date}")
    else:
        start_date = st.sidebar.date_input("起始日期", value=datetime.today().date() - timedelta(days=90))
        
    matches = db.query(Match).filter(
        Match.team_name == selected_team,
        Match.match_time >= start_date
    ).order_by(Match.match_time.desc()).all()
    
    if not matches:
        st.warning("该范围内无比赛数据。")
        db.close()
        return
    
    st.sidebar.success(f"已加载 {len(matches)} 场比赛")

    # =================================================================
    # TABS
    # =================================================================
    tab_team, tab_player, tab_bp = st.tabs(["🛡️ 战队概况 (Team)", "👤 选手绝活 (Player)", "⛓️ BP 链条 (BP Log)"])
    
    # -----------------------------------------------------------------
    # TAB 1: 战队概况
    # -----------------------------------------------------------------
    with tab_team:
        total = len(matches)
        wins = sum(1 for m in matches if m.win)
        
        rad_m = [m for m in matches if m.is_radiant]
        dire_m = [m for m in matches if not m.is_radiant]
        
        rad_wr = (sum(1 for m in rad_m if m.win) / len(rad_m) * 100) if rad_m else 0
        dire_wr = (sum(1 for m in dire_m if m.win) / len(dire_m) * 100) if dire_m else 0
        
        st.subheader("胜率统计")
        c1, c2, c3 = st.columns(3)
        c1.metric("总胜率", f"{(wins/total*100):.1f}%", f"{wins}W - {total-wins}L")
        c2.metric("天辉胜率", f"{rad_wr:.1f}%", f"{len(rad_m)}场")
        c3.metric("夜魇胜率", f"{dire_wr:.1f}%", f"{len(dire_m)}场")
        
        st.divider()
        
        pick_counts = {} 
        ban_counts = {}  
        
        for m in matches:
            my_side = 0 if m.is_radiant else 1
            
            for pb in m.pick_bans:
                if pb.is_pick and pb.team_side == my_side:
                    pick_counts[pb.hero_id] = pick_counts.get(pb.hero_id, 0) + 1
                
                if not pb.is_pick and pb.team_side != my_side:
                    ban_counts[pb.hero_id] = ban_counts.get(pb.hero_id, 0) + 1

        c_pick, c_ban = st.columns(2)
        
        with c_pick:
            st.subheader("本队常用英雄 (Most Picked)")
            if pick_counts:
                df_pick = pd.DataFrame(list(pick_counts.items()), columns=['hero_id', 'count'])
                df_pick['hero'] = df_pick['hero_id'].apply(lambda x: hm.get_hero(x).get('cn_name'))
                df_pick = df_pick.sort_values('count', ascending=False).head(10)
                st.dataframe(df_pick[['hero', 'count']], hide_index=True, use_container_width=False)
            else:
                st.caption("无数据")
                
        with c_ban:
            st.subheader("对手禁用英雄 (Most Banned)")
            if ban_counts:
                df_ban = pd.DataFrame(list(ban_counts.items()), columns=['hero_id', 'count'])
                df_ban['hero'] = df_ban['hero_id'].apply(lambda x: hm.get_hero(x).get('cn_name'))
                df_ban = df_ban.sort_values('count', ascending=False).head(10)
                st.dataframe(df_ban[['hero', 'count']], hide_index=True, use_container_width=False)
            else:
                st.caption("无数据")

    # -----------------------------------------------------------------
    # TAB 2: 选手绝活
    # -----------------------------------------------------------------
    with tab_player:
        st.subheader("主力选手英雄池")
        
        recent_7 = matches[:7] 
        
        pos_player_counts = {i: {} for i in range(1, 6)} 
        
        for m in recent_7:
            my_side = 0 if m.is_radiant else 1
            my_ps = [p for p in m.players if p.team_side == my_side]
            
            for p in my_ps:
                pos = p.position
                acc = p.account_id
                if pos and 1 <= pos <= 5 and acc:
                    pos_player_counts[pos][acc] = pos_player_counts[pos].get(acc, 0) + 1
        
        main_players = {} 
        for pos, counts in pos_player_counts.items():
            if counts:
                main = max(counts, key=counts.get)
                main_players[pos] = main
        
        pos_tabs = st.tabs([f"Pos {i}" for i in range(1, 6)])
        
        for i, tab in enumerate(pos_tabs):
            pos = i + 1
            acc_id = main_players.get(pos)
            
            with tab:
                if not acc_id:
                    st.warning(f"最近 7 场未检测到固定的 Pos {pos} 选手。")
                    continue
                
                p_info = db.query(Player).filter(Player.account_id == acc_id).first()
                p_name = p_info.name if p_info else f"Unknown ({acc_id})"
                st.markdown(f"**主力选手: {p_name}**")
                
                hero_stats = {} 
                
                for m in matches:
                    p_rec = next((p for p in m.players if p.account_id == acc_id), None)
                    if p_rec:
                        hid = p_rec.hero_id
                        if hid not in hero_stats:
                            hero_stats[hid] = {'picks':0, 'wins':0, 'rad_picks':0, 'rad_wins':0, 'dire_picks':0, 'dire_wins':0}
                        
                        s = hero_stats[hid]
                        
                        my_side = 0 if m.is_radiant else 1
                        if p_rec.team_side == my_side:
                            s['picks'] += 1
                            if m.win: s['wins'] += 1 
                            
                            if m.is_radiant:
                                s['rad_picks'] += 1
                                if m.win: s['rad_wins'] += 1
                            else:
                                s['dire_picks'] += 1
                                if m.win: s['dire_wins'] += 1
                
                if hero_stats:
                    data = []
                    for hid, s in hero_stats.items():
                        total = s['picks']
                        if total == 0: continue
                        
                        wr = s['wins']/total*100
                        rad_wr = (s['rad_wins']/s['rad_picks']*100) if s['rad_picks'] else 0
                        dire_wr = (s['dire_wins']/s['dire_picks']*100) if s['dire_picks'] else 0
                        
                        h = hm.get_hero(hid)
                        data.append({
                            "Hero": h.get('cn_name'),
                            "Pick%": f"{(total/len(matches)*100):.1f}% ({total})",
                            "Win%": f"{wr:.1f}%",
                            "Rad % (WR)": f"{(s['rad_picks']/total*100):.0f}% ({rad_wr:.0f}%)",
                            "Dire % (WR)": f"{(s['dire_picks']/total*100):.0f}% ({dire_wr:.0f}%)",
                            "icon": h.get('icon_url'),
                            "_sort_pick": total
                        })
                    
                    df = pd.DataFrame(data).sort_values("_sort_pick", ascending=False)
                    
                    st.dataframe(
                        df, 
                        column_config={
                            "icon": st.column_config.ImageColumn("Icon", width="small"),
                            "_sort_pick": None 
                        },
                        hide_index=True
                    )
                else:
                    st.info("无数据")

    # -----------------------------------------------------------------
    # TAB 3: BP 链条 (BP Log)
    # -----------------------------------------------------------------
    with tab_bp:
        st.subheader("最近比赛 BP 链条")
        
        # 1. Filter Opponent
        opponents = list(set([m.opponent_name for m in matches]))
        opponents.sort()
        selected_opponents = st.multiselect("过滤对手 (Filter Opponent)", options=opponents)
        
        limit_bp = st.number_input("显示最近多少场?", 5, 50, 10)
        
        # Apply filter
        bp_matches = matches
        if selected_opponents:
            bp_matches = [m for m in bp_matches if m.opponent_name in selected_opponents]
            
        bp_matches = bp_matches[:limit_bp]
        
        if not bp_matches:
            st.info("无符合条件的比赛。")
        
        # Helper to render a strip (Same logic as match_list.py)
        def render_strip(label, items, is_ban=False):
            if not items: return
            st.caption(label)
            cols = st.columns(12)
            for idx, item in enumerate(items):
                if idx >= 12: break
                h = item['hero']
                # Use img_url (Large) for consistency
                url = h.get('img_url') or h.get('icon_url')
                with cols[idx]:
                    st.markdown(f"**#{item['order']}**")
                    if url:
                        st.image(url, width=45)
                    st.caption(h.get('cn_name') or h.get('en_name'))

        for m in bp_matches:
            res_emoji = "✅" if m.win else "❌"
            header = f"{m.match_time.strftime('%m-%d')} | vs {m.opponent_name} ({'Radiant' if m.is_radiant else 'Dire'}) | {res_emoji}"
            
            with st.expander(header, expanded=True):
                
                rad_picks = []
                rad_bans = []
                dire_picks = []
                dire_bans = []
                
                sorted_pbs = sorted(m.pick_bans, key=lambda x: x.order)
                
                for pb in sorted_pbs:
                    item = {
                        'hero': hm.get_hero(pb.hero_id),
                        'order': pb.order + 1,
                        'is_pick': pb.is_pick
                    }
                    if pb.team_side == 0: # Radiant
                        if pb.is_pick: rad_picks.append(item)
                        else: rad_bans.append(item)
                    else: # Dire
                        if pb.is_pick: dire_picks.append(item)
                        else: dire_bans.append(item)
                
                render_strip("🟢 天辉 Pick", rad_picks)
                render_strip("🚫 天辉 Ban", rad_bans, is_ban=True)
                st.write("")
                render_strip("🔴 夜魇 Pick", dire_picks)
                render_strip("🚫 夜魇 Ban", dire_bans, is_ban=True)

    db.close()
