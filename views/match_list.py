import streamlit as st
import pandas as pd
from database import get_db
from models import Match, PickBan, PlayerPerformance, League, Player, Team, PlayerAlias
from services.hero_manager import HeroManager
from views.components import render_bp_visual
from sqlalchemy import or_

def show():
    st.title("比赛列表")
    
    db = next(get_db())
    hm = HeroManager()
    
    # --- Sidebar Filters ---
    st.sidebar.header("筛选条件")
    
    search_id = st.sidebar.text_input("搜索 Match ID")
    
    leagues = db.query(League).order_by(League.league_id.desc()).all()
    league_options = {f"{l.name} ({l.tier})" : l.league_id for l in leagues}
    league_options["所有联赛"] = None
    
    selected_league_label = st.sidebar.selectbox(
        "联赛", 
        options=list(league_options.keys()), 
        index=len(league_options)-1
    )
    selected_league_id = league_options[selected_league_label]
    
    match_teams = [r[0] for r in db.query(Match.team_name).distinct().all()]
    selected_teams = st.sidebar.multiselect("队伍", options=match_teams)
    
    date_filter = st.sidebar.date_input("比赛日期 (起始)", value=None)

    # --- Query Data ---
    query = db.query(Match)
    
    if search_id:
        query = query.filter(Match.match_id.contains(search_id))
    
    if selected_league_id:
        query = query.filter(Match.league_id == selected_league_id)
    
    if selected_teams:
        query = query.filter(
            or_(
                Match.team_name.in_(selected_teams),
                Match.opponent_name.in_(selected_teams)
            )
        )
        
    if date_filter:
        query = query.filter(Match.match_time >= date_filter)
        
    matches = query.order_by(Match.match_time.desc()).limit(50).all()
    
    if not matches:
        st.info("暂无符合条件的比赛数据。")
        db.close()
        return

    # --- Helper Functions ---
    def get_player_display_name(p_perf):
        display_name = p_perf.player_name or "未知"
        if p_perf.account_id:
            alias = db.query(PlayerAlias).filter(PlayerAlias.account_id == p_perf.account_id).first()
            if alias and alias.player:
                return f"**{alias.player.name}** ({p_perf.player_name})"
            pro = db.query(Player).filter(Player.account_id == p_perf.account_id).first()
            if pro and pro.name:
                return f"**{pro.name}**"
        return display_name

    def get_team_logo(team_name):
        t = db.query(Team).filter(Team.name == team_name).first()
        if t and t.logo_url:
            return t.logo_url
        return None

    # --- Display List ---
    for match in matches:
        res_emoji = "✅" if match.win else "❌"
        header_text = f"{match.match_time.strftime('%Y-%m-%d %H:%M')} | {match.team_name} vs {match.opponent_name} | {res_emoji}"
        
        with st.expander(header_text):
            # --- Header with Logos ---
            rad_name = match.team_name if match.is_radiant else match.opponent_name
            dire_name = match.opponent_name if match.is_radiant else match.team_name
            
            rad_logo = get_team_logo(rad_name)
            dire_logo = get_team_logo(dire_name)
            
            h1, h2, h3, h4, h5 = st.columns([1, 3, 1, 3, 1])
            with h1:
                if rad_logo: st.image(rad_logo, width=50)
            with h2:
                st.subheader(f"🟢 {rad_name}")
            with h3:
                st.markdown("<h3 style='text-align: center;'>VS</h3>", unsafe_allow_html=True)
                st.caption(f"ID: {match.match_id}")
            with h4:
                st.subheader(f"🔴 {dire_name}")
            with h5:
                if dire_logo: st.image(dire_logo, width=50)

            st.divider()
            
            # --- BP Visualization ---
            st.write("#### BP 流程")
            
            # Determine First Pick Team
            is_radiant_first = (match.is_radiant == match.first_pick)
            
            # Render visual centered
            c_vis_1, c_vis_2, c_vis_3 = st.columns([1, 2, 1])
            with c_vis_2:
                render_bp_visual(match.pick_bans, rad_name, dire_name, hm, first_pick_radiant=is_radiant_first)
            
            st.divider()
            
            # --- Player Data ---
            st.write("#### 选手详情")
            
            rad_players = sorted([p for p in match.players if p.team_side == 0], key=lambda x: x.position if x.position > 0 else 99)
            dire_players = sorted([p for p in match.players if p.team_side == 1], key=lambda x: x.position if x.position > 0 else 99)
            
            # Fallback sort
            if rad_players and rad_players[0].position == 0:
                rad_players.sort(key=lambda x: x.id)
                for i, p in enumerate(rad_players): p.position = i + 1
            if dire_players and dire_players[0].position == 0:
                dire_players.sort(key=lambda x: x.id)
                for i, p in enumerate(dire_players): p.position = i + 1
            
            c_left, c_right = st.columns(2)
            
            with c_left:
                st.caption(f"🟢 {rad_name}")
                for p in rad_players:
                    h = hm.get_hero(p.hero_id)
                    p_name = get_player_display_name(p)
                    
                    r1, r2, r3, r4 = st.columns([1, 1, 3, 3])
                    with r1: st.markdown(f"**Pos {p.position}**")
                    with r2: 
                        if h.get('icon_url'): st.image(h.get('icon_url'), width=30)
                    with r3: st.caption(h.get('cn_name'))
                    with r4: st.write(p_name)

            with c_right:
                st.caption(f"🔴 {dire_name}")
                for p in dire_players:
                    h = hm.get_hero(p.hero_id)
                    p_name = get_player_display_name(p)
                    
                    r1, r2, r3, r4 = st.columns([1, 1, 3, 3])
                    with r1: st.markdown(f"**Pos {p.position}**")
                    with r2: 
                        if h.get('icon_url'): st.image(h.get('icon_url'), width=30)
                    with r3: st.caption(h.get('cn_name'))
                    with r4: st.write(p_name)

    db.close()
