from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, Date, Text, Boolean, DateTime, UniqueConstraint
from .database import Base

class Opportunity(Base):
    __tablename__ = "opportunities"
    id = Column(Integer, primary_key=True, index=True)
    ref = Column(String, unique=True, index=True)
    title = Column(String)
    buyer = Column(String)
    # Domain tags used for multi-profile filtering (ex: ["AI","DATA"]) stored as JSON/text.
    domains = Column(Text, default="")
    # Short UI label derived from domains (ex: "AI / DATA" or "IT").
    service = Column(String, default="")
    budget = Column(Float)
    deadline = Column(Date)
    score = Column(Float)
    level = Column(String)
    sector = Column(String)
    description = Column(Text)
    description_technique = Column(Text, default="")
    description_fonctionnelle = Column(Text, default="")
    requirements = Column(Text, default="")  # ' | ' separated
    url = Column(Text, default="")
    comment = Column(Text, default="")
    # NOUVEAU: Suivi du workflow RAG (nouveau, en_cours, termine, erreur) pour n8n
    rag_status = Column(String, default="nouveau", index=True)
    
    # NOTE: Single-user convenience flag. True "likes" are stored per-user in the `likes` table.
    liked = Column(Boolean, default=False, index=True)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)  # username
    # UI profile bucket for this notification (GLOBAL/AI/DATA/CLOUD/DEV/CYBERSECURITY).
    # NULL/empty means "GLOBAL" for backward compatibility.
    profile = Column(String, index=True, nullable=True, default="GLOBAL")
    message = Column(Text)
    type = Column(String, index=True)
    opportunity_id = Column(String, index=True, nullable=True)
    read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class Like(Base):
    __tablename__ = "likes"
    __table_args__ = (
        UniqueConstraint("user_id", "opportunity_id", name="uq_like_user_opportunity"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)  # username
    opportunity_id = Column(String, index=True)
    liked = Column(Boolean, default=True, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, index=True)
