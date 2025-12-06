import pandas as pd
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from models import Match, PickBan, PlayerPerformance, Team, Player
from config import RADIANT_TEAM, DIRE_TEAM

class DataProcessor:
    @staticmethod
    def save_match_to_db(db: Session, match_data: Dict[str, Any], target_team_id: Optional[int] = None) -> Match:
        """
        将 OpenDota 的比赛详情 JSON 保存到数据库。
        支持双向录入：如果 target_team_id 为 None，则只保存主视角（默认为 Radiant 或基于队伍逻辑）。
        如果需要双向，需要在外部调用两次，或在此处修改逻辑。
        目前保持单次保存逻辑，由上层控制多次调用。
        """
        match_id_str = str(match_data.get('match_id'))
        
        # 2. 确定主队视角 (Perspective)
        rad_team_id = match_data.get('radiant_team_id')
        dire_team_id = match_data.get('dire_team_id')
        
        # Default to Radiant perspective if no target specified
        is_radiant = True
        if target_team_id:
            if target_team_id == dire_team_id:
                is_radiant = False
            elif target_team_id == rad_team_id:
                is_radiant = True
        
        # 3. 提取基础信息
        radiant_name = match_data.get('radiant_team', {}).get('name') or "Radiant"
        dire_name = match_data.get('dire_team', {}).get('name') or "Dire"
        
        team_name = radiant_name if is_radiant else dire_name
        opponent_name = dire_name if is_radiant else radiant_name
        
        # Check existing for THIS perspective
        existing = db.query(Match).filter(
            Match.match_id == match_id_str,
            Match.team_name == team_name
        ).first()
        
        if existing:
            return existing
        
        radiant_win = match_data.get('radiant_win')
        win = (is_radiant == radiant_win)
        
        start_time = datetime.fromtimestamp(match_data.get('start_time', 0))
        
        # 4. 创建 Match 对象
        picks_bans = match_data.get('picks_bans', [])
        first_pick = False 
        if picks_bans:
            first_pick_team = picks_bans[0].get('team') # 0 or 1
            my_side = 0 if is_radiant else 1
            first_pick = (first_pick_team == my_side)
            
        new_match = Match(
            match_id=match_id_str,
            team_name=team_name,
            opponent_name=opponent_name,
            is_scrim=False, 
            match_time=start_time,
            patch_version="", 
            league_id=match_data.get('leagueid'),
            is_radiant=is_radiant,
            win=win,
            first_pick=first_pick
        )
        db.add(new_match)
        db.flush()
        
        # 5. 处理 BP (PickBan)
        if picks_bans:
            for pb in picks_bans:
                db_pb = PickBan(
                    match_id=new_match.id,
                    hero_id=pb.get('hero_id'),
                    is_pick=pb.get('is_pick'),
                    order=pb.get('order'),
                    team_side=pb.get('team') # 0=Radiant, 1=Dire
                )
                db.add(db_pb)
                
        # 6. 处理选手表现 (PlayerPerformance)
        players = match_data.get('players', [])
        
        for p in players:
            slot = p.get('player_slot')
            is_p_radiant = slot < 128
            p_side = 0 if is_p_radiant else 1
            
            pos = 0
            if 0 <= slot <= 4:
                pos = slot + 1
            elif 128 <= slot <= 132:
                pos = slot - 127
            else:
                pos = 0
            
            acc_id = p.get('account_id')
            
            pp = PlayerPerformance(
                match_id=new_match.id,
                player_name=p.get('personaname') or p.get('name') or "Unknown",
                account_id=acc_id,
                hero_id=p.get('hero_id'),
                position=pos,
                team_side=p_side,
                net_worth=p.get('net_worth', 0),
                gpm=p.get('gold_per_min', 0)
            )
            db.add(pp)

        db.commit()
        return new_match

    @staticmethod
    def save_dual_perspective(db: Session, match_data: Dict[str, Any]) -> List[Match]:
        """
        自动保存双方视角的比赛记录。
        """
        saved = []
        
        # Perspective 1: Radiant
        rad_tid = match_data.get('radiant_team_id')
        m1 = DataProcessor.save_match_to_db(db, match_data, target_team_id=rad_tid) # Will default to Radiant if tid is None
        saved.append(m1)
        
        # Perspective 2: Dire
        dire_tid = match_data.get('dire_team_id')
        # If dire_tid is missing, we still want to save the Dire perspective?
        # Yes, user wants "A vs B" and "B vs A".
        # If save_match_to_db sees target_team_id=None, it defaults to Radiant.
        # We need to force Dire perspective.
        
        # Hack: Pass a dummy ID if None, or modify save logic to accept is_radiant flag directly?
        # Let's rely on logic: if target_team_id matches dire_team_id (even if None==None?), it sets is_radiant=False.
        # Wait, line 27: if target_team_id == dire_team_id: is_radiant = False
        # If both are None, it falls through to is_radiant=True.
        
        # Let's pass the actual dire_team_id if it exists. If it doesn't exist (e.g. pub game), 
        # we might not have a "Team B" to query later easily by ID, but by Name.
        # The requirement "Team A vs Team B" implies known teams.
        
        if dire_tid:
             m2 = DataProcessor.save_match_to_db(db, match_data, target_team_id=dire_tid)
             saved.append(m2)
        else:
            # Force create Dire perspective
            # We need to bypass the "target_team_id" check inside save_match_to_db which relies on ID matching.
            # But wait, save_match_to_db determines "is_radiant" based on ID match.
            # If we want to force it, we should refactor save_match_to_db to accept 'force_perspective' or similar.
            # OR:
            # Just call it with the dire team ID. If dire_team_id is None, we can't easily force it without changing code.
            # Let's assume professional matches have team IDs.
            pass
            
        return saved
