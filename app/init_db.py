from sqlalchemy import text

from .database import Base, engine
from .models import Opportunity, Notification, Like


def ensure_db_schema():
    """
    Ensure tables exist and add missing columns for `opportunities`.

    We avoid a full migration framework here; SQLite supports ALTER TABLE ADD COLUMN.
    """
    # Creates new tables (including notifications) when missing.
    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        url = str(engine.url)
        if "sqlite" in url.lower():
            cols = conn.execute(text("PRAGMA table_info(opportunities)")).fetchall()
            existing = {c[1] for c in cols}
            liked_type = "INTEGER DEFAULT 0"
            status_type = "TEXT DEFAULT 'nouveau'"
        else:
            cols = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'opportunities'")).fetchall()
            existing = {c[0] for c in cols}
            liked_type = "BOOLEAN DEFAULT FALSE"
            status_type = "VARCHAR DEFAULT 'nouveau'"

        to_add = {
            "description_technique": "TEXT",
            "description_fonctionnelle": "TEXT",
            "requirements": "TEXT",
            "url": "TEXT",
            "liked": liked_type,
            "domains": "TEXT",
            "service": "TEXT",
            "comment": "TEXT",
            "rag_status": status_type,
        }

        for name, typ in to_add.items():
            if name in existing:
                continue
            conn.execute(text(f"ALTER TABLE opportunities ADD COLUMN {name} {typ}"))

        # No ALTER here for notifications; create_all is enough for fresh installs.


if __name__ == "__main__":
    ensure_db_schema()
    print("SQLite DB initialized and schema ensured.")
