import streamlit as st
from database import get_db
from models import Match, Team, PlayerPerformance, Player, PickBan, League, PlayerAlias
from services.hero_manager import HeroManager
from services.patch_manager import PatchManager
from views.components import render_bp_visual
from sqlalchemy import desc, func, or_
import pandas as pd
from datetime import datetime, timedelta
from io import BytesIO

def generate_excel_export(matches, team_name, db, hm):
    """
    Generates an Excel file with analysis data.
    """
    output = BytesIO()
    # Use 'xlsxwriter' or 'openpyxl'. Default is openpyxl for xlsx usually.
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # --- Sheet 1: Overview ---
        total = len(matches)
        if total == 0:
            return None
            
        wins = sum(1 for m in matches if m.win)
        rad_m = [m for m in matches if m.is_radiant]
        dire_m = [m for m in matches if not m.is_radiant]
        
        rad_wr = (sum(1 for m in rad_m if m.win) / len(rad_m)) if rad_m else 0
        dire_wr = (sum(1 for m in dire_m if m.win) / len(dire_m)) if dire_m else 0
        
        overview_data = {
            "指标 (Metric)": ["总场次 (Total)", "胜场 (Wins)", "胜率 (Win Rate)", "天辉场次 (Radiant)", "天辉胜率 (Rad WR)", "夜魇场次 (Dire)", "夜魇胜率 (Dire WR)"],
            "数值 (Value)": [total, wins, f"{wins/total:.1%}", len(rad_m), f"{rad_wr:.1%}", len(dire_m), f"{dire_wr:.1%}"]
        }
        pd.DataFrame(overview_data).to_excel(writer, sheet_name="队伍概况", index=False)
        
        # --- Sheet 2: Hero Picks & Bans ---
        pick_counts = {}
        ban_counts = {}
        
        for m in matches:
            my_side = 0 if m.is_radiant else 1
            for pb in m.pick_bans:
                if pb.is_pick and pb.team_side == my_side:
                    pick_counts[pb.hero_id] = pick_counts.get(pb.hero_id, 0) + 1
                if not pb.is_pick and pb.team_side != my_side:
                    ban_counts[pb.hero_id] = ban_counts.get(pb.hero_id, 0) + 1
        
        # Picks
        if pick_counts:
            df_p = pd.DataFrame(list(pick_counts.items()), columns=['hero_id', 'count'])
            df_p['hero_name'] = df_p['hero_id'].apply(lambda x: hm.get_hero(x).get('cn_name'))
            df_p = df_p.sort_values('count', ascending=False)
            df_p[['hero_name', 'count']].to_excel(writer, sheet_name="本队Pick", index=False)
            
        # Bans
        if ban_counts:
            df_b = pd.DataFrame(list(ban_counts.items()), columns=['hero_id', 'count'])
            df_b['hero_name'] = df_b['hero_id'].apply(lambda x: hm.get_hero(x).get('cn_name'))
            df_b = df_b.sort_values('count', ascending=False)
            df_b[['hero_name', 'count']].to_excel(writer, sheet_name="对手Ban", index=False)
            
        # --- Sheet 3: Player Stats ---
        # Identify main players (simplification: just list all players found in filtered matches)
        player_stats = []
        
        # We process all players in these matches
        # Map: Account ID -> {Hero -> {picks, wins...}}
        p_map = {}
        
        for m in matches:
            my_side = 0 if m.is_radiant else 1
            radiant_won = (m.is_radiant == m.win)
            
            for p in m.players:
                if p.team_side == my_side and p.account_id:
                    if p.account_id not in p_map:
                        p_map[p.account_id] = {'name': p.name or str(p.account_id), 'heroes': {}}
                    
                    ph_map = p_map[p.account_id]['heroes']
                    if p.hero_id not in ph_map:
                        ph_map[p.hero_id] = {'picks':0, 'wins':0}
                    
                    ph_map[p.hero_id]['picks'] += 1
                    
                    # Did this player win?
                    player_won = (p.team_side == 0 and radiant_won) or (p.team_side == 1 and not radiant_won)
                    if player_won:
                        ph_map[p.hero_id]['wins'] += 1
        
        # Flatten for Excel
        # Columns: Player, Hero, Picks, Win Rate
        export_rows = []
        for pid, p_data in p_map.items():
            # Get real name if possible
            p_obj = db.query(Player).filter(Player.account_id == pid).first()
            p_name = p_obj.name if p_obj else p_data['name']
            
            for hid, stats in p_data['heroes'].items():
                h_name = hm.get_hero(hid).get('cn_name')
                picks = stats['picks']
                wr = stats['wins'] / picks if picks else 0
                export_rows.append({
                    "选手": p_name,
                    "英雄": h_name,
                    "场次": picks,
                    "胜率": f"{wr:.1%}"
                })
        
        if export_rows:
            df_players = pd.DataFrame(export_rows)
            # Sort by Player then Picks
            df_players = df_players.sort_values(['选手', '场次'], ascending=[True, False])
            df_players.to_excel(writer, sheet_name="选手英雄池", index=False)

    return output.getvalue()

def show():
    st.title("统计分析")
    
    db = next(get_db())
    hm = HeroManager()
    pm = PatchManager()
    
    # --- Sidebar Filters ---
    st.sidebar.header("分析配置")
    
    # Team Selection
    teams = [r[0] for r in db.query(Match.team_name).distinct().all()]
    selected_team = st.sidebar.selectbox("目标战队", options=teams)
    
    if not selected_team:
        st.info("请先选择战队。")
        db.close()
        return
    
    # League Selection (Multi-select)
    all_leagues = db.query(League).order_by(League.league_id.desc()).all()
    league_opts = {f"{l.name}": l.league_id for l in all_leagues}
    selected_league_names = st.sidebar.multiselect("筛选联赛", options=list(league_opts.keys()))
    selected_league_ids = [league_opts[n] for n in selected_league_names] if selected_league_names else []

    # Date/Patch Filter
    patches = pm.get_all_patches()
    filter_mode = st.sidebar.radio("时间范围模式", ["按版本", "按日期"])
    
    start_date = None
    if filter_mode == "按版本":
        selected_patch = st.sidebar.selectbox("选择版本", patches)
        if selected_patch:
            start_date = pm.get_patch_date(selected_patch)
            st.sidebar.caption(f"起始日期: {start_date}")
    else:
        start_date = st.sidebar.date_input("起始日期", value=datetime.today().date() - timedelta(days=90))
        
    # Build Query
    query = db.query(Match).filter(Match.team_name == selected_team)
    
    if start_date:
        query = query.filter(Match.match_time >= start_date)
    
    if selected_league_ids:
        query = query.filter(Match.league_id.in_(selected_league_ids))
        
    matches = query.order_by(Match.match_time.desc()).all()
    
    if not matches:
        st.warning("该范围内无比赛数据。")
        db.close()
        return
    
    st.sidebar.success(f"已加载 {len(matches)} 场比赛")
    
    # --- Excel Export Button ---
    if st.sidebar.button("生成 Excel 报告"):
        excel_data = generate_excel_export(matches, selected_team, db, hm)
        if excel_data:
            st.sidebar.download_button(
                label="📥 下载 Excel",
                data=excel_data,
                file_name=f"{selected_team}_analysis_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    # =================================================================
    # TABS
    # =================================================================
    tab_team, tab_player, tab_bp = st.tabs(["🛡️ 战队概况", "👤 选手绝活", "⛓️ BP 链条"])
    
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
        c1.metric("总胜率", f"{(wins/total*100):.1f}%", f"{wins}胜 - {total-wins}负")
        c2.metric("天辉胜率", f"{rad_wr:.1f}%", f"{len(rad_m)}场")
        c3.metric("夜魇胜率", f"{dire_wr:.1f}%", f"{len(dire_m)}场")
        
        st.divider()
        
        # --- Hero Stats ---
        pick_counts = {} 
        ban_counts = {}  
        
        # Combo Analysis Data Preparation
        hero_partners = {} 
        hero_positions = {} # hero_id -> {pos: count}
        
        for m in matches:
            my_side = 0 if m.is_radiant else 1
            
            # Picks/Bans
            for pb in m.pick_bans:
                if pb.is_pick and pb.team_side == my_side:
                    pick_counts[pb.hero_id] = pick_counts.get(pb.hero_id, 0) + 1
                
                if not pb.is_pick and pb.team_side != my_side:
                    ban_counts[pb.hero_id] = ban_counts.get(pb.hero_id, 0) + 1
            
            # Player Performance for Combos & Positions
            my_team_heroes = []
            my_team_performances = [p for p in m.players if p.team_side == my_side]
            
            for p in my_team_performances:
                my_team_heroes.append(p.hero_id)
                
                # Position Stats
                if p.hero_id not in hero_positions: hero_positions[p.hero_id] = {}
                pos = p.position
                if pos > 0:
                    hero_positions[p.hero_id][pos] = hero_positions[p.hero_id].get(pos, 0) + 1

            # Combo Counting
            for hid in my_team_heroes:
                if hid not in hero_partners: hero_partners[hid] = {}
                for partner in my_team_heroes:
                    if hid != partner:
                        hero_partners[hid][partner] = hero_partners[hid].get(partner, 0) + 1

        # Top Picks / Bans UI
        c_pick, c_ban = st.columns(2)
        
        with c_pick:
            st.subheader("本队常用英雄 (Pick)")
            if pick_counts:
                df_pick = pd.DataFrame(list(pick_counts.items()), columns=['hero_id', 'count'])
                df_pick['英雄'] = df_pick['hero_id'].apply(lambda x: hm.get_hero(x).get('cn_name'))
                df_pick['场次'] = df_pick['count']
                df_pick = df_pick.sort_values('count', ascending=False).head(10)
                st.dataframe(df_pick[['英雄', '场次']], hide_index=True, use_container_width=False)
            else:
                st.caption("无数据")
                
        with c_ban:
            st.subheader("对手禁用英雄 (Ban)")
            if ban_counts:
                df_ban = pd.DataFrame(list(ban_counts.items()), columns=['hero_id', 'count'])
                df_ban['英雄'] = df_ban['hero_id'].apply(lambda x: hm.get_hero(x).get('cn_name'))
                df_ban['场次'] = df_ban['count']
                df_ban = df_ban.sort_values('count', ascending=False).head(10)
                st.dataframe(df_ban[['英雄', '场次']], hide_index=True, use_container_width=False)
            else:
                st.caption("无数据")

        # --- Detailed Analysis (Requirement #5 & #6) ---
        st.divider()
        st.subheader("英雄深度分析")
        
        # Hero Selector (sorted by pick count)
        sorted_heroes = sorted(pick_counts.items(), key=lambda x: x[1], reverse=True)
        hero_opts = {f"{hm.get_hero(hid).get('cn_name')} ({count}场)": hid for hid, count in sorted_heroes}
        
        if not hero_opts:
            st.info("暂无英雄数据")
        else:
            sel_hero_label = st.selectbox("选择要分析的英雄", options=list(hero_opts.keys()))
            sel_hero_id = hero_opts[sel_hero_label]
            
            h_data = hm.get_hero(sel_hero_id)
            
            dc1, dc2 = st.columns([1, 3])
            with dc1:
                st.image(h_data.get('img_url'), width=150) # Approx 50% width if column is small
                
                # Position Stats
                st.markdown("**位置分布:**")
                pos_stats = hero_positions.get(sel_hero_id, {})
                if pos_stats:
                    total_p = sum(pos_stats.values())
                    for p_idx in range(1, 6):
                        c = pos_stats.get(p_idx, 0)
                        if c > 0:
                            st.text(f"{p_idx}号位: {c} ({c/total_p*100:.0f}%)")
                else:
                    st.caption("暂无位置数据")

            with dc2:
                st.markdown("**最佳搭档:**")
                partners = hero_partners.get(sel_hero_id, {})
                if partners:
                    df_partners = pd.DataFrame(list(partners.items()), columns=['partner_id', 'count'])
                    df_partners['搭档'] = df_partners['partner_id'].apply(lambda x: hm.get_hero(x).get('cn_name'))
                    df_partners['头像'] = df_partners['partner_id'].apply(lambda x: hm.get_hero(x).get('icon_url'))
                    df_partners['场次'] = df_partners['count']
                    df_partners = df_partners.sort_values('count', ascending=False).head(5)
                    
                    st.dataframe(
                        df_partners[['头像', '搭档', '场次']],
                        column_config={
                            "头像": st.column_config.ImageColumn("头像", width="small")
                        },
                        hide_index=True
                    )
                else:
                    st.caption("暂无搭档数据")

    # -----------------------------------------------------------------
    # TAB 2: 选手绝活 (With Context Filter - Req #7)
    # -----------------------------------------------------------------
    with tab_player:
        st.subheader("主力选手英雄池")
        
        # Filter Checkbox
        filter_context = st.checkbox("仅分析当前筛选范围内的比赛", value=True)
        
        # Identify Main Players from CURRENT context first
        recent_7 = matches[:7] 
        pos_player_counts = {i: {} for i in range(1, 6)} 
        for m in recent_7:
            my_side = 0 if m.is_radiant else 1
            my_ps = [p for p in m.players if p.team_side == my_side]
            for p in my_ps:
                if p.position and 1 <= p.position <= 5 and p.account_id:
                    pos_player_counts[p.position][p.account_id] = pos_player_counts[p.position].get(p.account_id, 0) + 1
        
        main_players = {} 
        for pos, counts in pos_player_counts.items():
            if counts:
                main_players[pos] = max(counts, key=counts.get)
        
        pos_tabs = st.tabs([f"{i}号位" for i in range(1, 6)])
        
        for i, tab in enumerate(pos_tabs):
            pos = i + 1
            acc_id = main_players.get(pos)
            
            with tab:
                if not acc_id:
                    st.warning(f"当前范围内未检测到固定的 {pos}号位 选手。")
                    continue
                
                # Get Player Info
                p_info = db.query(Player).filter(Player.account_id == acc_id).first()
                # Or Alias
                alias = db.query(PlayerAlias).filter(PlayerAlias.account_id == acc_id).first()
                p_name_display = f"未知 ({acc_id})"
                if alias and alias.player: p_name_display = alias.player.name
                elif p_info: p_name_display = p_info.name
                
                st.markdown(f"**选手: {p_name_display}**")
                
                # Determine data source
                player_matches = []
                if filter_context:
                    player_matches = matches
                else:
                    # Query ALL matches for this player in last 3 years
                    three_years_ago = datetime.now() - timedelta(days=3*365)
                    perfs = db.query(PlayerPerformance).join(Match).filter(
                        PlayerPerformance.account_id == acc_id,
                        Match.match_time >= three_years_ago
                    ).all()
                    player_matches = [p.match for p in perfs if p.match]
                
                # Calculate Stats
                hero_stats = {} 
                for m in player_matches:
                    p_rec = next((p for p in m.players if p.account_id == acc_id), None)
                    
                    if p_rec:
                        hid = p_rec.hero_id
                        if hid not in hero_stats:
                            hero_stats[hid] = {'picks':0, 'wins':0, 'rad_picks':0, 'rad_wins':0, 'dire_picks':0, 'dire_wins':0}
                        
                        s = hero_stats[hid]
                        s['picks'] += 1
                        
                        radiant_won = (m.is_radiant == m.win)
                        player_won = (p_rec.team_side == 0 and radiant_won) or (p_rec.team_side == 1 and not radiant_won)
                        
                        if player_won: s['wins'] += 1
                        
                        if p_rec.team_side == 0: # Radiant
                            s['rad_picks'] += 1
                            if player_won: s['rad_wins'] += 1
                        else: # Dire
                            s['dire_picks'] += 1
                            if player_won: s['dire_wins'] += 1
                
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
                            "英雄": h.get('cn_name'),
                            "使用率": f"{(total/len(player_matches)*100):.1f}% ({total})",
                            "胜率": f"{wr:.1f}%",
                            "天辉% (胜率)": f"{(s['rad_picks']/total*100):.0f}% ({rad_wr:.0f}%)",
                            "夜魇% (胜率)": f"{(s['dire_picks']/total*100):.0f}% ({dire_wr:.0f}%)",
                            "icon": h.get('icon_url'),
                            "_sort_pick": total
                        })
                    
                    df = pd.DataFrame(data).sort_values("_sort_pick", ascending=False)
                    
                    st.dataframe(
                        df, 
                        column_config={
                            "icon": st.column_config.ImageColumn("头像", width="small"),
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
        selected_opponents = st.multiselect("过滤对手", options=opponents)
        
        limit_bp = st.number_input("显示最近多少场?", 5, 50, 10)
        
        # Apply filter
        bp_matches = matches
        if selected_opponents:
            bp_matches = [m for m in bp_matches if m.opponent_name in selected_opponents]
            
        bp_matches = bp_matches[:limit_bp]
        
        if not bp_matches:
            st.info("无符合条件的比赛。")
        
        for m in bp_matches:
            res_emoji = "✅" if m.win else "❌"
            # Determine side for display
            my_side_str = "天辉" if m.is_radiant else "夜魇"
            header = f"{m.match_time.strftime('%m-%d')} | vs {m.opponent_name} ({my_side_str}) | {res_emoji}"
            
            with st.expander(header, expanded=True):
                rad_name = m.team_name if m.is_radiant else m.opponent_name
                dire_name = m.opponent_name if m.is_radiant else m.team_name
                
                is_radiant_first = (m.is_radiant == m.first_pick)
                
                # Center the visual
                c1, c2, c3 = st.columns([1, 2, 1])
                with c2:
                    render_bp_visual(m.pick_bans, rad_name, dire_name, hm, first_pick_radiant=is_radiant_first)

    db.close()