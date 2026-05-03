import sys

main_file = r'c:\Users\pc\IdeaProjects\marche_ai_platform\api\main.py'
with open(main_file, 'r', encoding='utf-8') as f:
    text = f.read()

target = """    \"\"\"
    latest = _find_latest("pipeline_results_*.csv")"""

replacement = """    \"\"\"
    if _DB_AVAILABLE and db is not None:
        try:
            from app.models import Opportunity
            import json
            
            q = db.query(Opportunity)
            if not include_excluded:
                q = q.filter(Opportunity.level != "EXCLUDED")
                
            opps_db = q.all()
            
            _migrate_likes_file_to_db(db, user_id=str(user))
            liked_ids = _get_liked_ids_db(db, user_id=str(user))
            
            out_items = []
            for o in opps_db:
                oid = o.ref or str(getattr(o, "id", ""))
                try:
                    domains = json.loads(getattr(o, "domains", "[]")) if getattr(o, "domains", None) else []
                except:
                    domains = [d.strip() for d in (str(getattr(o, "domains", "")) or "").split("/") if d.strip()]
                    
                reqs = [r.strip() for r in (str(getattr(o, "requirements", "")) or "").split('|') if r.strip()]
                similarity_score = getattr(o, "score", 0.0) / 20.0  # approximate, we'd rather use _compute_similarity_score
                similarity_score = _compute_similarity_score(priority=getattr(o, "level", ""), score=int(getattr(o, "score", 0.0) or 0))
                
                out_items.append({
                    "id": oid,
                    "reference": oid,
                    "priority": getattr(o, "level", "") or "",
                    "qualification": f"Score {getattr(o, 'score', 0)}" if getattr(o, 'score', 0) else "",
                    "similarity_score": similarity_score,
                    "domains": domains,
                    "domain": domains,
                    "sector": getattr(o, "sector", "") or "",
                    "service": getattr(o, "service", "") or "",
                    "title": getattr(o, "title", "") or "",
                    "buyer": getattr(o, "buyer", "") or "",
                    "organization": getattr(o, "buyer", "") or "",
                    "deadline": o.deadline.isoformat() if getattr(o, "deadline", None) else None,
                    "budget": getattr(o, "budget", 0.0) or 0.0,
                    "score": getattr(o, "score", 0.0) or 0.0,
                    "description_technique": getattr(o, "description_technique", "") or "",
                    "description_fonctionnelle": getattr(o, "description_fonctionnelle", "") or "",
                    "requirements": reqs,
                    "url": getattr(o, "url", "") or "",
                    "cps_source": "",
                    "domaines_activite": "",
                    "liked": oid in liked_ids,
                    "rag_status": getattr(o, "rag_status", "nouveau")
                })
            
            return {
                "source": "PostgreSQL Database",
                "count": len(out_items),
                "opportunities": out_items,
            }
        except Exception as e:
            logger.warning(f"Fallback to CSV due to DB error: {e}")

    latest = _find_latest("pipeline_results_*.csv")"""

if "source\": \"PostgreSQL Database" not in text:
    text = text.replace(target, replacement)
    with open(main_file, 'w', encoding='utf-8') as f:
        f.write(text)
    print("Database short-circuit injected for Dashboard!")
else:
    print("Already patched!")
