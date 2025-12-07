import streamlit as st
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
                new_pos = c1.number_input("常规位置 (Pos)", min_value=0, max_value=5, value=p.default_pos or 0)
                
                # Aliases
                aliases = [str(a.account_id) for a in p.aliases if a.account_id != p.account_id]
                st.text(f"关联小号: {', '.join(aliases) if aliases else '无'}")
                
                new_alias_id = st.text_input("添加关联小号 ID", placeholder="输入小号 ID")
                
                if st.form_submit_button("保存修改 (Save Changes)"):
                    p.name = new_name
                    p.remark = new_remark
                    p.default_pos = new_pos if new_pos > 0 else None
                    
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

    db.close()
