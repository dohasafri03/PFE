import os
import sys
from pathlib import Path

# Ensure project root is importable when running as a script
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

import api.main as m  # noqa: E402


def main() -> int:
    raw = m._load_latest_raw_scrape_index()
    rows = m._load_latest_pipeline_results_rows()
    missing = []

    def is_missing(v: str) -> bool:
        s = (m._normalize_buyer_label(v or "") or "").strip().lower()
        return s in {"", "non identifie", "non identifié", "-", "n/a"}

    for row in rows:
        oid = (row.get("ID") or "").strip()
        if not oid:
            continue
        client = (row.get("Client") or "").strip()
        if not is_missing(client):
            continue
        rr = raw.get(oid) or {}
        cand = (
            m._normalize_buyer_label(rr.get("acheteur", "") or "").strip()
            or m._normalize_buyer_label(m._infer_buyer_from_objet(rr.get("objet", "") or "")).strip()
            or m._normalize_buyer_label(m._infer_buyer_from_title(row.get("Titre", "") or "")).strip()
        )
        if not cand:
            missing.append(
                {
                    "id": oid,
                    "client": client,
                    "raw_acheteur": (rr.get("acheteur") or "").strip(),
                    "raw_objet": (rr.get("objet") or "").strip(),
                    "title": (row.get("Titre") or "").strip(),
                }
            )

    print(f"raw_index={len(raw)} pipeline_rows={len(rows)} missing={len(missing)}")
    for item in missing[:20]:
        print("\n---")
        print("id:", item["id"])
        print("client:", item["client"])
        print("raw_acheteur:", item["raw_acheteur"])
        print("title:", item["title"][:200])
        print("raw_objet:", item["raw_objet"][:260])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

