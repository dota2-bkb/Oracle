import streamlit as st
import pandas as pd
from database import get_db
from models import Match, PickBan, PlayerPerformance, League, Player, Team, PlayerAlias
from services.hero_manager import HeroManager
from datetime import datetime
from sqlalchemy import desc

def show():
    st.title("比赛列表 / Match List")
    
    db = next(get_db())
    hm = HeroManager()
    
    # --- Sidebar Filters ---
    st.sidebar.header("筛选条件 (Filters)")
    
    search_id = st.sidebar.text_input("搜索 Match ID")
    
    leagues = db.query(League).order_by(League.league_id.desc()).all()
    league_options = {f"{l.name} ({l.tier})" : l.league_id for l in leagues}
    league_options["所有联赛 (All Leagues)"] = None
    
    # 默认选中最后一个 (None)
    selected_league_label = st.sidebar.selectbox(
        "联赛 (League)", 
        options=list(league_options.keys()), 
        index=len(league_options)-1
    )
    selected_league_id = league_options[selected_league_label]
    
    match_teams = [r[0] for r in db.query(Match.team_name).distinct().all()]
    selected_teams = st.sidebar.multiselect("队伍 (Team)", options=match_teams)
    
    date_filter = st.sidebar.date_input("比赛日期 (Start Date)", value=None)

    # --- Query Data ---
    query = db.query(Match)
    
    if search_id:
        query = query.filter(Match.match_id.contains(search_id))
    
    if selected_league_id:
        query = query.filter(Match.league_id == selected_league_id)
    
    if selected_teams:
        from sqlalchemy import or_
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
        # 1. Check Manual Alias Mapping first
        # We need to join PlayerAlias -> Player
        # This is heavy in a loop? Maybe optimize or pre-fetch aliases?
        # For now, simple query.
        
        display_name = p_perf.player_name or "Unknown"
        
        # Try Alias table match first (Account ID -> Player)
        if p_perf.account_id:
            # Check Alias
            alias = db.query(PlayerAlias).filter(PlayerAlias.account_id == p_perf.account_id).first()
            if alias and alias.player:
                # Found master player via alias
                return f"**{alias.player.name}** ({p_perf.player_name})"
            
            # Fallback: Check Player table directly (legacy behavior)
            pro = db.query(Player).filter(Player.account_id == p_perf.account_id).first()
            if pro and pro.name:
                return f"**{pro.name}**"
                
        return display_name

    def get_team_logo(team_name):
        # Try to find team logo in DB by name match (fuzzy or exact)
        # Since match.team_name comes from API snapshot, it might match Team.name
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
            # Determine Side
            rad_name = match.team_name if match.is_radiant else match.opponent_name
            dire_name = match.opponent_name if match.is_radiant else match.team_name
            
            rad_logo = get_team_logo(rad_name)
            dire_logo = get_team_logo(dire_name)
            
            # Layout: Logo Name (Rad) -- VS -- Name Logo (Dire)
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
            
            # --- BP Visualization (4 Rows: Rad Pick, Rad Ban, Dire Pick, Dire Ban) ---
            # Need to sort actions into buckets but maintain GLOBAL order index
            
            st.write("#### BP 流程 (Pick / Ban)")
            
            # Filter actions
            # pbs = sorted(match.pick_bans, key=lambda x: x.order)
            # We need to render them in 4 rows? Or 2 rows (Radiant / Dire)?
            # User asked for: "Radiant Pick, Radiant Ban, Dire Pick, Dire Ban" - 4 rows.
            # And "Each row ordered left to right by absolute order".
            
            # Let's build 4 lists
            rad_picks = []
            rad_bans = []
            dire_picks = []
            dire_bans = []
            
            sorted_pbs = sorted(match.pick_bans, key=lambda x: x.order)
            
            for pb in sorted_pbs:
                # pb.team_side: 0=Radiant, 1=Dire
                item = {
                    'hero': hm.get_hero(pb.hero_id),
                    'order': pb.order + 1, # 1-based
                    'is_pick': pb.is_pick
                }
                
                if pb.team_side == 0: # Radiant
                    if pb.is_pick: rad_picks.append(item)
                    else: rad_bans.append(item)
                else: # Dire
                    if pb.is_pick: dire_picks.append(item)
                    else: dire_bans.append(item)
            
            # Helper to render a strip
            def render_strip(label, items, is_ban=False):
                if not items: return
                st.caption(label)
                
                # Use 12 columns fixed layout as requested
                cols = st.columns(12)
                
                # Items are already sorted by absolute order
                for idx, item in enumerate(items):
                    if idx >= 12: break # Safety cap
                    
                    h = item['hero']
                    # Always use img_url (Large) for consistency
                    url = h.get('img_url') or h.get('icon_url')

                    with cols[idx]:
                        # Order Badge
                        st.markdown(f"**#{item['order']}**")
                        
                        # Image with reduced width
                        if url:
                            # Ban: Use opacity hack or overlay? Streamlit native doesn't support styling easily.
                            # Just render image normally but maybe add Emoji below
                            st.image(url, width=45)
                        
                        st.caption(h.get('cn_name') or h.get('en_name'))
            
            # Row 1: Radiant Picks
            render_strip(f"🟢 {rad_name} Pick (Radiant)", rad_picks)
            
            # Row 2: Radiant Bans
            render_strip(f"🚫 {rad_name} Ban (Radiant)", rad_bans, is_ban=True)
            
            st.write("") # Spacer
            
            # Row 3: Dire Picks
            render_strip(f"🔴 {dire_name} Pick (Dire)", dire_picks)
            
            # Row 4: Dire Bans
            render_strip(f"🚫 {dire_name} Ban (Dire)", dire_bans, is_ban=True)

            st.divider()
            
            # --- Player Data (Two Columns) ---
            st.write("#### 选手详情")
            
            # Sort by position (1-5)
            # If position is 0 (old data), fallback to slot logic: 0-4 -> 1-5, 5-9 -> 1-5 (roughly)
            
            rad_players = sorted([p for p in match.players if p.team_side == 0], key=lambda x: x.position if x.position > 0 else 99)
            dire_players = sorted([p for p in match.players if p.team_side == 1], key=lambda x: x.position if x.position > 0 else 99)
            
            # Fallback sort if positions are all 0 (based on id which is insertion order)
            if rad_players and rad_players[0].position == 0:
                rad_players.sort(key=lambda x: x.id)
                # Assign temp positions for display
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
                    
                    # Layout: Pos | Icon | Hero Name | Player Name
                    r1, r2, r3, r4 = st.columns([1, 1, 2, 2])
                    with r1:
                        st.markdown(f"**Pos {p.position}**")
                    with r2:
                        if h.get('icon_url'): st.image(h.get('icon_url'), width=30)
                    with r3:
                        st.caption(h.get('cn_name'))
                    with r4:
                        st.write(p_name)

            with c_right:
                st.caption(f"🔴 {dire_name}")
                for p in dire_players:
                    h = hm.get_hero(p.hero_id)
                    p_name = get_player_display_name(p)
                    
                    r1, r2, r3, r4 = st.columns([1, 1, 2, 2])
                    with r1:
                        st.markdown(f"**Pos {p.position}**")
                    with r2:
                        if h.get('icon_url'): st.image(h.get('icon_url'), width=30)
                    with r3:
                        st.caption(h.get('cn_name'))
                    with r4:
                        st.write(p_name)

    db.close()
