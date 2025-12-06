import streamlit as st
from database import get_db
from models import Team, Player, League
from services.api_client import OpenDotaClient
from services.hero_manager import HeroManager
from datetime import datetime, timedelta

def show():
    st.title("系统设置 / Settings")
    
    tab1, tab2 = st.tabs(["数据同步 (Sync)", "英雄别名配置 (Hero Config)"])
    
    # --- Tab 1: Sync Logic ---
    with tab1:
        st.markdown("### 活跃数据同步")
        st.info("核心逻辑：根据指定的时间范围，扫描 OpenDota 的近期职业比赛，自动提取并同步活跃的联赛和战队。")
        
        col1, col2 = st.columns(2)
        with col1:
            sync_days = st.number_input("扫描最近多少天?", min_value=7, max_value=1095, value=90, help="扫描过去 N 天内的职业比赛")
        
        if st.button("开始全量扫描同步 (Sync All Active)"):
            db = next(get_db())
            client = OpenDotaClient()
            
            try:
                progress = st.progress(0)
                status = st.empty()
                
                # 1. 准备全量联赛列表 (用于后续匹配 ID 查 Name)
                status.text("正在获取 OpenDota 全量联赛字典...")
                all_leagues_raw = client.fetch_leagues()
                all_leagues_map = {l['leagueid']: l for l in all_leagues_raw}
                
                # 2. 准备全量战队列表
                status.text("正在获取 OpenDota 全量战队字典...")
                all_teams_raw = client.fetch_teams()
                all_teams_map = {t['team_id']: t for t in all_teams_raw}
                
                # 3. 扫描 Pro Matches
                status.text(f"正在扫描最近 {sync_days} 天的职业比赛...")
                
                active_league_ids = set()
                active_team_ids = set()
                
                last_match_id = None
                cutoff_date = datetime.now() - timedelta(days=sync_days)
                
                fetched_count = 0
                
                while True:
                    params = {"limit": 100}
                    if last_match_id:
                        params["less_than_match_id"] = last_match_id
                    
                    matches = client._get("/proMatches", params=params)
                    if not matches:
                        break
                        
                    newest_ts = matches[0]['start_time']
                    oldest_ts = matches[-1]['start_time']
                    oldest_date = datetime.fromtimestamp(oldest_ts)
                    
                    for m in matches:
                        if m.get('leagueid'):
                            active_league_ids.add(m['leagueid'])
                        
                        if m.get('radiant_team_id'): active_team_ids.add(m['radiant_team_id'])
                        if m.get('dire_team_id'): active_team_ids.add(m['dire_team_id'])
                    
                    last_match_id = matches[-1]['match_id']
                    fetched_count += len(matches)
                    
                    status.text(f"已分析 {fetched_count} 场比赛... (追溯至 {oldest_date.strftime('%Y-%m-%d')}) \n发现: {len(active_league_ids)} 个联赛, {len(active_team_ids)} 支战队")
                    
                    if oldest_date < cutoff_date:
                        break
                    
                    # Safety break if too many
                    if fetched_count > 5000:
                        st.warning("为防止 API 超时，已自动停止（达到 5000 场）。建议缩小时间范围。")
                        break
                
                progress.progress(50)
                
                # 4. 保存活跃联赛
                status.text(f"正在入库活跃联赛 (仅保留 premium/professional)...")
                league_count = 0
                skipped_count = 0
                target_tiers = ['premium', 'professional']
                
                for lid in active_league_ids:
                    l_data = all_leagues_map.get(lid)
                    if l_data:
                        # Filter by tier
                        if l_data.get('tier') not in target_tiers:
                            skipped_count += 1
                            continue
                            
                        existing = db.query(League).filter(League.league_id == lid).first()
                        if not existing:
                            existing = League(league_id=lid)
                            db.add(existing)
                        
                        existing.name = l_data.get('name') or f"League {lid}"
                        existing.tier = l_data.get('tier')
                        league_count += 1
                
                db.commit()
                
                # 5. 保存活跃战队
                status.text(f"正在入库 {len(active_team_ids)} 支活跃战队...")
                team_count = 0
                for tid in active_team_ids:
                    t_data = all_teams_map.get(tid)
                    if not t_data:
                        t_data = client.fetch_team_details(tid)
                    
                    if t_data:
                        team = db.query(Team).filter(Team.team_id == tid).first()
                        if not team:
                            team = Team(team_id=tid)
                            db.add(team)
                        
                        team.name = t_data.get('name')
                        team.tag = t_data.get('tag')
                        team.logo_url = t_data.get('logo_url')
                        team_count += 1
                
                # 6. 保存全量职业选手 (Metadata)
                status.text(f"正在同步职业选手数据库 (Metadata)...")
                pro_players = client.fetch_pro_players()
                player_count = 0
                if pro_players:
                    for p in pro_players:
                        pid = p.get('account_id')
                        if not pid: continue
                        
                        existing_p = db.query(Player).filter(Player.account_id == pid).first()
                        if not existing_p:
                            existing_p = Player(account_id=pid)
                            db.add(existing_p)
                        
                        existing_p.name = p.get('name')
                        existing_p.team_id = p.get('team_id')
                        existing_p.fantasy_role = p.get('fantasy_role')
                        existing_p.country_code = p.get('country_code')
                        player_count += 1
                    
                    db.commit()
                
                progress.progress(100)
                
                st.success(f"""
                同步完成！
                - 扫描时间范围: {sync_days} 天
                - 活跃联赛更新: {league_count} 个
                - 活跃战队更新: {team_count} 支
                - 职业选手更新: {player_count} 名
                """)
                
            except Exception as e:
                st.error(f"同步失败: {e}")
            finally:
                db.close()

    # --- Tab 2: Hero Config ---
    with tab2:
        st.write("配置英雄别名 (Slang)。")
        hm = HeroManager()
        csv_data = hm.export_csv()
        st.download_button("下载 CSV", data=csv_data, file_name="heroes_config.csv", mime="text/csv")
        uploaded_file = st.file_uploader("上传 CSV", type=["csv"])
        if uploaded_file and st.button("应用更改"):
            if hm.import_csv(uploaded_file):
                st.success("配置已更新！")
            else:
                st.error("CSV 格式错误")
        st.dataframe(hm.get_all_heroes())
