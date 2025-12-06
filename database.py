from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.ext.declarative import declarative_base

# 使用 SQLite 作为本地数据库
DATABASE_URL = "sqlite:///./dota2_analyst.db"

# check_same_thread=False is needed for SQLite with Streamlit (multi-threaded)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 使用 scoped_session 确保在 Streamlit 的线程安全
db_session = scoped_session(SessionLocal)

Base = declarative_base()

def init_db():
    import models
    Base.metadata.create_all(bind=engine)

def get_db():
    db = db_session()
    try:
        yield db
    finally:
        db.close()

