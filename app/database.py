from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from dotenv import load_dotenv

load_dotenv()

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not SQLALCHEMY_DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required (PostgreSQL only).")

url_l = SQLALCHEMY_DATABASE_URL.lower()
if url_l.startswith("sqlite"):
    raise RuntimeError("SQLite is disabled. Provide a PostgreSQL DATABASE_URL.")

# Accept both SQLAlchemy dialect forms and raw postgres URL.
# Recommended: postgresql+psycopg://user:pass@host:5432/dbname
if not (url_l.startswith("postgresql://") or url_l.startswith("postgresql+psycopg://")):
    raise RuntimeError("Unsupported DATABASE_URL scheme. Use postgresql:// or postgresql+psycopg://")

engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
