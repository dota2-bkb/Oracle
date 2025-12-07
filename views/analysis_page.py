import streamlit as st
from database import get_db
from models import Match, Team, PlayerPerformance, Player, PickBan, League, PlayerAlias
from services.hero_manager import HeroManager
from services.patch_manager import PatchManager
from views.components import render_bp_visual, generate_bp_image, generate_bp_grid_image
from sqlalchemy import desc, func, or_
import pandas as pd
from datetime import datetime, timedelta
from io import BytesIO
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

# --- Helper Function for Statistics Sheet ---
def create_shared_stats_sheet(wb, matches, db, hm):
    ws_stats = wb.create_sheet("统计数据")
    
    # 3.1 Win Rates
    total = len(matches)
    if total > 0:
        wins = sum(1 for m in matches if m.win)
        
        rad_m = [m for m in matches if m.is_radiant]
        rad_wins = sum(1 for m in rad_m if m.win)
        
        dire_m = [m for m in matches if not m.is_radiant]
        dire_wins = sum(1 for m in dire_m if m.win)
        
        fp_m = [m for m in matches if m.first_pick]
        fp_wins = sum(1 for m in fp_m if m.win)
        
        sp_m = [m for m in matches if not m.first_pick]
        sp_wins = sum(1 for m in sp_m if m.win)
        
        stats_data = [
            ["统计项", "场次", "胜场", "胜率"],
            ["总计", total, wins, f"{wins/total:.1%}"],
            ["天辉", len(rad_m), rad_wins, f"{rad_wins/len(rad_m):.1%}" if rad_m else "0%"],
            ["夜魇", len(dire_m), dire_wins, f"{dire_wins/len(dire_m):.1%}" if dire_m else "0%"],
            ["先选", len(fp_m), fp_wins, f"{fp_wins/len(fp_m):.1%}" if fp_m else "0%"],
            ["后选", len(sp_m), sp_wins, f"{sp_wins/len(sp_m):.1%}" if sp_m else "0%"]
        ]
        
        for r_idx, row_data in enumerate(stats_data, start=1):
            for c_idx, val in enumerate(row_data, start=1):
                cell = ws_stats.cell(row=r_idx, column=c_idx, value=val)
                if r_idx == 1: cell.font = Font(bold=True)

    # 3.2 Top 10 Common Heroes & Combinations
    ws_stats.cell(row=8, column=1, value="常用英雄及最佳搭档 (Top 10)").font = Font(bold=True)
    # Update Header with Win Rate for partners
    ws_stats.append(["排名", "英雄", "出场次数", "胜率", "最佳搭档1", "场次", "胜率", "最佳搭档2", "场次", "胜率", "最佳搭档3", "场次", "胜率"])
    
    # Calc Logic
    pick_counts = {}
    hero_wins = {}
    hero_partners = {} # hid -> {partner_id: count}
    
    for m in matches:
        my_side = 0 if m.is_radiant else 1
        my_picks = [pb.hero_id for pb in m.pick_bans if pb.is_pick and pb.team_side == my_side]
        
        for hid in my_picks:
            pick_counts[hid] = pick_counts.get(hid, 0) + 1
            if m.win:
                hero_wins[hid] = hero_wins.get(hid, 0) + 1
                
            if hid not in hero_partners: hero_partners[hid] = {}
            for pid in my_picks:
                if hid != pid:
                    hero_partners[hid][pid] = hero_partners[hid].get(pid, 0) + 1
                    
    sorted_heroes = sorted(pick_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    
    start_row = 10
    for i, (hid, count) in enumerate(sorted_heroes, start=1):
        h_data = hm.get_hero(hid)
        h_name = h_data.get('slang') or h_data.get('cn_name')
        wr = hero_wins.get(hid, 0) / count
        
        row_vals = [i, h_name, count, f"{wr:.1%}"]
        
        # Partners
        partners = hero_partners.get(hid, {})
        # Calculate win rates for partners
        partner_stats = []
        for pid, p_count in partners.items():
            # Count wins where both hid and pid were on My Team
            wins_with_partner = 0
            for m in matches:
                my_side = 0 if m.is_radiant else 1
                my_picks = [pb.hero_id for pb in m.pick_bans if pb.is_pick and pb.team_side == my_side]
                if hid in my_picks and pid in my_picks:
                    if m.win:
                        wins_with_partner += 1
            
            p_wr = wins_with_partner / p_count if p_count > 0 else 0
            partner_stats.append((pid, p_count, p_wr))

        sorted_partners = sorted(partner_stats, key=lambda x: x[1], reverse=True)[:3]
        
        for pid, p_count, p_wr in sorted_partners:
            p_data = hm.get_hero(pid)
            p_name = p_data.get('slang') or p_data.get('cn_name')
            row_vals.extend([p_name, p_count, f"{p_wr:.1%}"])
            
        # Write Row
        for col, val in enumerate(row_vals, start=1):
            ws_stats.cell(row=start_row + i - 1, column=col, value=val)

    # 3.3 Signature Heroes by Position (1-5) - VERTICAL LAYOUT
    ws_stats.cell(row=start_row + 12, column=1, value="各位置绝活列表").font = Font(bold=True)
    
    # Identify Main Players
    pos_player_counts = {i: {} for i in range(1, 6)}
    for m in matches: # Use all matches passed in
        my_side = 0 if m.is_radiant else 1
        my_ps = [p for p in m.players if p.team_side == my_side]
        for p in my_ps:
            if p.position and 1 <= p.position <= 5 and p.account_id:
                pos_player_counts[p.position][p.account_id] = pos_player_counts[p.position].get(p.account_id, 0) + 1
    
    main_players = {}
    for pos, counts in pos_player_counts.items():
        if counts:
            main_players[pos] = max(counts, key=counts.get)
            
    base_r = start_row + 13
    # Vertical Layout: 5 Columns (one per position)
    
    for pos in range(1, 6):
        # Calculate column offset for each position (3 columns wide per position + 1 gap)
        col_offset = 1 + (pos - 1) * 4 
        
        r = base_r
        ws_stats.cell(row=r, column=col_offset, value=f"{pos}号位").font = Font(bold=True)
        r += 1
        
        acc_id = main_players.get(pos)
        
        if not acc_id:
            ws_stats.cell(row=r, column=col_offset, value="未识别")
            continue
            
        # Get Name
        alias = db.query(PlayerAlias).filter(PlayerAlias.account_id == acc_id).first()
        p_info = db.query(Player).filter(Player.account_id == acc_id).first()
        p_name = "未知"
        if alias and alias.player: p_name = alias.player.name
        elif p_info: p_name = p_info.name
        else: p_name = str(acc_id)
        
        ws_stats.cell(row=r, column=col_offset, value=p_name).font = Font(bold=True, color="0000FF")
        r += 1
        
        # Headers for this player
        ws_stats.cell(row=r, column=col_offset, value="英雄")
        ws_stats.cell(row=r, column=col_offset+1, value="场次")
        ws_stats.cell(row=r, column=col_offset+2, value="胜率")
        r += 1
        
        # Get Top Heroes for this player in these matches
        p_heroes = {} # hid -> {picks, wins}
        for m in matches:
             p_rec = next((p for p in m.players if p.account_id == acc_id), None)
             if p_rec:
                 hid = p_rec.hero_id
                 if hid not in p_heroes: p_heroes[hid] = {'picks': 0, 'wins': 0}
                 p_heroes[hid]['picks'] += 1
                 
                 # Check win
                 radiant_won = (m.is_radiant == m.win)
                 player_won = (p_rec.team_side == 0 and radiant_won) or (p_rec.team_side == 1 and not radiant_won)
                 if player_won:
                     p_heroes[hid]['wins'] += 1

        sorted_ph = sorted(p_heroes.items(), key=lambda x: x[1]['picks'], reverse=True)[:5]
        
        for hid, stats in sorted_ph:
            h_data = hm.get_hero(hid)
            h_name = h_data.get('slang') or h_data.get('cn_name')
            cnt = stats['picks']
            wr = stats['wins'] / cnt if cnt > 0 else 0
            
            ws_stats.cell(row=r, column=col_offset, value=h_name)
            ws_stats.cell(row=r, column=col_offset+1, value=cnt)
            ws_stats.cell(row=r, column=col_offset+2, value=f"{wr:.1%}")
            r += 1

def generate_detailed_excel_export(matches, team_name, db, hm):
    """
    Template 1: Detailed Match & Stats
    """
    wb = Workbook()
    
    # Remove default sheet
    default_sheet = wb.active
    wb.remove(default_sheet)
    
    # Sort matches by time ascending (Old -> New) for the horizontal layout
    # User said: "left to right sequentially increasing time"
    matches_asc = sorted(matches, key=lambda m: m.match_time)
    
    # --- Helper to create Match Sheet ---
    def create_match_sheet(sheet_name, filter_func):
        ws = wb.create_sheet(sheet_name)
        filtered_matches = [m for m in matches_asc if filter_func(m)]
        
        if not filtered_matches:
            ws.cell(row=1, column=1, value="无符合条件的比赛数据")
            return

        # Set Row Headers
        headers = ["比赛ID", "日期", "联赛", "天辉队伍", "夜魇队伍", "获胜方", "BP详情"]
        for r, header in enumerate(headers, start=1):
            cell = ws.cell(row=r, column=1, value=header)
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal='center', vertical='center')
            
        # Set Row Heights
        ws.row_dimensions[7].height = 200 # Approx height for BP image (adjust as needed)
        ws.column_dimensions['A'].width = 15

        for idx, m in enumerate(filtered_matches):
            col_idx = idx + 2 # Start from Column B
            col_letter = get_column_letter(col_idx)
            ws.column_dimensions[col_letter].width = 50 # Width for BP image

            # 1. Match ID
            ws.cell(row=1, column=col_idx, value=str(m.match_id)).alignment = Alignment(horizontal='center')
            
            # 2. Date
            ws.cell(row=2, column=col_idx, value=m.match_time.strftime('%Y-%m-%d')).alignment = Alignment(horizontal='center')
            
            # 3. League (Lazy Load name)
            l_name = "未知联赛"
            if m.league_id:
                lg = db.query(League).filter(League.league_id == m.league_id).first()
                if lg: l_name = lg.name
            ws.cell(row=3, column=col_idx, value=l_name).alignment = Alignment(horizontal='center', wrap_text=True)

            # 4. Radiant
            r_name = m.team_name if m.is_radiant else m.opponent_name
            ws.cell(row=4, column=col_idx, value=r_name).alignment = Alignment(horizontal='center')
            
            # 5. Dire
            d_name = m.opponent_name if m.is_radiant else m.team_name
            ws.cell(row=5, column=col_idx, value=d_name).alignment = Alignment(horizontal='center')
            
            # 6. Winner (With crown)
            winner_name = m.team_name if m.win else m.opponent_name
            ws.cell(row=6, column=col_idx, value=f"👑 {winner_name}").alignment = Alignment(horizontal='center')
            
            # 7. BP Image
            # Determine params for generation
            rad_name = m.team_name if m.is_radiant else m.opponent_name
            dire_name = m.opponent_name if m.is_radiant else m.team_name
            is_radiant_first = (m.is_radiant == m.first_pick)
            
            # Add winner mark to team name passed to image gen?
            # User requirement: "BP图片中谁获胜了需要文字中添加信息"
            # We modify the names passed to the image generator
            rad_disp = f"👑 {rad_name}" if (m.is_radiant == m.win) else rad_name
            dire_disp = f"👑 {dire_name}" if (m.is_radiant != m.win) else dire_name
            
            try:
                img_pil = generate_bp_image(m.pick_bans, rad_disp, dire_disp, hm, first_pick_radiant=is_radiant_first)
                if img_pil:
                    # Scaling
                    w_target = 300
                    h_target = int(w_target * (img_pil.height / img_pil.width))
                    
                    img_resized = img_pil.resize((w_target, h_target))
                    
                    # Convert to Bytes for OpenPyXL
                    img_byte_arr = BytesIO()
                    img_resized.save(img_byte_arr, format='PNG')
                    img_byte_arr.seek(0)
                    
                    xl_img = XLImage(img_byte_arr)
                    
                    # Anchor to cell
                    ws.add_image(xl_img, f"{col_letter}7")
                    
                    ws.row_dimensions[7].height = h_target * 0.75
            except Exception as e:
                print(f"Error generating image for excel: {e}")
                ws.cell(row=7, column=col_idx, value="图片生成失败")

    # Sheet 1: Analyzed Team First Pick
    create_match_sheet(f"{team_name}-先选", lambda m: m.first_pick)
    
    # Sheet 2: Analyzed Team Second Pick
    create_match_sheet(f"{team_name}-后选", lambda m: not m.first_pick)
    
    # --- Sheet 3: 统计信息 (Stats) ---
    create_shared_stats_sheet(wb, matches, db, hm)

    output = BytesIO()
    wb.save(output)
    return output.getvalue()

def generate_template_2(matches, team_name, db, hm):
    """
    Template 2: Grid Style BP Image (Vertical List, No Text, Original Width)
    """
    wb = Workbook()
    
    # Remove default sheet
    default_sheet = wb.active
    wb.remove(default_sheet)
    
    # Sort matches by time ascending
    matches_asc = sorted(matches, key=lambda m: m.match_time)
    
    # --- Helper to create Match Sheet ---
    def create_match_sheet(sheet_name, filter_func):
        ws = wb.create_sheet(sheet_name)
        filtered_matches = [m for m in matches_asc if filter_func(m)]
        
        # Header
        ws.cell(row=1, column=1, value=sheet_name).font = Font(bold=True, size=14)
        
        if not filtered_matches:
            ws.cell(row=2, column=1, value="无符合条件的比赛数据")
            return

        # Set Column A Width to accommodate image width
        # Original width ~1280px. 50% = 640px. Excel width ~90
        ws.column_dimensions['A'].width = 90

        for idx, m in enumerate(filtered_matches):
            row_idx = idx + 2 # Start from row 2 (row 1 is header)
            
            # --- Generate Grid Image ---
            # Analyzed Team on LEFT
            left_is_radiant = m.is_radiant
            left_team_name = m.team_name
            right_team_name = m.opponent_name
            
            # Winner logic
            winner_is_left = m.win 
            
            # First Pick logic
            left_is_first_pick = m.first_pick
            
            try:
                img_pil = generate_bp_grid_image(
                    m.pick_bans, 
                    left_team_name, right_team_name, 
                    hm, 
                    left_is_radiant=left_is_radiant,
                    left_is_first_pick=left_is_first_pick,
                    winner_is_left=winner_is_left
                )
                
                if img_pil:
                    # Resize to 50%
                    new_w = int(img_pil.width * 0.5)
                    new_h = int(img_pil.height * 0.5)
                    img_resized = img_pil.resize((new_w, new_h))
                    
                    img_byte_arr = BytesIO()
                    img_resized.save(img_byte_arr, format='PNG')
                    img_byte_arr.seek(0)
                    
                    xl_img = XLImage(img_byte_arr)
                    ws.add_image(xl_img, f"A{row_idx}")
                    
                    # Set Row Height
                    ws.row_dimensions[row_idx].height = new_h * 0.75
                    
            except Exception as e:
                print(f"Error generating grid image: {e}")
                ws.cell(row=row_idx, column=1, value="图片生成失败")

    # Sheet 1: Analyzed Team First Pick
    create_match_sheet(f"{team_name}-先选", lambda m: m.first_pick)
    
    # Sheet 2: Analyzed Team Second Pick
    create_match_sheet(f"{team_name}-后选", lambda m: not m.first_pick)
    
    # --- Sheet 3: 统计信息 (Stats) ---
    create_shared_stats_sheet(wb, matches, db, hm)

    output = BytesIO()
    wb.save(output)
    return output.getvalue()

def generate_template_3(matches, team_name, db, hm):
    """
    Template 3: Pure Text Log (Detailed BP & Positions)
    """
    wb = Workbook()
    # Default sheet
    ws = wb.active
    ws.title = "战绩详情"
    
    # 1. Styles
    fill_yellow = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
    fill_green  = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid") # Light Green
    fill_blue   = PatternFill(start_color="ADD8E6", end_color="ADD8E6", fill_type="solid") # Light Blue (Win)
    fill_red    = PatternFill(start_color="FFC0CB", end_color="FFC0CB", fill_type="solid") # Pink (Loss)
    
    font_header = Font(bold=True)
    alignment_center = Alignment(horizontal='center', vertical='center')
    border_thin = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))

    # 2. Headers
    # Groups: [Meta 4] [My Team 5] [Opponent 1+5] [Bans]
    
    # Row 1: High Level Headers
    ws.merge_cells('A1:D1') # Meta
    ws.cell(row=1, column=1, value="比赛信息").alignment = alignment_center
    
    ws.merge_cells('E1:I1') # My Team
    ws.cell(row=1, column=5, value=team_name).alignment = alignment_center
    ws.cell(row=1, column=5).font = Font(bold=True, size=12)
    
    ws.merge_cells('J1:O1') # Opponent
    ws.cell(row=1, column=10, value="对手").alignment = alignment_center
    
    # FP Bans: 7 columns (P to V)
    ws.merge_cells('P1:V1') 
    ws.cell(row=1, column=16, value="1选方Ban").alignment = alignment_center
    ws.cell(row=1, column=16).fill = fill_yellow
    
    # SP Bans: 7 columns (W to AC)
    ws.merge_cells('W1:AC1') 
    ws.cell(row=1, column=23, value="2选方Ban").alignment = alignment_center
    ws.cell(row=1, column=23).fill = fill_blue 

    # Row 2: Detail Headers
    headers = [
        "编号", "时间", "对手", "胜负", # Meta
        "1", "2", "3", "4", "5", # My Team Pos
        "阵营", "1号位", "2号位", "3号位", "4号位", "5号位", # Opponent
        "Ban1", "Ban2", "Ban3", "Ban4", "Ban5", "Ban6", "Ban7", # FP Bans
        "Ban1", "Ban2", "Ban3", "Ban4", "Ban5", "Ban6", "Ban7"  # SP Bans
    ]
    
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=2, column=i, value=h)
        c.font = font_header
        c.alignment = alignment_center
        c.border = border_thin

    # 3. Data Rows
    # Using 'matches' which is typically passed as Descending time (Latest first).
    
    # Global Order Constants for Coloring
    # DOTA 2 (Current Captains Mode - or user approximation)
    # Pick Orders (1-based Global):
    # FP Picks: 9 (1st), 13, 16, 17, 24
    # SP Picks: 8 (1st), 14, 15, 18, 23
    #
    # User Logic:
    # "1选方1选" -> FP Team's 1st Pick (Order 9) -> Yellow
    # "对方counter 1 2选" -> Opponent's 1st & 2nd Pick
    #   If Opponent is SP: Orders 8, 14 -> Green
    #   If Opponent is FP (My Team is SP): Orders 9, 13 -> Green
    
    # Correction per user request:
    # "1 选人高亮没有做：每场比赛 第8手黄色格子 第9 13手绿色格子"
    # Wait, if User says Order 8 is Yellow, then Order 8 must be considered "1选" (First Pick of Phase).
    # In our system, Order 8 is SP's first pick. Order 9 is FP's first pick.
    # User might be using a system where Order 8 is the FIRST pick of the draft?
    # Standard Dota 2: First Pick Team picks at 8? No, at 5, 8?
    # Let's strictly follow User's Explicit Instruction:
    # "第8手黄色格子" -> Order 8 Yellow.
    # "第9 13手绿色格子" -> Order 9, 13 Green.
    
    COLOR_YELLOW_PICK_ORDER = 8
    COLOR_GREEN_PICK_ORDERS = [9, 13]
    
    # Ban Colors:
    # "1 4 7 手黄色 2 3 5 6 手绿色"
    COLOR_YELLOW_BAN_ORDERS = [1, 4, 7]
    COLOR_GREEN_BAN_ORDERS = [2, 3, 5, 6]

    row_idx = 3
    for idx, m in enumerate(matches, start=1):
        # A: Index
        ws.cell(row=row_idx, column=1, value=idx).border = border_thin
        
        # B: Time
        ws.cell(row=row_idx, column=2, value=m.match_time.strftime('%m-%d')).border = border_thin
        
        # C: Opponent
        ws.cell(row=row_idx, column=3, value=m.opponent_name).border = border_thin
        
        # D: Result
        res_str = "胜" if m.win else "负"
        res_cell = ws.cell(row=row_idx, column=4, value=res_str)
        res_cell.fill = fill_blue if m.win else fill_red
        res_cell.border = border_thin
        res_cell.alignment = alignment_center
        
        # --- Process Players for Positions 1-5 ---
        def get_pos_map(is_radiant):
            # Returns {pos (1-5): hero_id}
            pmap = {}
            side = 0 if is_radiant else 1
            
            # Filter players on this side
            # Note: m.players is a list of PlayerPerformance objects
            team_players = [p for p in m.players if p.team_side == side]
            
            for p in team_players:
                # Use 'position' field (1-5)
                # Fallback to internal logic if 0/None?
                # Assuming data is clean enough or we accept gaps
                if p.position and 1 <= p.position <= 5:
                    pmap[p.position] = p.hero_id
            return pmap

        my_is_radiant = m.is_radiant
        my_pmap = get_pos_map(my_is_radiant)
        opp_pmap = get_pos_map(not my_is_radiant)
        
        # Logic for Highlighting
        # Map hero_id -> Pick Order to determine if it needs color
        # PickBan list has this info
        pick_order_map = {} # hero_id -> global_order
        ban_order_map = {}
        for pb in m.pick_bans:
            if pb.is_pick:
                pick_order_map[pb.hero_id] = pb.order + 1 # 1-based
            else:
                ban_order_map[pb.hero_id] = pb.order + 1
        
        # Determine who is FP
        # m.first_pick is True if 'team_name' (My Team) was First Pick
        i_am_fp = m.first_pick
        
        # E-I: My Team Pos 1-5
        for p in range(1, 6):
            col = 4 + p # E is 5
            hid = my_pmap.get(p)
            cell = ws.cell(row=row_idx, column=col)
            cell.border = border_thin
            
            if hid:
                h_data = hm.get_hero(hid)
                h_name = h_data.get('slang') or h_data.get('cn_name')
                cell.value = h_name
                
                # Color Logic
                order = pick_order_map.get(hid)
                if order:
                    if order == COLOR_YELLOW_PICK_ORDER:
                        cell.fill = fill_yellow
                    elif order in COLOR_GREEN_PICK_ORDERS:
                        cell.fill = fill_green

        # J: Side (Opponent Side)
        opp_side_str = "夜魇" if my_is_radiant else "天辉"
        ws.cell(row=row_idx, column=10, value=opp_side_str).border = border_thin
        
        # K-O: Opponent Pos 1-5
        for p in range(1, 6):
            col = 10 + p # K is 11
            hid = opp_pmap.get(p)
            cell = ws.cell(row=row_idx, column=col)
            cell.border = border_thin
            
            if hid:
                h_data = hm.get_hero(hid)
                h_name = h_data.get('slang') or h_data.get('cn_name')
                cell.value = h_name
                
                # Color Logic for Opponent
                order = pick_order_map.get(hid)
                if order:
                    if order == COLOR_YELLOW_PICK_ORDER:
                        cell.fill = fill_yellow
                    elif order in COLOR_GREEN_PICK_ORDERS:
                        cell.fill = fill_green

        # --- Bans ---
        # Need to separate bans into FP Bans (first 3) and SP Bans (first 4)
        # BUT User Logic: "1 4 7 Yellow, 2 3 5 6 Green" -> This refers to Global Order?
        # If we list bans for FP team, they are Orders 1, 3, 7...
        # If we list bans for SP team, they are Orders 2, 4, 5, 6...
        
        fp_bans = []
        sp_bans = []
        
        sorted_pbs = sorted(m.pick_bans, key=lambda x: x.order)
        
        # Determine sides
        # My Side = my_is_radiant (0/1)
        # FP Side: If i_am_fp is True, FP Side = My Side. Else Opp Side.
        fp_side = (0 if my_is_radiant else 1) if i_am_fp else (1 if my_is_radiant else 0)
        
        for pb in sorted_pbs:
            if not pb.is_pick:
                h_data = hm.get_hero(pb.hero_id)
                h_name = h_data.get('slang') or h_data.get('cn_name')
                order = pb.order + 1
                
                item = {'name': h_name, 'order': order}
                
                if pb.team_side == fp_side:
                    fp_bans.append(item)
                else:
                    sp_bans.append(item)
                    
        # Fill Columns P-V (FP Bans 1-7)
        for i in range(7):
            col = 16 + i
            cell = ws.cell(row=row_idx, column=col)
            cell.border = border_thin
            
            if i < len(fp_bans):
                b = fp_bans[i]
                cell.value = b['name']
                o = b['order']
                if o in COLOR_YELLOW_BAN_ORDERS: cell.fill = fill_yellow
                elif o in COLOR_GREEN_BAN_ORDERS: cell.fill = fill_green
            else:
                cell.value = "-"
            
        # Fill Columns W-AC (SP Bans 1-7)
        for i in range(7):
            col = 23 + i
            cell = ws.cell(row=row_idx, column=col)
            cell.border = border_thin
            
            if i < len(sp_bans):
                b = sp_bans[i]
                cell.value = b['name']
                o = b['order']
                if o in COLOR_YELLOW_BAN_ORDERS: cell.fill = fill_yellow
                elif o in COLOR_GREEN_BAN_ORDERS: cell.fill = fill_green
            else:
                cell.value = "-"

        row_idx += 1

    # Auto-adjust widths (rough)
    ws.column_dimensions['B'].width = 8
    ws.column_dimensions['C'].width = 15
    for c in range(5, 30):
        ws.column_dimensions[get_column_letter(c)].width = 12

    output = BytesIO()
    wb.save(output)
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
    
    # League Selection (Updated Logic: Dynamic Filter based on Selected Team)
    # Filter matches for the selected team first to get relevant leagues
    team_matches_query = db.query(Match.league_id).filter(Match.team_name == selected_team).distinct()
    team_league_ids = [r[0] for r in team_matches_query.all()]
    
    # Fetch League details only for these IDs
    if team_league_ids:
        relevant_leagues = db.query(League).filter(League.league_id.in_(team_league_ids)).order_by(League.league_id.desc()).all()
        league_opts = {f"{l.name}": l.league_id for l in relevant_leagues}
    else:
        league_opts = {}
        
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
    st.sidebar.markdown("---")
    st.sidebar.subheader("Excel 报告")
    
    # Template Selection
    export_template = st.sidebar.selectbox(
        "选择导出模版",
        options=["模版 1: 详细战绩与BP (标准)", "模版 2: 预留模版 (空)", "模版 3: 纯文字战报 (开发中)"]
    )
    
    if st.sidebar.button("生成 Excel 报告"):
        with st.spinner("正在生成 Excel 报告..."):
            # Ensure filtering context is passed/used implicitly by passing 'matches' which is already filtered.
            excel_data = None
            
            if "模版 1" in export_template:
                excel_data = generate_detailed_excel_export(matches, selected_team, db, hm)
            elif "模版 2" in export_template:
                excel_data = generate_template_2(matches, selected_team, db, hm)
            elif "模版 3" in export_template:
                excel_data = generate_template_3(matches, selected_team, db, hm)
            
            if excel_data:
                st.sidebar.download_button(
                    label="📥 下载 Excel",
                    data=excel_data,
                    file_name=f"{selected_team}_{export_template.split(':')[0]}_{datetime.now().strftime('%Y%m%d')}.xlsx",
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
        rad_wins = sum(1 for m in rad_m if m.win)
        
        dire_m = [m for m in matches if not m.is_radiant]
        dire_wins = sum(1 for m in dire_m if m.win)
        
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
                st.dataframe(df_pick[['英雄', '场次']], hide_index=True)
            else:
                st.caption("无数据")
                
        with c_ban:
            st.subheader("对手禁用英雄 (Ban)")
            if ban_counts:
                df_ban = pd.DataFrame(list(ban_counts.items()), columns=['hero_id', 'count'])
                df_ban['英雄'] = df_ban['hero_id'].apply(lambda x: hm.get_hero(x).get('cn_name'))
                df_ban['场次'] = df_ban['count']
                df_ban = df_ban.sort_values('count', ascending=False).head(10)
                st.dataframe(df_ban[['英雄', '场次']], hide_index=True)
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
                    # Logic to calculate Win Rate for partners
                    # Need to go back to matches and find when both were picked
                    partner_stats = []
                    
                    for pid, p_count in partners.items():
                        # Count wins where both sel_hero_id and pid were on My Team
                        wins_with_partner = 0
                        for m in matches:
                            my_side = 0 if m.is_radiant else 1
                            # Check if both heroes are in My Picks
                            my_picks = [pb.hero_id for pb in m.pick_bans if pb.is_pick and pb.team_side == my_side]
                            
                            if sel_hero_id in my_picks and pid in my_picks:
                                if m.win:
                                    wins_with_partner += 1
                                    
                        wr = wins_with_partner / p_count if p_count > 0 else 0
                        partner_stats.append({
                            'partner_id': pid,
                            'count': p_count,
                            'win_rate': wr
                        })
                    
                    df_partners = pd.DataFrame(partner_stats)
                    df_partners['搭档'] = df_partners['partner_id'].apply(lambda x: hm.get_hero(x).get('cn_name'))
                    df_partners['头像'] = df_partners['partner_id'].apply(lambda x: hm.get_hero(x).get('icon_url'))
                    df_partners['场次'] = df_partners['count']
                    df_partners['胜率'] = df_partners['win_rate'].apply(lambda x: f"{x:.1%}")
                    
                    df_partners = df_partners.sort_values('count', ascending=False).head(5)
                    
                    st.dataframe(
                        df_partners[['头像', '搭档', '场次', '胜率']],
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
                
                # Center the visual - or standard layout
                # User requested "side-by-side" compact view for BP chain too?
                # "优化一下比赛列表和统计分析中BP显示的排版" -> "Stats Analysis BP Chain" also implied.
                # So we use the new layout here too.
                
                render_bp_visual(m.pick_bans, rad_name, dire_name, hm, first_pick_radiant=is_radiant_first, layout="side-by-side")

    db.close()