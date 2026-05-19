from sqlalchemy import text

from .database import Base, engine
from .models import Opportunity, Notification, Like, User, GeneratedDocument


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

            ncols = conn.execute(text("PRAGMA table_info(notifications)")).fetchall()
            nexisting = {c[1] for c in ncols}
            notif_profile_type = "TEXT DEFAULT 'GLOBAL'"

            ucols = conn.execute(text("PRAGMA table_info(users)")).fetchall()
            uexisting = {c[1] for c in ucols}
            dcols = conn.execute(text("PRAGMA table_info(generated_documents)")).fetchall()
            dexisting = {c[1] for c in dcols}
        else:
            cols = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'opportunities'")).fetchall()
            existing = {c[0] for c in cols}
            liked_type = "BOOLEAN DEFAULT FALSE"
            status_type = "VARCHAR DEFAULT 'nouveau'"

            ncols = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'notifications'")
            ).fetchall()
            nexisting = {c[0] for c in ncols}
            notif_profile_type = "VARCHAR DEFAULT 'GLOBAL'"

            ucols = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'users'")
            ).fetchall()
            uexisting = {c[0] for c in ucols}
            dcols = conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'generated_documents'")
            ).fetchall()
            dexisting = {c[0] for c in dcols}

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

        # Notifications: add profile bucket for per-profile UI filtering.
        if "profile" not in nexisting:
            conn.execute(text(f"ALTER TABLE notifications ADD COLUMN profile {notif_profile_type}"))

        # Users metadata (for migrations on existing deployments).
        user_to_add = {
            "display_name": "TEXT",
            "role": "TEXT",
            "profile": "TEXT",
            "avatar_url": "TEXT",
            "password_salt": "TEXT",
            "password_hash": "TEXT",
            "last_login": "TIMESTAMP",
            "created_at": "TIMESTAMP",
            "updated_at": "TIMESTAMP",
        }
        for name, typ in user_to_add.items():
            if name in uexisting:
                continue
            conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {typ}"))

        # Generated document metadata.
        doc_to_add = {
            "opportunity_id": "TEXT",
            "title": "TEXT",
            "service": "TEXT",
            "domains": "TEXT",
            "deadline": "DATE",
            "generated_at": "TIMESTAMP",
            "file_path": "TEXT",
            "ext": "TEXT",
            "kind": "TEXT",
            "size_kb": "FLOAT",
            "modified_at": "TIMESTAMP",
        }
        for name, typ in doc_to_add.items():
            if name in dexisting:
                continue
            conn.execute(text(f"ALTER TABLE generated_documents ADD COLUMN {name} {typ}"))


if __name__ == "__main__":
    ensure_db_schema()
    print("DB initialized and schema ensured.")
