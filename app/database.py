from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from dotenv import load_dotenv

load_dotenv()

# Database URL from environment (Postgres recommended).
# If DATABASE_URL is missing, fallback to local SQLite so the app can still run
# (likes/notifications/persistence become available without extra setup).
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not SQLALCHEMY_DATABASE_URL:
    os.makedirs("data", exist_ok=True)
    SQLALCHEMY_DATABASE_URL = "sqlite:///./data/marche_ai.db"

def _mk_engine(url: str):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


try:
    engine = _mk_engine(SQLALCHEMY_DATABASE_URL)
except ModuleNotFoundError as e:
    # Common case on Windows: DATABASE_URL is postgres but psycopg2 isn't installed.
    # Fallback to SQLite so the app still works out of the box.
    if "psycopg2" in str(e).lower() or "psycopg" in str(e).lower():
        os.makedirs("data", exist_ok=True)
        SQLALCHEMY_DATABASE_URL = "sqlite:///./data/marche_ai.db"
        engine = _mk_engine(SQLALCHEMY_DATABASE_URL)
    else:
        raise
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
