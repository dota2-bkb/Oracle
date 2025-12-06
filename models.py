from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float, BigInteger
from sqlalchemy.orm import relationship
from database import Base

class Match(Base):
    """
    存储单场比赛的核心元数据
    """
    __tablename__ = 'matches'
    
    id = Column(Integer, primary_key=True, index=True) # 数据库自增ID
    match_id = Column(String, unique=True, index=True) # 游戏内 Match ID 或 手动生成的 UUID
    
    # 基础标签 (需求 0)
    team_name = Column(String)      # 被分析队伍名 (主视角队伍)
    opponent_name = Column(String)  # 对手队伍名
    is_scrim = Column(Boolean, default=False) # 是否训练赛
    match_time = Column(DateTime)   # 比赛时间
    patch_version = Column(String)  # 版本号 (e.g., "7.37d")
    league_id = Column(Integer, nullable=True) # 关联联赛 ID
    
    # 胜负与阵营 (需求 1)
    is_radiant = Column(Boolean)    # 被分析队伍是否在天辉
    win = Column(Boolean)           # 被分析队伍是否获胜
    first_pick = Column(Boolean)    # 被分析队伍是否先选
    
    # 关联
    pick_bans = relationship("PickBan", back_populates="match", cascade="all, delete-orphan")
    players = relationship("PlayerPerformance", back_populates="match", cascade="all, delete-orphan")

class PickBan(Base):
    """
    存储 BP 过程 (需求 2)
    """
    __tablename__ = 'pick_bans'
    
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey('matches.id'))
    
    hero_id = Column(Integer)
    is_pick = Column(Boolean)       # True=Pick, False=Ban
    order = Column(Integer)         # 1-24 的全局顺序
    team_side = Column(Integer)     # 0=Radiant, 1=Dire
    
    match = relationship("Match", back_populates="pick_bans")

class PlayerPerformance(Base):
    """
    存储选手表现，用于分析绝活 (需求 3)
    """
    __tablename__ = 'player_performances'
    
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey('matches.id'))
    
    player_name = Column(String)    # 游戏内昵称
    account_id = Column(BigInteger) # Steam ID (用于关联 Player 表)
    hero_id = Column(Integer)
    position = Column(Integer)      # 1-5号位
    team_side = Column(Integer, default=0) # 0=Radiant, 1=Dire (重要: 区分敌我)
    
    # 扩展数据用于排序
    net_worth = Column(Integer, default=0)
    gpm = Column(Integer, default=0)
    
    match = relationship("Match", back_populates="players")

# --- 元数据模型 (Team/Player/League) ---

class Team(Base):
    """
    职业战队数据
    """
    __tablename__ = 'teams'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(BigInteger, unique=True, index=True)
    name = Column(String)
    tag = Column(String)
    logo_url = Column(String)
    
    players = relationship("Player", back_populates="team")

class Player(Base):
    """
    职业选手数据 (元数据)
    """
    __tablename__ = 'players'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, unique=True, index=True) # 主账号
    name = Column(String) # 职业 ID (如: Ame, Yatoro)
    team_id = Column(BigInteger, ForeignKey('teams.team_id'), nullable=True)
    fantasy_role = Column(Integer) # 1=Core, 2=Support (OpenDota standard)
    country_code = Column(String)
    default_pos = Column(Integer, nullable=True) # 常规位置 1-5
    remark = Column(String, nullable=True) # 备注 (如: XXX替补)
    
    team = relationship("Team", back_populates="players")
    aliases = relationship("PlayerAlias", back_populates="player", cascade="all, delete-orphan")

class PlayerAlias(Base):
    """
    选手小号/别名映射表
    """
    __tablename__ = 'player_aliases'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, unique=True, index=True) # 小号/别名 ID
    player_id = Column(Integer, ForeignKey('players.id')) # 关联的主选手 ID
    
    player = relationship("Player", back_populates="aliases")

class League(Base):
    """
    职业联赛数据
    """
    __tablename__ = 'leagues'

    id = Column(Integer, primary_key=True)
    league_id = Column(Integer, unique=True, index=True)
    name = Column(String)
    tier = Column(String) # professional, premium, etc.
