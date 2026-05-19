"""One-shot: fetch missing budgets from marchespublics.gov.ma and update the DB."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from app.database import SessionLocal
from api.main import _enrich_opportunity_budgets_from_portal


def main() -> None:
    limit = int(os.environ.get("BUDGET_PORTAL_ENRICH_LIMIT", "30"))
    session = SessionLocal()
    try:
        result = _enrich_opportunity_budgets_from_portal(session, max_fetch=limit)
        print(result)
    finally:
        session.close()


if __name__ == "__main__":
    main()
