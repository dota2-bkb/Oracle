import streamlit as st
from datetime import datetime
from services.api_client import OpenDotaClient
from services.data_processor import DataProcessor
from services.hero_manager import HeroManager
from database import get_db
from models import Match, Team, League, PickBan, PlayerPerformance, Player
from sqlalchemy.orm import Session
import uuid
import pandas as pd
from io import BytesIO

def show():
    st.title("数据录入")
    
    db = next(get_db())
    client = OpenDotaClient()
    processor = DataProcessor()
    hm = HeroManager()
    
    tab1, tab2, tab3, tab4 = st.tabs(["批量抓取", "单场抓取", "手动录入", "Excel 导入"])
    
    # --- Tab 1: 批量抓取 ---
    with tab1:
        st.subheader("批量比赛录入")
        
        fetch_mode = st.radio("抓取模式", ["按战队", "按联赛"])
        
        if fetch_mode == "按战队":
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

        elif fetch_mode == "按联赛":
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
                
                if not r_name: r_name = "天辉"
                if not d_name: d_name = "夜魇"
                
                # Duration Check (Expert Filter)
                duration = m.get('duration', 0)
                is_short = duration < 900 # 15 mins
                
                col1, col2, col3, col4 = st.columns([1, 4, 2, 2])
                with col1:
                    # Default unchecked if short game or existing
                    default_val = (not exists) and (not is_short)
                    save = st.checkbox(f"{mid}", value=default_val, key=f"chk_{mid}", disabled=bool(exists))
                with col2:
                    st.text(f"{r_name} vs {d_name}")
                    if is_short:
                        st.caption(f"⚠️ 短时长比赛 ({duration//60} min) - 可能是弃赛/重开")
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
                        
                        # Auto-save Teams
                        for side in ['radiant_team_id', 'dire_team_id']:
                            tid = detail_data.get(side)
                            if tid:
                                t = db.query(Team).filter(Team.team_id == tid).first()
                                if not t:
                                    t_info = client.fetch_team_details(tid)
                                    if t_info:
                                        db.add(Team(team_id=tid, name=t_info.get('name'), tag=t_info.get('tag'), logo_url=t_info.get('logo_url')))
                                        db.commit()

                        # DUAL PERSPECTIVE SAVE
                        if fetch_type == 'team':
                            tid = st.session_state.get('target_team_id')
                            processor.save_match_to_db(db, detail_data, target_team_id=tid)
                            
                            # Also save opponent perspective (Rule #0)
                            opp_tid = m_summary.get('opposing_team_id')
                            if opp_tid:
                                processor.save_match_to_db(db, detail_data, target_team_id=opp_tid)
                                
                        else:
                            processor.save_dual_perspective(db, detail_data)
                            
                        success_count += 1
                        
                    except Exception as e:
                        st.error(f"比赛 {mid} 保存失败: {e}")
                    
                    progress.progress((i + 1) / len(matches_to_save))
                
                st.success(f"操作完成！成功: {success_count}/{len(matches_to_save)}")
                del st.session_state['preview_matches']
                st.rerun()

    # --- Tab 2: 单场抓取 ---
    with tab2:
        st.subheader("单场抓取")
        match_id_input = st.text_input("输入 Match ID", placeholder="例如 7123456789")
        
        teams = db.query(Team).order_by(Team.name).all()
        team_options = {t.name: t.team_id for t in teams}
        team_options["不指定 (自动双向录入)"] = None
        
        selected_team_name = st.selectbox("选择分析视角 (主队)", options=list(team_options.keys()), index=len(team_options)-1, key="single_fetch_team")
        target_team_id = team_options[selected_team_name]
        
        if st.button("抓取并保存"):
            if not match_id_input:
                st.warning("请输入 Match ID")
            else:
                with st.spinner("正在请求 OpenDota API..."):
                    data = client.fetch_match_details(match_id_input)
                    if data and 'error' not in data:
                        try:
                            # Save Teams
                            r_id = data.get('radiant_team_id')
                            if r_id and not db.query(Team).filter(Team.team_id == r_id).first():
                                t_info = client.fetch_team_details(r_id)
                                if t_info: db.add(Team(team_id=r_id, name=t_info.get('name'), tag=t_info.get('tag'), logo_url=t_info.get('logo_url'))); db.commit()
                                    
                            d_id = data.get('dire_team_id')
                            if d_id and not db.query(Team).filter(Team.team_id == d_id).first():
                                t_info = client.fetch_team_details(d_id)
                                if t_info: db.add(Team(team_id=d_id, name=t_info.get('name'), tag=t_info.get('tag'), logo_url=t_info.get('logo_url'))); db.commit()

                            if target_team_id:
                                match_obj = processor.save_match_to_db(db, data, target_team_id=target_team_id)
                                # Also save opponent? Yes, double entry requirement.
                                # Check radiant/dire to find opponent ID
                                if target_team_id == r_id and d_id:
                                    processor.save_match_to_db(db, data, target_team_id=d_id)
                                elif target_team_id == d_id and r_id:
                                    processor.save_match_to_db(db, data, target_team_id=r_id)
                                
                                st.success(f"成功保存: {match_obj.team_name} vs {match_obj.opponent_name} (及对手视角)")
                            else:
                                # Dual Save
                                saved = processor.save_dual_perspective(db, data)
                                st.success(f"成功双向保存: {len(saved)} 条记录")
                                
                        except Exception as e:
                            st.error(f"保存失败: {e}")
                    else:
                        st.error("API 错误")

    # --- Tab 3: 手动录入 (Scrims) ---
    with tab3:
        st.subheader("手动录入")
        
        with st.form("scrim_form"):
            # Row 1: Basic
            c1, c2, c3 = st.columns(3)
            scrim_date = c1.date_input("日期", datetime.today())
            is_scrim = c2.checkbox("标记为训练赛", value=True)
            
            leagues = db.query(League).order_by(League.league_id.desc()).all()
            league_keys = ["无"] + [l.name for l in leagues]
            league_map = {l.name: l.league_id for l in leagues}
            league_map["无"] = None
            
            selected_league = c3.selectbox("联赛", league_keys, index=0)
            
            # Row 2: Teams & Result
            all_teams = db.query(Team).order_by(Team.name).all()
            team_opts = [t.name for t in all_teams] + ["未知/自定义"]
            
            c4, c5, c6, c7 = st.columns(4)
            my_team = c4.selectbox("我方队伍", team_opts, index=0)
            opp_team = c5.selectbox("对方队伍", team_opts, index=1 if len(team_opts)>1 else 0)
            
            my_side = c6.radio("我方阵营", ["天辉 (Radiant)", "夜魇 (Dire)"])
            result = c7.radio("比赛结果", ["胜 (Win)", "负 (Loss)"])
            
            first_pick_team = st.radio("先 Ban/Pick 阵营", ["天辉 (Radiant)", "夜魇 (Dire)"], horizontal=True)

            st.divider()
            
            heroes = hm.get_all_heroes()
            # Use CN name for sorting
            heroes.sort(key=lambda x: x.get('cn_name') or "")
            hero_opts = {f"{h['cn_name']} ({h['en_name']})": h['id'] for h in heroes}
            
            def hero_select(key, label, placeholder_text):
                box_options = [placeholder_text] + list(hero_opts.keys())
                selected = st.selectbox(label, box_options, key=key, label_visibility="collapsed")
                if selected == placeholder_text: return None
                return hero_opts[selected]

            st.caption("🟢 天辉 Pick")
            c_rp = st.columns(5)
            rad_picks = [hero_select(f"rp_{i}", f"Pick {i+1}", f"P{i+1}") for i in range(5)]
            
            st.caption("🚫 天辉 Ban")
            c_rb = st.columns(7)
            rad_bans = [hero_select(f"rb_{i}", f"Ban {i+1}", f"B{i+1}") for i in range(7)]
            
            st.caption("🔴 夜魇 Pick")
            c_dp = st.columns(5)
            dire_picks = [hero_select(f"dp_{i}", f"Pick {i+1}", f"P{i+1}") for i in range(5)]
            
            st.caption("🚫 夜魇 Ban")
            c_db = st.columns(7)
            dire_bans = [hero_select(f"db_{i}", f"Ban {i+1}", f"B{i+1}") for i in range(7)]
            
            submitted = st.form_submit_button("保存记录")
            
            if submitted:
                # Validation & Save Logic (Same as before)
                # Simplified for brevity but functional
                is_rad = (my_side == "天辉 (Radiant)")
                is_win = (result == "胜 (Win)")
                league_id_val = league_map[selected_league] if not is_scrim else None
                
                prefix = "scrim" if is_scrim else "manual"
                match_id_gen = f"{prefix}_{uuid.uuid4().hex[:8]}"
                
                is_rad_fp = (first_pick_team == "天辉 (Radiant)")
                
                # Maps
                if is_rad_fp:
                    rad_ban_map = [0, 2, 6, 8, 10, 17, 19]
                    dire_ban_map = [1, 3, 7, 9, 11, 16, 18]
                    rad_pick_map = [4, 13, 15, 21, 23] 
                    dire_pick_map = [5, 12, 14, 20, 22]
                else:
                    dire_ban_map = [0, 2, 6, 8, 10, 17, 19]
                    rad_ban_map = [1, 3, 7, 9, 11, 16, 18]
                    dire_pick_map = [4, 13, 15, 21, 23]
                    rad_pick_map = [5, 12, 14, 20, 22]

                try:
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
                            if hid and idx < len(order_map):
                                db.add(PickBan(match_id=new_match.id, hero_id=hid, is_pick=is_pick, order=order_map[idx], team_side=team_side))
                    
                    save_pb(rad_picks, rad_pick_map, True, 0)
                    save_pb(rad_bans, rad_ban_map, False, 0)
                    save_pb(dire_picks, dire_pick_map, True, 1)
                    save_pb(dire_bans, dire_ban_map, False, 1)
                    
                    db.commit()
                    st.success(f"手动记录已保存! ID: {match_id_gen}")
                except Exception as e:
                    st.error(f"错误: {e}")

    # --- Tab 4: Excel Import ---
    with tab4:
        st.subheader("Excel 导入")
        
        # Template Generator
        st.write("1. 下载模版")
        
        def generate_template():
            # Translate Headers
            df_tpl = pd.DataFrame(columns=[
                "日期 (YYYY-MM-DD)", "联赛名称", "我方队伍", "对方队伍", "我方阵营 (天辉/夜魇)", "比赛结果 (胜/负)", "先选阵营 (天辉/夜魇)",
                "天辉 Pick 1", "天辉 Pick 2", "天辉 Pick 3", "天辉 Pick 4", "天辉 Pick 5",
                "天辉 Ban 1", "天辉 Ban 2", "天辉 Ban 3", "天辉 Ban 4", "天辉 Ban 5", "天辉 Ban 6", "天辉 Ban 7",
                "夜魇 Pick 1", "夜魇 Pick 2", "夜魇 Pick 3", "夜魇 Pick 4", "夜魇 Pick 5",
                "夜魇 Ban 1", "夜魇 Ban 2", "夜魇 Ban 3", "夜魇 Ban 4", "夜魇 Ban 5", "夜魇 Ban 6", "夜魇 Ban 7"
            ])
            # Add example row (translated)
            df_tpl.loc[0] = [
                datetime.today().strftime('%Y-%m-%d'), "DreamLeague", "Team A", "Team B", "天辉", "胜", "天辉",
                "帕吉", "水晶室女", "宙斯", "玛尔斯", "莉娜",
                "工程师", "狙击手", "祈求者", "斧王", "祸乱之源", "陈", "末日使者",
                "斯温", "小小", "昆卡", "潮汐猎人", "斯拉达",
                "巫妖", "莱恩", "巫医", "戴泽", "神谕者", "艾欧", "帕克"
            ]
            return df_tpl
            
        df_template = generate_template()
        
        # Convert to buffer
        buffer = BytesIO()
        try:
            # Try Excel first
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_template.to_excel(writer, index=False)
            file_ext = ".xlsx"
            mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        except:
            # Fallback to CSV
            buffer = BytesIO()
            df_template.to_csv(buffer, index=False)
            file_ext = ".csv"
            mime_type = "text/csv"
            st.caption("⚠️ 检测到未安装 openpyxl，使用 CSV 格式模版。")
            
        st.download_button(
            label=f"下载模版 ({file_ext})",
            data=buffer.getvalue(),
            file_name=f"match_import_template{file_ext}",
            mime=mime_type
        )
        
        st.divider()
        
        st.write("2. 上传文件")
        uploaded_file = st.file_uploader("上传填好的 Excel/CSV", type=["xlsx", "xls", "csv"])
        
        if uploaded_file:
            try:
                if uploaded_file.name.endswith('.csv'):
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file)
                
                st.write("预览数据:")
                st.dataframe(df.head())
                
                if st.button("确认并导入数据库"):
                    # Processing Logic
                    # Need to map Hero Names to IDs
                    heroes = hm.get_all_heroes()
                    # Create a map: Name -> ID, CN_Name -> ID, En_Name -> ID, Slang -> ID?
                    # For now, strict match on Name (CN or EN)
                    name_map = {}
                    for h in heroes:
                        name_map[h['en_name'].lower()] = h['id']
                        if h.get('cn_name'):
                            name_map[h['cn_name']] = h['id']
                    
                    success_count = 0
                    errors = []
                    
                    for idx, row in df.iterrows():
                        try:
                            # Parse Basic
                            m_date = pd.to_datetime(row["日期 (YYYY-MM-DD)"])
                            league_name = row["联赛名称"]
                            # Find league ID if exists
                            league_obj = db.query(League).filter(League.name == league_name).first()
                            lid = league_obj.league_id if league_obj else None
                            
                            team_name = row["我方队伍"]
                            opp_name = row["对方队伍"]
                            
                            # Robust parsing of side/result/firstpick
                            side_str = str(row["我方阵营 (天辉/夜魇)"]).strip()
                            is_rad = ("天辉" in side_str or "Radiant" in side_str)
                            
                            res_str = str(row["比赛结果 (胜/负)"]).strip()
                            win = ("胜" in res_str or "Win" in res_str)
                            
                            fp_str = str(row["先选阵营 (天辉/夜魇)"]).strip()
                            fp_rad = ("天辉" in fp_str or "Radiant" in fp_str)
                            
                            # Create Match
                            mid = f"excel_{uuid.uuid4().hex[:8]}"
                            new_match = Match(
                                match_id=mid,
                                team_name=team_name,
                                opponent_name=opp_name,
                                is_scrim=True, # Assume manual import is scrim
                                league_id=lid,
                                match_time=m_date,
                                is_radiant=is_rad,
                                win=win,
                                first_pick=fp_rad
                            )
                            db.add(new_match)
                            db.flush()
                            
                            # Parse BP
                            # Helper to get ID
                            def get_hid(val):
                                if not val or pd.isna(val): return None
                                val = str(val).strip()
                                # Check map
                                if val.lower() in name_map: return name_map[val.lower()]
                                if val in name_map: return name_map[val]
                                return None
                                
                            # Order Maps (Standard)
                            if fp_rad:
                                rad_ban_map = [0, 2, 6, 8, 10, 17, 19]
                                dire_ban_map = [1, 3, 7, 9, 11, 16, 18]
                                rad_pick_map = [4, 13, 15, 21, 23] 
                                dire_pick_map = [5, 12, 14, 20, 22]
                            else:
                                dire_ban_map = [0, 2, 6, 8, 10, 17, 19]
                                rad_ban_map = [1, 3, 7, 9, 11, 16, 18]
                                dire_pick_map = [4, 13, 15, 21, 23]
                                rad_pick_map = [5, 12, 14, 20, 22]

                            def save_col_list(cols, order_map, is_pick, side):
                                for i, col in enumerate(cols):
                                    if i < len(order_map):
                                        hid = get_hid(row.get(col))
                                        if hid:
                                            db.add(PickBan(match_id=new_match.id, hero_id=hid, is_pick=is_pick, order=order_map[i], team_side=side))

                            save_col_list([f"天辉 Pick {i}" for i in range(1,6)], rad_pick_map, True, 0)
                            save_col_list([f"天辉 Ban {i}" for i in range(1,8)], rad_ban_map, False, 0)
                            save_col_list([f"夜魇 Pick {i}" for i in range(1,6)], dire_pick_map, True, 1)
                            save_col_list([f"夜魇 Ban {i}" for i in range(1,8)], dire_ban_map, False, 1)
                            
                            success_count += 1
                            
                        except Exception as e:
                            errors.append(f"第 {idx+1} 行错误: {e}")
                    
                    db.commit()
                    st.success(f"导入完成: {success_count} 成功")
                    if errors:
                        st.error(f"失败: {len(errors)} 行")
                        with st.expander("错误详情"):
                            for err in errors: st.write(err)
                            
            except Exception as e:
                st.error(f"文件解析失败: {e}")

    db.close()
