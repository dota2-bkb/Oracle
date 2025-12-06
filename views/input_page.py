import streamlit as st
from datetime import datetime
from services.api_client import OpenDotaClient
from services.data_processor import DataProcessor
from services.hero_manager import HeroManager
from database import get_db
from models import Match, Team, League, PickBan, PlayerPerformance, Player
from sqlalchemy.orm import Session
import uuid

def show():
    st.title("数据录入 / Data Entry")
    
    db = next(get_db())
    client = OpenDotaClient()
    processor = DataProcessor()
    hm = HeroManager()
    
    tab1, tab2, tab3 = st.tabs(["批量抓取 (Batch Fetch)", "单场抓取 (Single Fetch)", "手动录入 (Manual Scrim)"])
    
    # --- Tab 1: 批量抓取 ---
    with tab1:
        st.subheader("批量比赛录入")
        
        fetch_mode = st.radio("抓取模式", ["按战队 (By Team)", "按联赛 (By League)"])
        
        if fetch_mode == "按战队 (By Team)":
            teams = db.query(Team).order_by(Team.name).all()
            if not teams:
                st.error("暂无战队数据，请先去设置页面同步活跃战队。")
            else:
                team_options = {f"{t.name} [{t.tag}]": t.team_id for t in teams}
                selected_team_label = st.selectbox("选择目标战队", options=list(team_options.keys()))
                
                if selected_team_label:
                    target_team_id = team_options[selected_team_label]
                    limit = st.number_input("获取最近比赛场数", min_value=1, max_value=50, value=5)
                    
                    if st.button("预览最近比赛"):
                        with st.spinner("正在获取比赛列表..."):
                            matches = client.fetch_team_matches(target_team_id, limit=limit)
                            if matches:
                                st.session_state['preview_matches'] = matches
                                st.session_state['target_team_id'] = target_team_id
                                st.session_state['fetch_type'] = 'team'
                            else:
                                st.warning("未找到比赛记录")

        elif fetch_mode == "按联赛 (By League)":
            leagues = db.query(League).order_by(League.league_id.desc()).all()
            if not leagues:
                st.info("暂无联赛数据，可直接输入 ID 或去设置页面同步。")
                league_options = {}
            else:
                league_options = {f"{l.name} (ID: {l.league_id})": l.league_id for l in leagues}
            
            use_dropdown = st.checkbox("从列表选择", value=True)
            
            league_id = 0
            if use_dropdown and league_options:
                selected_label = st.selectbox("选择联赛", options=list(league_options.keys()))
                league_id = league_options[selected_label]
            else:
                league_id = st.number_input("手动输入 League ID", value=0)
            
            limit = st.number_input("检查最近多少场职业比赛", value=100)
            
            if st.button("搜索联赛近期比赛") and league_id > 0:
                with st.spinner("正在搜索..."):
                    pro_matches = client.fetch_pro_matches(limit=limit)
                    filtered_matches = [m for m in pro_matches if m.get('leagueid') == league_id]
                    
                    if filtered_matches:
                        st.session_state['preview_matches'] = filtered_matches
                        st.session_state['target_team_id'] = None 
                        st.session_state['fetch_type'] = 'league'
                        st.success(f"找到 {len(filtered_matches)} 场该联赛的比赛")
                    else:
                        st.warning(f"在最近 {limit} 场职业比赛记录中未找到该联赛 (ID {league_id}) 的比赛。")

        # --- Preview Area ---
        if 'preview_matches' in st.session_state and st.session_state['preview_matches']:
            st.divider()
            st.write("### 待保存比赛预览")
            
            matches_to_save = []
            preview_list = st.session_state['preview_matches']
            fetch_type = st.session_state.get('fetch_type')
            
            team_map = {}
            if fetch_type == 'team':
                all_db_teams = db.query(Team).all()
                for t in all_db_teams:
                    team_map[t.team_id] = t.name
            
            for m in preview_list:
                mid = m['match_id']
                exists = db.query(Match).filter(Match.match_id == str(mid)).first()
                
                r_name = m.get('radiant_name')
                d_name = m.get('dire_name')
                
                if fetch_type == 'team':
                    my_tid = st.session_state['target_team_id']
                    is_radiant = m.get('radiant') 
                    opp_tid = m.get('opposing_team_id')
                    my_team_name = team_map.get(my_tid, f"Team {my_tid}")
                    opp_team_name = team_map.get(opp_tid, f"Opponent {opp_tid}")
                    
                    if is_radiant:
                        r_name = my_team_name
                        d_name = opp_team_name
                    else:
                        r_name = opp_team_name
                        d_name = my_team_name
                
                if not r_name: r_name = "Radiant"
                if not d_name: d_name = "Dire"
                
                col1, col2, col3, col4 = st.columns([1, 4, 2, 2])
                with col1:
                    save = st.checkbox(f"{mid}", value=not exists, key=f"chk_{mid}", disabled=bool(exists))
                with col2:
                    st.text(f"{r_name} vs {d_name}")
                with col3:
                    if m.get('start_time'):
                        ts = datetime.fromtimestamp(m['start_time'])
                        st.text(ts.strftime('%Y-%m-%d %H:%M'))
                    else:
                        st.text("-")
                with col4:
                    if exists:
                        st.caption("已存在")
                    else:
                        st.caption("新比赛")
                
                if save and not exists:
                    matches_to_save.append(m)
            
            if st.button(f"保存选中的 {len(matches_to_save)} 场比赛"):
                progress = st.progress(0)
                success_count = 0
                
                for i, m_summary in enumerate(matches_to_save):
                    try:
                        mid = m_summary['match_id']
                        detail_data = client.fetch_match_details(mid)
                        
                        for side in ['radiant_team_id', 'dire_team_id']:
                            tid = detail_data.get(side)
                            if tid:
                                t = db.query(Team).filter(Team.team_id == tid).first()
                                if not t:
                                    t_info = client.fetch_team_details(tid)
                                    if t_info:
                                        db.add(Team(team_id=tid, name=t_info.get('name'), tag=t_info.get('tag'), logo_url=t_info.get('logo_url')))
                                        db.commit()

                        tid = st.session_state.get('target_team_id')
                        processor.save_match_to_db(db, detail_data, target_team_id=tid)
                        success_count += 1
                        
                    except Exception as e:
                        st.error(f"Match {mid} failed: {e}")
                    
                    progress.progress((i + 1) / len(matches_to_save))
                
                st.success(f"操作完成！成功: {success_count}/{len(matches_to_save)}")
                del st.session_state['preview_matches']
                st.rerun()

    # --- Tab 2: 单场抓取 ---
    with tab2:
        st.subheader("单场抓取")
        match_id_input = st.text_input("输入 Match ID", placeholder="e.g. 7123456789")
        
        teams = db.query(Team).order_by(Team.name).all()
        team_options = {t.name: t.team_id for t in teams}
        team_options["不指定 (默认天辉视角)"] = None
        
        selected_team_name = st.selectbox("选择分析视角 (主队)", options=list(team_options.keys()), index=len(team_options)-1, key="single_fetch_team")
        target_team_id = team_options[selected_team_name]
        
        if st.button("抓取并保存 (Fetch & Save)"):
            if not match_id_input:
                st.warning("请输入 Match ID")
            else:
                with st.spinner("正在请求 OpenDota API..."):
                    data = client.fetch_match_details(match_id_input)
                    if data and 'error' not in data:
                        try:
                            r_id = data.get('radiant_team_id')
                            if r_id and not db.query(Team).filter(Team.team_id == r_id).first():
                                t_info = client.fetch_team_details(r_id)
                                if t_info:
                                    db.add(Team(team_id=r_id, name=t_info.get('name'), tag=t_info.get('tag'), logo_url=t_info.get('logo_url')))
                                    db.commit()
                                    
                            d_id = data.get('dire_team_id')
                            if d_id and not db.query(Team).filter(Team.team_id == d_id).first():
                                t_info = client.fetch_team_details(d_id)
                                if t_info:
                                    db.add(Team(team_id=d_id, name=t_info.get('name'), tag=t_info.get('tag'), logo_url=t_info.get('logo_url')))
                                    db.commit()

                            match_obj = processor.save_match_to_db(db, data, target_team_id=target_team_id)
                            st.success(f"成功保存: {match_obj.team_name} vs {match_obj.opponent_name}")
                        except Exception as e:
                            st.error(f"保存失败: {e}")
                    else:
                        st.error("API Error")

    # --- Tab 3: 手动录入 (Scrims) ---
    with tab3:
        st.subheader("手动录入 (Manual Entry)")
        
        with st.form("scrim_form"):
            # Row 1: Basic
            c1, c2, c3 = st.columns(3)
            scrim_date = c1.date_input("日期", datetime.today())
            
            is_scrim = c2.checkbox("标记为训练赛 (Scrim)", value=True)
            
            # League Selection
            leagues = db.query(League).order_by(League.league_id.desc()).all()
            league_keys = ["None"] + [l.name for l in leagues]
            league_map = {l.name: l.league_id for l in leagues}
            league_map["None"] = None
            
            selected_league = c3.selectbox("联赛 (League)", league_keys, index=0)
            
            # Row 2: Teams & Result
            all_teams = db.query(Team).order_by(Team.name).all()
            team_opts = [t.name for t in all_teams] + ["Unknown/Custom"]
            
            c4, c5, c6, c7 = st.columns(4)
            my_team = c4.selectbox("我方队伍", team_opts, index=0)
            opp_team = c5.selectbox("对方队伍", team_opts, index=1 if len(team_opts)>1 else 0)
            
            my_side = c6.radio("我方阵营", ["Radiant (天辉)", "Dire (夜魇)"])
            result = c7.radio("比赛结果", ["Win (胜)", "Loss (负)"])
            
            # FIRST PICK Selection
            st.write("##### BP 先后手 (First Pick)")
            first_pick_team = st.radio("谁先 Ban/Pick?", ["Radiant (天辉)", "Dire (夜魇)"], horizontal=True)

            # Row 3: BP Input
            st.divider()
            st.write("##### 阵容录入 (Pick / Ban)")
            
            heroes = hm.get_all_heroes()
            heroes.sort(key=lambda x: x.get('cn_name') or "")
            hero_opts = {f"{h['cn_name']} ({h['en_name']})": h['id'] for h in heroes}
            
            input_errors = []
            
            def hero_select(key, label, placeholder_text):
                box_options = [placeholder_text] + list(hero_opts.keys())
                selected = st.selectbox(label, box_options, key=key, label_visibility="collapsed")
                if selected == placeholder_text:
                    return None
                return hero_opts[selected]

            # 1. Radiant Pick (5)
            st.caption("🟢 天辉 Pick")
            c_rp = st.columns(5)
            rad_picks = []
            for i in range(5):
                with c_rp[i]:
                    pid = f"rp_{i}"
                    lbl = f"Pick {i+1}"
                    val = hero_select(pid, f"Rad Pick {i+1}", lbl)
                    rad_picks.append(val)

            # 2. Radiant Ban (7)
            st.caption("🚫 天辉 Ban")
            c_rb = st.columns(7)
            rad_bans = []
            for i in range(7):
                with c_rb[i]:
                    pid = f"rb_{i}"
                    lbl = f"Ban {i+1}"
                    val = hero_select(pid, f"Rad Ban {i+1}", lbl)
                    rad_bans.append(val)

            st.write("") # Spacer

            # 3. Dire Pick (5)
            st.caption("🔴 夜魇 Pick")
            c_dp = st.columns(5)
            dire_picks = []
            for i in range(5):
                with c_dp[i]:
                    pid = f"dp_{i}"
                    lbl = f"Pick {i+1}"
                    val = hero_select(pid, f"Dire Pick {i+1}", lbl)
                    dire_picks.append(val)

            # 4. Dire Ban (7)
            st.caption("🚫 夜魇 Ban")
            c_db = st.columns(7)
            dire_bans = []
            for i in range(7):
                with c_db[i]:
                    pid = f"db_{i}"
                    lbl = f"Ban {i+1}"
                    val = hero_select(pid, f"Dire Ban {i+1}", lbl)
                    dire_bans.append(val)

            submitted = st.form_submit_button("保存记录")
            
            if submitted:
                # Validation
                missing_slots = []
                if any(x is None for x in rad_picks): missing_slots.append("天辉 Pick")
                if any(x is None for x in rad_bans): missing_slots.append("天辉 Ban")
                if any(x is None for x in dire_picks): missing_slots.append("夜魇 Pick")
                if any(x is None for x in dire_bans): missing_slots.append("夜魇 Ban")
                
                if missing_slots:
                    st.error(f"录入未完成！以下区域存在未选择的英雄: {', '.join(missing_slots)}。")
                else:
                    is_rad = (my_side == "Radiant (天辉)")
                    is_win = (result == "Win (胜)")
                    league_id_val = league_map[selected_league] if not is_scrim else None
                    
                    # Generate ID
                    prefix = "scrim" if is_scrim else "manual"
                    match_id_gen = f"{prefix}_{uuid.uuid4().hex[:8]}"
                    
                    try:
                        # Determine First Pick Logic
                        is_rad_fp = (first_pick_team == "Radiant (天辉)")
                        
                        # Standard 7.36+ CM Order Approximation
                        # Total 24 Steps (0-23)
                        # Logic: We just map the 5 Picks and 7 Bans to specific indices
                        # This is an APPROXIMATION to make the visualizer work reasonably well.
                        
                        # If Radiant First Pick:
                        # Phase 1 Bans (4): R(0), D(1), R(2), D(3) -> Rad Bans 0,1 / Dire Bans 0,1
                        # Phase 1 Picks (2): R(4), D(5) -> Rad Pick 0 / Dire Pick 0
                        # Phase 2 Bans (6): R(6), D(7), R(8), D(9), R(10), D(11) -> Rad Bans 2,3,4 / Dire Bans 2,3,4
                        # Phase 2 Picks (4): D(12), R(13), D(14), R(15) -> Dire Picks 1,2 / Rad Picks 1,2
                        # Phase 3 Bans (4): D(16), R(17), D(18), R(19) -> Dire Bans 5,6 / Rad Bans 5,6
                        # Phase 3 Picks (2): D(20), R(21) -> Dire Pick 3 / Rad Pick 3 (Wait, total 5 picks)
                        
                        # Let's define a mapping table for 5 picks + 7 bans per side
                        
                        if is_rad_fp:
                            # Map input list index -> Global Order (0-23)
                            rad_ban_map = [0, 2, 6, 8, 10, 17, 19]
                            dire_ban_map = [1, 3, 7, 9, 11, 16, 18]
                            
                            rad_pick_map = [4, 13, 15, 21, 23] 
                            dire_pick_map = [5, 12, 14, 20, 22] # 23? No total 24 steps. 
                            # Last pick is 23 (24th step).
                            
                            # Verify total unique: 
                            # R_Ban: 0,2,6,8,10,17,19 (7)
                            # D_Ban: 1,3,7,9,11,16,18 (7)
                            # R_Pick: 4,13,15,21,23 (5)
                            # D_Pick: 5,12,14,20,22 (5)
                            # All unique in 0-23? Yes.
                        else:
                            # Dire First Pick (Just swap Rad/Dire maps)
                            dire_ban_map = [0, 2, 6, 8, 10, 17, 19]
                            rad_ban_map = [1, 3, 7, 9, 11, 16, 18]
                            
                            dire_pick_map = [4, 13, 15, 21, 23]
                            rad_pick_map = [5, 12, 14, 20, 22]

                        new_match = Match(
                            match_id=match_id_gen,
                            team_name=my_team,
                            opponent_name=opp_team,
                            is_scrim=is_scrim,
                            league_id=league_id_val,
                            match_time=datetime.combine(scrim_date, datetime.min.time()),
                            is_radiant=is_rad,
                            win=is_win,
                            first_pick=is_rad_fp 
                        )
                        db.add(new_match)
                        db.flush()
                        
                        def save_pb(hids, order_map, is_pick, team_side):
                            for idx, hid in enumerate(hids):
                                # Safety for map length
                                if idx < len(order_map):
                                    db.add(PickBan(
                                        match_id=new_match.id,
                                        hero_id=hid,
                                        is_pick=is_pick,
                                        order=order_map[idx],
                                        team_side=team_side
                                    ))
                        
                        save_pb(rad_picks, rad_pick_map, True, 0)
                        save_pb(rad_bans, rad_ban_map, False, 0)
                        save_pb(dire_picks, dire_pick_map, True, 1)
                        save_pb(dire_bans, dire_ban_map, False, 1)
                        
                        db.commit()
                        st.success(f"记录已保存! ID: {match_id_gen} (First Pick: {first_pick_team})")
                        
                    except Exception as e:
                        st.error(f"保存失败: {e}")
                        import traceback
                        st.text(traceback.format_exc())

    db.close()
