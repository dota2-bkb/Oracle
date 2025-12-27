import streamlit as st
import pandas as pd
from database import get_db
from models import Player, PlayerAlias, Team, PlayerPerformance
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

def show():
    st.title("选手管理 / Player Manager")
    
    db = next(get_db())
    
    # --- Top Actions ---
    c_act1, c_act2 = st.columns(2)
    
    with c_act1:
        if st.button("🛠️ 将当前选手定位应用到历史比赛 (修复位置错误)"):
            with st.spinner("正在修复历史数据..."):
                # 1. Build Map: Account ID -> Default Pos
                # Includes Aliases
                players_with_pos = db.query(Player).filter(Player.default_pos != None).all()
                
                pos_map = {} # acc_id -> pos
                for p in players_with_pos:
                    if p.default_pos and 1 <= p.default_pos <= 5:
                        pos_map[p.account_id] = p.default_pos
                        for alias in p.aliases:
                            pos_map[alias.account_id] = p.default_pos
                
                if not pos_map:
                    st.warning("未配置任何选手的常规位置，请先在下方配置。")
                else:
                    # 2. Update PlayerPerformance
                    # Bulk update is tricky with different values.
                    # We can iterate matches or use SQL CASE?
                    # Given dataset size (thousands?), iterating in Python is acceptable for a "tool".
                    
                    # Optimization: Only fetch PPs where account_id is in map
                    pps_to_update = db.query(PlayerPerformance).filter(
                        PlayerPerformance.account_id.in_(pos_map.keys())
                    ).all()
                    
                    updated_count = 0
                    for pp in pps_to_update:
                        new_pos = pos_map[pp.account_id]
                        if pp.position != new_pos:
                            pp.position = new_pos
                            updated_count += 1
                    
                    db.commit()
                    st.success(f"已基于当前人员配置修复了 {updated_count} 条比赛记录的位置信息！")

    with c_act2:
        if st.button("🔄 根据比赛记录猜测选手位置 (仅参考)"):
            with st.spinner("正在分析比赛记录..."):
                # Logic:
                # 1. Get all players in DB
                # 2. For each player, query PlayerPerformance grouped by position
                # 3. Find mode (most frequent) position
                # 4. Update default_pos
                
                # Optimized:
                # Query: account_id, position, count(*) from PlayerPerformance group by 1, 2
                # Then process in python
                
                results = db.query(
                    PlayerPerformance.account_id, 
                    PlayerPerformance.position, 
                    func.count(PlayerPerformance.id)
                ).filter(PlayerPerformance.position > 0)\
                 .group_by(PlayerPerformance.account_id, PlayerPerformance.position).all()
                
                # Process
                player_pos_counts = {} # {acc_id: {pos: count}}
                for acc_id, pos, count in results:
                    if not acc_id: continue
                    if acc_id not in player_pos_counts:
                        player_pos_counts[acc_id] = {}
                    player_pos_counts[acc_id][pos] = count
                
                updated_count = 0
                for acc_id, counts in player_pos_counts.items():
                    # Find max
                    best_pos = max(counts, key=counts.get)
                    
                    # Update Player
                    # Note: acc_id might be alias. We need to update MASTER player.
                    # Find player by alias or direct
                    
                    # Check direct
                    player = db.query(Player).filter(Player.account_id == acc_id).first()
                    if not player:
                        # Check alias
                        alias = db.query(PlayerAlias).filter(PlayerAlias.account_id == acc_id).first()
                        if alias:
                            player = alias.player
                    
                    if player:
                        # Only update if current is None or we force update?
                        # Let's update if different
                        if player.default_pos != best_pos:
                            player.default_pos = best_pos
                            updated_count += 1
                
                db.commit()
                st.success(f"已更新 {updated_count} 名选手的常规位置！")

    st.divider()

    # --- Search & Filter ---
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        search_query = st.text_input("搜索选手 (ID 或 名字)", placeholder="输入 Account ID 或 Name")
    
    with col2:
        filter_has_team = st.checkbox("仅显示有战队选手", value=True)
    
    with col3:
        # Team Filter
        # Get all team names
        all_teams = db.query(Team).order_by(Team.name).all()
        team_options = {t.name: t.team_id for t in all_teams}
        team_options["全部战队"] = None
        selected_team_label = st.selectbox("筛选战队", options=list(team_options.keys()), index=len(team_options)-1)
        selected_team_id = team_options[selected_team_label]
        
    # Pos Filter
    filter_pos = st.multiselect("筛选位置", [1, 2, 3, 4, 5])

    # --- Query Construction ---
    query = db.query(Player)
    
    if filter_has_team:
        query = query.filter(Player.team_id != None)
    
    if selected_team_id:
        query = query.filter(Player.team_id == selected_team_id)
        # Sort by position for easier reading
        query = query.order_by(Player.default_pos)
        
    if filter_pos:
        query = query.filter(Player.default_pos.in_(filter_pos))

    if search_query:
        # Check if numeric
        if search_query.isdigit():
            acc_id = int(search_query)
            alias_match = db.query(PlayerAlias).filter(PlayerAlias.account_id == acc_id).first()
            if alias_match:
                query = query.filter(Player.id == alias_match.player_id)
            else:
                query = query.filter(Player.account_id == acc_id)
        else:
            query = query.filter(Player.name.contains(search_query))
            
    players = query.limit(50).all()
    
    # --- Player List ---
    st.write(f"显示 {len(players)} 名选手")
    
    for p in players:
        # Determine team name
        team_name = "-"
        if p.team:
            team_name = f"{p.team.name}"
            
        with st.expander(f"{p.name} (ID: {p.account_id}) | {team_name} | Pos {p.default_pos or '?'}"):
            
            # --- Edit Form ---
            with st.form(key=f"edit_player_{p.id}"):
                c1, c2 = st.columns(2)
                new_name = c1.text_input("职业 ID (Standard Name)", value=p.name)
                new_remark = c2.text_input("备注 (Remark)", value=p.remark or "")
                
                # Position Selectbox
                pos_options = [0, 1, 2, 3, 4, 5]
                pos_labels = {0: "无 (-)", 1: "1号位", 2: "2号位", 3: "3号位", 4: "4号位", 5: "5号位"}
                current_pos = p.default_pos if p.default_pos in pos_options else 0
                
                new_pos = c1.selectbox(
                    "常规位置 (Pos)", 
                    options=pos_options, 
                    format_func=lambda x: pos_labels[x],
                    index=pos_options.index(current_pos),
                    key=f"pos_select_{p.id}"
                )
                
                # Team Selection
                # Build team options
                all_teams_list = db.query(Team).order_by(Team.name).all()
                team_map = {t.name: t.team_id for t in all_teams_list}
                team_map["无战队"] = 0
                
                current_team_id = p.team_id or 0
                # Find index
                team_names = list(team_map.keys())
                # Reverse lookup for display
                current_team_name = "无战队"
                if p.team:
                    current_team_name = p.team.name
                
                try:
                    default_idx = team_names.index(current_team_name)
                except ValueError:
                    default_idx = team_names.index("无战队")

                new_team_name = c2.selectbox("所属战队 (Team)", options=team_names, index=default_idx)
                
                # Aliases
                aliases = [str(a.account_id) for a in p.aliases if a.account_id != p.account_id]
                st.text(f"关联小号: {', '.join(aliases) if aliases else '无'}")
                
                new_alias_id = st.text_input("添加关联小号 ID", placeholder="输入小号 ID")
                
                if st.form_submit_button("保存修改 (Save Changes)"):
                    p.name = new_name
                    p.remark = new_remark
                    p.default_pos = new_pos if new_pos > 0 else None
                    
                    # Update Team
                    sel_team_id = team_map.get(new_team_name)
                    p.team_id = sel_team_id if sel_team_id != 0 else None
                    
                    if new_alias_id and new_alias_id.isdigit():
                        aid = int(new_alias_id)
                        existing_alias = db.query(PlayerAlias).filter(PlayerAlias.account_id == aid).first()
                        if existing_alias:
                            if existing_alias.player_id == p.id:
                                st.warning("该 ID 已经是当前选手的关联账号。")
                            else:
                                st.error(f"该 ID 已经被关联到其他选手 (Player ID: {existing_alias.player_id})，请先解除关联。")
                        else:
                            db.add(PlayerAlias(account_id=aid, player_id=p.id))
                            st.success(f"已添加小号 {aid}")
                    
                    db.commit()
                    st.success("已更新选手信息！")
                    st.rerun()

    # --- Add New Player (Manual) ---
    st.divider()
    with st.expander("手动添加新选手 (Add New Player)"):
        with st.form("add_player_form"):
            c1, c2 = st.columns(2)
            add_id = c1.text_input("Account ID (必填)")
            add_name = c2.text_input("职业 ID (Name)")
            
            if st.form_submit_button("添加"):
                if add_id and add_id.isdigit():
                    aid = int(add_id)
                    if db.query(Player).filter(Player.account_id == aid).first():
                        st.error("该 Account ID 已存在。")
                    else:
                        new_p = Player(account_id=aid, name=add_name or f"Player {aid}")
                        db.add(new_p)
                        db.add(PlayerAlias(account_id=aid, player=new_p))
                        db.commit()
                        st.success("添加成功！")
                        st.rerun()
                else:
                    st.error("请输入有效的数字 ID")

    # --- Bulk Edit Team Positions (Export/Import CSV) ---
    st.divider()
    st.subheader("批量战队位置管理 (Bulk Edit)")
    
    with st.expander("导出/导入 战队选手位置配置"):
        st.info("说明：此功能用于批量规整战队选手的常规位置。导出 CSV -> 修改 Pos -> 上传更新。")
        
        # 1. Multi-select teams to export
        all_teams_q = db.query(Team).order_by(Team.name).all()
        team_opts = {t.name: t.team_id for t in all_teams_q}
        
        selected_export_teams = st.multiselect("选择要导出的战队", options=list(team_opts.keys()))
        
        if st.button("生成位置配置 CSV"):
            if not selected_export_teams:
                st.warning("请至少选择一个战队")
            else:
                # Generate DataFrame
                # 按用户要求：只导出选手名字，不导出数字 ID
                # Columns: Team Name, Team ID, Pos 1 Name ... Pos 5 Name
                rows = []
                for t_name in selected_export_teams:
                    tid = team_opts[t_name]
                    # Find players for this team
                    t_players = db.query(Player).filter(Player.team_id == tid).all()
                    
                    # Map pos -> player
                    pos_map = {i: None for i in range(1, 6)}
                    
                    # Heuristic: If multiple players have same default_pos, pick first found
                    for p in t_players:
                        if p.default_pos and 1 <= p.default_pos <= 5:
                            if pos_map[p.default_pos] is None:
                                pos_map[p.default_pos] = p
                    
                    row = {"Team Name": t_name, "Team ID": tid}
                    for i in range(1, 6):
                        p = pos_map[i]
                        row[f"Pos {i} Name"] = p.name if p else ""
                        
                    rows.append(row)
                
                df_export = pd.DataFrame(rows)
                csv = df_export.to_csv(index=False).encode('utf-8')
                
                st.download_button(
                    label="📥 下载位置配置 CSV",
                    data=csv,
                    file_name="team_positions_export.csv",
                    mime="text/csv"
                )
        
        st.markdown("---")
        
        # 2. Import
        uploaded_pos_file = st.file_uploader("上传修改后的 CSV", type=["csv"])
        if uploaded_pos_file and st.button("应用位置更新"):
            try:
                # 使用多种编码尝试读取，兼容 Excel/记事本 保存的 GBK 等编码
                df_new = None
                encodings = ['utf-8', 'gbk', 'gb18030']
                for enc in encodings:
                    try:
                        if hasattr(uploaded_pos_file, 'seek'):
                            uploaded_pos_file.seek(0)
                        df_new = pd.read_csv(uploaded_pos_file, encoding=enc)
                        break
                    except UnicodeDecodeError:
                        continue
                    except Exception as e:
                        print(f"CSV Read Error ({enc}): {e}")
                        continue
                if df_new is None:
                    st.error("无法用常见编码 (utf-8 / gbk / gb18030) 解析 CSV，请检查文件编码。")
                    return
                
                # Validation
                required_cols = ["Team ID"]
                # 现在按名字导入：需要 Pos i Name 列
                for i in range(1, 6):
                    required_cols.append(f"Pos {i} Name")
                
                # Check columns
                if not all(col in df_new.columns for col in required_cols):
                    st.error("CSV 格式不匹配，请确保包含所有必需列 (Team ID, Pos 1 Account ID...)")
                else:
                    updated_count = 0
                    errors = []
                    
                    for _, row in df_new.iterrows():
                        tid = row.get("Team ID")
                        t_name = row.get("Team Name", "Unknown")
                        
                        if pd.isna(tid):
                            continue
                        
                        try:
                            tid = int(tid)
                        except:
                            errors.append(f"无效的 Team ID: {tid}")
                            continue
                            
                        # Process 1-5
                        for i in range(1, 6):
                            col_name = f"Pos {i} Name"
                            p_name = row.get(col_name)
                            
                            # 空值：不修改该位置
                            if pd.isna(p_name) or str(p_name).strip() == "":
                                continue
                            
                            p_name = str(p_name).strip()
                            
                            # 按名字查选手，优先匹配此战队下的选手，其次全局匹配
                            player = db.query(Player).filter(
                                Player.team_id == tid,
                                Player.name == p_name
                            ).first()
                            
                            if not player:
                                player = db.query(Player).filter(Player.name == p_name).first()
                            
                            if not player:
                                errors.append(f"战队 {t_name} Pos {i}: 找不到名为 '{p_name}' 的选手 (跳过)")
                                continue
                            
                            # Update Player
                            player.team_id = tid
                            player.default_pos = i
                            updated_count += 1
                    
                    db.commit()
                    
                    if updated_count > 0:
                        st.success(f"成功更新了 {updated_count} 个位置信息！")
                    
                    if errors:
                        with st.expander("导入过程中的警告/错误", expanded=True):
                            for e in errors:
                                st.warning(e)
                                
            except Exception as e:
                st.error(f"处理 CSV 失败: {e}")

    db.close()
