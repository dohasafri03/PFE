from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import re
import shutil
import sys
import time
import threading
import unicodedata
import base64
import hmac
import hashlib
from datetime import date, timedelta, timezone
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Body, Request, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# --- Auth models must be defined before route registration (FastAPI evaluates annotations early) ---
class LoginRequest(BaseModel):
    username: str
    password: str


class PreferencesRequest(BaseModel):
    preferred_domains: list[str] = []
    budget_min: float = 0.0
    budget_max: float = 0.0
    deadline_tolerance_days: int = 0
    enable_ai_learning: bool = True


class ActivityEventRequest(BaseModel):
    type: str
    opportunity_id: Optional[str] = None
    title: Optional[str] = None
    message: Optional[str] = None


class ProfileUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    role: Optional[str] = None
    profile: Optional[str] = None
    avatar_url: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

os.environ['PYTHONIOENCODING'] = 'utf-8'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger(__name__)

# Optional SQLite persistence (SQLAlchemy). The app works without it, but the DB stays empty.
try:
    from sqlalchemy.orm import Session
    from sqlalchemy import or_

    from app.database import get_db
    from app.init_db import ensure_db_schema
    from app.models import Opportunity, Notification, Like

    _DB_AVAILABLE = True
except Exception as e:
    _DB_AVAILABLE = False
    logger.warning(f"DB disabled (SQLAlchemy not available): {e}")

app = FastAPI(
    title="Marché AI Platform – API n8n",
    description="API REST pour orchestrer le pipeline de veille marchés publics",
    version="2.0.0",
)

# CORS Configuration
# NOTE: Cookies (login) require a non-wildcard Access-Control-Allow-Origin.
# Include common Vite dev/preview ports by default; override via CORS_ORIGINS if needed.
cors_origins_env = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173,http://localhost:8080,http://127.0.0.1:8080",
)
cors_origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]
if cors_origins_env.strip() == "*":
    cors_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Endpoint de test simple (doit être après la déclaration de app)
@app.get("/ping")
async def ping():
    return {"pong": True}

if os.environ.get("DEBUG_AUTH", "0").strip() == "1":
    @app.get("/debug/auth")
    async def debug_auth():
        """
        Debug endpoint (local dev only). Helps verify which password source is active.
        Enable by setting DEBUG_AUTH=1.
        """
        users = _load_users()
        admin = users.get("admin") if isinstance(users, dict) else None
        return {
            "debug_auth": True,
            "project_root": str(PROJECT_ROOT),
            "users_path": str(USERS_PATH),
            "has_users_file": USERS_PATH.exists(),
            "admin_has_hash": bool(isinstance(admin, dict) and admin.get("salt") and admin.get("password_hash")),
            "verify_admin_admin": _verify_login("admin", "admin"),
        }


@app.get("/")
async def root():
    """Landing endpoint for browsers / quick checks."""
    return {
        "name": "Marche AI Platform API",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "health": "/health",
        "ping": "/ping",
    }


@app.get("/favicon.ico")
async def favicon():
    # Browsers often request /favicon.ico automatically; return 204 to avoid noisy 404 logs.
    return Response(status_code=204)


@app.post("/auth/login")
async def auth_login(req: LoginRequest, response: Response):
    if not AUTH_ENABLED:
        return {"enabled": False, "message": "Auth disabled"}

    if not _verify_login(req.username or "", req.password or ""):
        raise HTTPException(401, "Invalid credentials")

    exp = int(time.time()) + 60 * 60 * 24 * 7  # 7 days
    token = _make_token(req.username, exp_ts=exp)
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=60 * 60 * 24 * 7,
        path="/",
    )
    # Audit (last login)
    try:
        audit = _load_auth_audit()
        audit[req.username] = {"last_login": datetime.now().isoformat()}
        _save_auth_audit(audit)
    except Exception:
        pass

    profile = _get_user_profile(req.username)
    return {"ok": True, **profile}


@app.post("/auth/logout")
async def auth_logout(response: Response):
    response.delete_cookie(key=AUTH_COOKIE_NAME, path="/")
    return {"ok": True}


@app.get("/auth/me")
async def auth_me(request: Request):
    user = require_auth(request)
    # If AUTH_ENABLED=0, user is None.
    if not user:
        return {"ok": True, "username": ""}
    return {"ok": True, **_get_user_profile(user)}


@app.post("/auth/change-password")
async def auth_change_password(request: Request, payload: ChangePasswordRequest):
    username = require_auth(request)
    if not username:
        raise HTTPException(401, "Not authenticated")

    # Verify current password either against users.json or env fallback.
    if not _verify_login(username, payload.current_password):
        raise HTTPException(400, "Current password is invalid")

    if len(payload.new_password or "") < 6:
        raise HTTPException(400, "New password must be at least 6 characters")

    _set_user_password(username, payload.new_password)
    _append_activity(
        {
            "type": "security_action",
            "message": "Changed password",
            "user": username,
            "created_at": datetime.now().isoformat(),
        }
    )
    return {"ok": True}

# ── State ────────────────────────────────────────────────────────────────────
_status = {
    "scraping": {"running": False, "started_at": None, "last_run": None, "last_csv": None, "error": None},
    "pipeline": {"running": False, "last_run": None, "last_report": None, "error": None},
    "dossiers": {"running": False, "last_run": None, "last_result": None, "error": None},
}

# --- In-memory caches (avoid re-parsing large CSV exports on each request) ---
_cache_lock = threading.Lock()
_pipeline_rows_cache: dict[str, object] = {"path": None, "mtime": None, "rows": None}
# key: (path, mtime, include_excluded) -> list[dict] (base items without per-user fields like "liked")
_opps_base_cache: dict[tuple[str, float, bool], list[dict]] = {}


# --- Likes storage (simple file-based store in ./data for persistence in Docker volumes) ---
LIKES_PATH = PROJECT_ROOT / "data" / "likes.json"
_likes_lock = threading.Lock()

ACTIVITY_PATH = PROJECT_ROOT / "data" / "activity.jsonl"
PREFERENCES_PATH = PROJECT_ROOT / "data" / "preferences.json"
AUTH_AUDIT_PATH = PROJECT_ROOT / "data" / "auth_audit.json"
USERS_PATH = PROJECT_ROOT / "data" / "users.json"


def _load_users() -> dict[str, dict]:
    if not USERS_PATH.exists():
        return {}
    try:
        with open(USERS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_users(data: dict[str, dict]) -> None:
    USERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(USERS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _hash_password(password: str, salt_b64: str) -> str:
    salt = base64.b64decode(salt_b64.encode("ascii"))
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return base64.b64encode(dk).decode("ascii")


def _new_salt_b64() -> str:
    return base64.b64encode(os.urandom(16)).decode("ascii")


def _verify_password(password: str, salt_b64: str, expected_hash_b64: str) -> bool:
    computed = _hash_password(password, salt_b64=salt_b64)
    return hmac.compare_digest(computed, expected_hash_b64)


def _get_user_profile(username: str) -> dict:
    users = _load_users()
    u = users.get(username) if isinstance(users, dict) else None
    if isinstance(u, dict):
        raw_profile = str(u.get("profile") or u.get("role") or "").strip().upper()
        if raw_profile == "CYBER":
            raw_profile = "CYBERSECURITY"
        if raw_profile not in {"GLOBAL", "AI", "DATA", "CLOUD", "DEV", "CYBERSECURITY"}:
            raw_profile = "GLOBAL"
        return {
            "username": username,
            "display_name": u.get("display_name") or username,
            "role": u.get("role") or "Admin",
            "profile": raw_profile,
            "avatar_url": u.get("avatar_url") or "",
        }
    return {"username": username, "display_name": username, "role": "Admin", "profile": "GLOBAL", "avatar_url": ""}


def _verify_login(username: str, password: str) -> bool:
    """Verify credentials: prefer file-based users; fallback to env default admin/admin."""
    users = _load_users()
    u = users.get(username) if isinstance(users, dict) else None
    if isinstance(u, dict) and u.get("salt") and u.get("password_hash"):
        try:
            return _verify_password(password, salt_b64=str(u["salt"]), expected_hash_b64=str(u["password_hash"]))
        except Exception:
            return False
    return False


def _set_user_password(username: str, new_password: str) -> None:
    users = _load_users()
    entry = users.get(username) if isinstance(users, dict) else None
    if not isinstance(entry, dict):
        entry = {"role": "Admin", "display_name": username, "avatar_url": ""}
    salt_b64 = _new_salt_b64()
    entry["salt"] = salt_b64
    entry["password_hash"] = _hash_password(new_password, salt_b64=salt_b64)
    users[username] = entry
    _save_users(users)


def _update_user_profile(username: str, update: ProfileUpdateRequest) -> dict:
    users = _load_users()
    entry = users.get(username) if isinstance(users, dict) else None
    if not isinstance(entry, dict):
        entry = {"role": "Admin", "display_name": username, "avatar_url": ""}

    if update.display_name is not None:
        entry["display_name"] = update.display_name.strip() or username
    if update.role is not None:
        entry["role"] = update.role.strip() or entry.get("role") or "Admin"
    if update.profile is not None:
        prof = update.profile.strip().upper()
        if prof == "CYBER":
            prof = "CYBERSECURITY"
        if prof in {"GLOBAL", "AI", "DATA", "CLOUD", "DEV", "CYBERSECURITY"}:
            entry["profile"] = prof
    if update.avatar_url is not None:
        entry["avatar_url"] = update.avatar_url.strip()

    users[username] = entry
    _save_users(users)
    return _get_user_profile(username)


def _ensure_default_profile_users() -> None:
    """
    Create one local account per profile (simple multi-profile auth).

    Defaults (dev):
      - global / global
      - ai / ai
      - data / data
      - cloud / cloud
      - dev / dev
      - cyber / cyber

    Override per-user passwords via env:
      AUTH_PASS_GLOBAL, AUTH_PASS_AI, AUTH_PASS_DATA, AUTH_PASS_CLOUD, AUTH_PASS_DEV, AUTH_PASS_CYBER
    Disable bootstrap via: AUTH_BOOTSTRAP_USERS=0
    """
    if not AUTH_ENABLED:
        return
    if os.environ.get("AUTH_BOOTSTRAP_USERS", "1").strip() == "0":
        return

    defaults = [
        ("global", "GLOBAL", os.environ.get("AUTH_PASS_GLOBAL") or "global"),
        ("ai", "AI", os.environ.get("AUTH_PASS_AI") or "ai"),
        ("data", "DATA", os.environ.get("AUTH_PASS_DATA") or "data"),
        ("cloud", "CLOUD", os.environ.get("AUTH_PASS_CLOUD") or "cloud"),
        ("dev", "DEV", os.environ.get("AUTH_PASS_DEV") or "dev"),
        ("cyber", "CYBERSECURITY", os.environ.get("AUTH_PASS_CYBER") or "cyber"),
    ]

    users = _load_users()
    changed = False

    # Ensure existing admin gets a profile (keeps current password).
    admin = users.get("admin") if isinstance(users, dict) else None
    if isinstance(admin, dict) and not admin.get("profile"):
        admin["profile"] = "GLOBAL"
        users["admin"] = admin
        changed = True

    # Ensure profile users exist.
    for uname, profile, pwd in defaults:
        entry = users.get(uname) if isinstance(users, dict) else None
        if not isinstance(entry, dict):
            users[uname] = {"display_name": uname, "role": profile, "profile": profile, "avatar_url": ""}
            changed = True
        else:
            if not entry.get("profile"):
                entry["profile"] = profile
                users[uname] = entry
                changed = True

    if changed:
        _save_users(users)

    # Set passwords for newly created accounts (only if missing hash).
    users = _load_users()
    for uname, profile, pwd in defaults:
        entry = users.get(uname) if isinstance(users, dict) else None
        if isinstance(entry, dict) and not entry.get("password_hash"):
            _set_user_password(uname, pwd)


def _load_likes() -> dict[str, dict]:
    if not LIKES_PATH.exists():
        return {}
    try:
        with open(LIKES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_likes(data: dict[str, dict]) -> None:
    LIKES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LIKES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _migrate_likes_file_to_db(db: "Session", user_id: str) -> int:
    """
    One-time migration: copy data/likes.json into SQLite likes table.
    Only runs when the user has no likes rows yet (prevents duplicates).
    """
    if not _DB_AVAILABLE:
        return 0
    user_id = (user_id or "").strip()
    if not user_id:
        return 0
    try:
        if db.query(Like).filter(Like.user_id == user_id).count():
            return 0
        with _likes_lock:
            likes = _load_likes()
        now = datetime.utcnow()
        migrated = 0
        for oid, entry in (likes or {}).items():
            if not isinstance(entry, dict) or not entry.get("liked"):
                continue
            oid = (str(oid) or "").strip()
            if not oid:
                continue
            db.add(Like(user_id=user_id, opportunity_id=oid, liked=True, updated_at=now))
            migrated += 1
        if migrated:
            db.commit()
            # Keep convenience flag in opportunities table in sync (single-user use case).
            try:
                db.query(Opportunity).filter(Opportunity.ref.in_([str(k) for k, v in likes.items() if isinstance(v, dict) and v.get("liked")])).update(  # type: ignore[attr-defined]
                    {Opportunity.liked: True},  # type: ignore[attr-defined]
                    synchronize_session=False,
                )
                db.commit()
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
        return migrated
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return 0


def _get_liked_ids_db(db: "Session", user_id: str) -> set[str]:
    if not _DB_AVAILABLE:
        return set()
    user_id = (user_id or "").strip()
    if not user_id:
        return set()
    rows = (
        db.query(Like.opportunity_id)
        .filter(Like.user_id == user_id, Like.liked == True)  # noqa: E712
        .all()
    )
    return {r[0] for r in rows if r and r[0]}


def _set_like_db(db: "Session", user_id: str, opportunity_id: str, liked: bool) -> bool:
    """Upsert a like row for (user_id, opportunity_id) and commit. Returns the final state."""
    if not _DB_AVAILABLE:
        return bool(liked)
    user_id = (user_id or "").strip()
    opportunity_id = (opportunity_id or "").strip()
    if not user_id or not opportunity_id:
        return bool(liked)

    row = (
        db.query(Like)
        .filter(Like.user_id == user_id, Like.opportunity_id == opportunity_id)
        .one_or_none()
    )
    now = datetime.utcnow()
    if row is None:
        row = Like(user_id=user_id, opportunity_id=opportunity_id, liked=bool(liked), updated_at=now)
        db.add(row)
    else:
        row.liked = bool(liked)
        row.updated_at = now
    # SQLite can occasionally hit "database is locked" under concurrent requests.
    # Retry a few times to make likes stable.
    try:
        from sqlalchemy.exc import OperationalError  # type: ignore
    except Exception:  # pragma: no cover
        OperationalError = Exception  # type: ignore

    for attempt in range(3):
        try:
            db.commit()
            break
        except OperationalError as e:  # type: ignore[misc]
            try:
                db.rollback()
            except Exception:
                pass
            if attempt >= 2:
                raise
            time.sleep(0.15 * (attempt + 1))

    # Also update the convenience `opportunities.liked` flag (best-effort).
    try:
        opp = db.query(Opportunity).filter(Opportunity.ref == opportunity_id).one_or_none()
        if opp is not None:
            opp.liked = bool(row.liked)
            try:
                db.commit()
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    return bool(row.liked)


def _is_liked(opportunity_id: str, likes: dict[str, dict]) -> bool:
    entry = likes.get(opportunity_id)
    return bool(entry.get("liked")) if isinstance(entry, dict) else False


def _append_activity(event: dict) -> None:
    ACTIVITY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ACTIVITY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _load_activity(limit: int = 50) -> list[dict]:
    if not ACTIVITY_PATH.exists():
        return []
    items: list[dict] = []
    try:
        with open(ACTIVITY_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return items[-max(1, limit):][::-1]


def _load_preferences() -> dict:
    if not PREFERENCES_PATH.exists():
        return {}
    try:
        with open(PREFERENCES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_preferences(data: dict) -> None:
    PREFERENCES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PREFERENCES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_auth_audit() -> dict:
    if not AUTH_AUDIT_PATH.exists():
        return {}
    try:
        with open(AUTH_AUDIT_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_auth_audit(data: dict) -> None:
    AUTH_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(AUTH_AUDIT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _list_known_users() -> list[str]:
    """Return all known usernames (users.json + AUTH_USERNAME fallback)."""
    users = set()
    try:
        users_data = _load_users()
        for k in (users_data or {}).keys():
            if k:
                users.add(str(k))
    except Exception:
        pass
    if AUTH_USERNAME:
        users.add(AUTH_USERNAME)
    return sorted(users)


def _normalize_profile_label(p: Optional[str]) -> str:
    s = (p or "").strip().upper()
    if s == "CYBER":
        s = "CYBERSECURITY"
    if not s or s in {"ALL"}:
        return "GLOBAL"
    if s not in {"GLOBAL", "AI", "DATA", "CLOUD", "DEV", "CYBERSECURITY"}:
        return "GLOBAL"
    return s


def _user_has_admin_visibility(username: str) -> bool:
    """
    Admin accounts should see ALL notifications across profiles.

    Convention in this project:
    - `users.json` uses role == "Admin" for the administrator account(s).
    - Back-compat: treat default `admin` username as admin even if role is missing.
    """
    u = (username or "").strip()
    if not u:
        return False
    if u.lower() == "admin":
        return True
    try:
        users = _load_users()
        entry = users.get(u) if isinstance(users, dict) else None
        if isinstance(entry, dict):
            role = str(entry.get("role") or "").strip().upper()
            if role in {"ADMIN", "ADMINISTRATOR", "SUPERADMIN", "ROOT"}:
                return True
            if str(entry.get("role") or "").strip() == "Admin":
                return True
    except Exception:
        return False
    return False


def _domains_from_opportunity_dict(o: dict) -> list[str]:
    if not isinstance(o, dict):
        return []
    doms = o.get("domains") or o.get("domain") or []
    if isinstance(doms, str):
        doms = [d.strip().upper() for d in doms.split("/") if d.strip()]
    if isinstance(doms, list):
        return [str(d).strip().upper() for d in doms if str(d).strip()]
    # Fallback: parse qualification string if present (CSV/DB exports).
    qual = o.get("qualification") or o.get("Qualification") or ""
    try:
        return _parse_pipeline_domains(str(qual))
    except Exception:
        return []


def _notification_bucket_for_opportunity(o: dict) -> str:
    """
    Pick a single profile bucket for a notification tied to an opportunity.

    We prefer the strongest domain label already attached to the opportunity.
    """
    doms = _domains_from_opportunity_dict(o)
    if not doms:
        return "GLOBAL"
    order = {"AI": 0, "DATA": 1, "CLOUD": 2, "DEV": 3, "CYBERSECURITY": 4}
    doms_sorted = sorted(set(doms), key=lambda d: order.get(d, 99))
    return doms_sorted[0]


def _opportunity_matches_user_profile(o: dict, user_profile: str) -> bool:
    """
    Lightweight match aligned with dossiers filtering intent:
    - GLOBAL/ALL: everything
    - Otherwise: match domain tag OR substring match in service string (CYBER alias included)
    """
    p = _normalize_profile_label(user_profile)
    if p in {"GLOBAL", "ALL"}:
        return True

    if not isinstance(o, dict):
        return False

    doms = _domains_from_opportunity_dict(o)
    if p in doms:
        return True

    svc = str(o.get("service") or "").upper()
    if p == "CYBERSECURITY" and "CYBER" in svc:
        return True
    if p and p in svc:
        return True
    return False


def _notification_matches_view(*, view_profile: str, notif_profile: Optional[str]) -> bool:
    """
    Filter notifications for the UI "profile view".

    Rules:
    - GLOBAL/ALL view: show everything (including legacy NULL profile rows).
    - Specific view: strict match on `profile` (DEV sees only DEV-tagged rows, etc.).
    """
    vp = _normalize_profile_label(view_profile)
    np = _normalize_profile_label(notif_profile) if (notif_profile is not None and str(notif_profile).strip() != "") else "GLOBAL"

    if vp in {"GLOBAL", "ALL"}:
        return True

    # Specific profile: strict match only (DEV sees DEV-tagged rows, etc.)
    return np == vp


def _create_notification(
    db: "Session",
    user_id: str,
    message: str,
    ntype: str,
    opportunity_id: Optional[str] = None,
    profile: Optional[str] = None,
) -> None:
    if not _DB_AVAILABLE:
        return
    user_id = (user_id or "").strip()
    if not user_id:
        return
    obj = Notification(
        user_id=user_id,
        profile=_normalize_profile_label(profile),
        message=message,
        type=ntype,
        opportunity_id=opportunity_id,
        read=False,
        created_at=datetime.utcnow(),
    )
    db.add(obj)

# --- Auth (simple signed token, cookie-based) ---
AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "1").strip() != "0"
AUTH_USERNAME = os.environ.get("AUTH_USERNAME", "admin")
AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD", "admin")
AUTH_SECRET = os.environ.get("AUTH_SECRET", "change-me-in-prod")
AUTH_COOKIE_NAME = "marche_ai_token"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("ascii"))


def _sign(msg: bytes) -> str:
    return _b64url(hmac.new(AUTH_SECRET.encode("utf-8"), msg, hashlib.sha256).digest())


def _make_token(username: str, exp_ts: int) -> str:
    payload = json.dumps({"u": username, "exp": exp_ts}, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    body = _b64url(payload).encode("ascii")
    sig = _sign(body).encode("ascii")
    return (body + b"." + sig).decode("ascii")


def _verify_token(token: str) -> Optional[dict]:
    try:
        body_b64, sig = token.split(".", 1)
        expected = _sign(body_b64.encode("ascii"))
        if not hmac.compare_digest(expected, sig):
            return None
        payload = json.loads(_b64url_decode(body_b64).decode("utf-8"))
        exp = int(payload.get("exp", 0))
        if exp <= int(time.time()):
            return None
        return payload
    except Exception:
        return None


def require_auth(request: Request) -> Optional[str]:
    if not AUTH_ENABLED:
        return None

    token = request.cookies.get(AUTH_COOKIE_NAME) or ""
    if not token:
        auth = request.headers.get("authorization") or request.headers.get("Authorization") or ""
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()

    payload = _verify_token(token) if token else None
    if not payload:
        raise HTTPException(401, "Unauthorized")
    return str(payload.get("u") or "")


@app.get("/profile/stats")
async def profile_stats(request: Request, db=Depends(get_db) if _DB_AVAILABLE else None):
    user = require_auth(request)

    current = await results_opportunities(include_excluded=False, user=user, db=db)  # type: ignore[arg-type]
    opps = current.get("opportunities") or []

    liked = [o for o in opps if o.get("liked")]
    recommended = [o for o in opps if float(o.get("similarity_score") or 0.0) > 0.75]

    # Generated dossiers count (docx+pdf files)
    dossiers_root = PROJECT_ROOT / "dossiers_generes"
    docx_count = 0
    pdf_count = 0
    if dossiers_root.exists():
        docx_count = len([p for p in dossiers_root.rglob("*.docx") if not p.name.startswith("~$")])
        pdf_count = len([p for p in dossiers_root.rglob("*.pdf") if not p.name.startswith("~$")])

    avg_score_selected = 0.0
    if liked:
        avg_score_selected = sum(float(o.get("score") or 0.0) for o in liked) / max(1, len(liked))

    return {
        "liked_count": len(liked),
        "recommended_count": len(recommended),
        "generated_dossiers_count": docx_count + pdf_count,
        "avg_score_selected": round(avg_score_selected, 2),
    }


@app.get("/profile/me")
async def profile_me(request: Request):
    user = require_auth(request)
    if not user:
        raise HTTPException(401, "Not authenticated")
    return {"ok": True, **_get_user_profile(user)}


@app.post("/profile/me")
async def profile_me_update(request: Request, body: ProfileUpdateRequest):
    user = require_auth(request)
    if not user:
        raise HTTPException(401, "Not authenticated")
    profile = _update_user_profile(user, body)
    _append_activity(
        {
            "user": user,
            "type": "profile_edit",
            "message": "Updated profile",
            "created_at": datetime.now().isoformat(),
        }
    )
    return {"ok": True, **profile}


@app.get("/profile/preferences")
async def profile_preferences(request: Request):
    user = require_auth(request)
    prefs = _load_preferences()
    return prefs.get(user, {
        "preferred_domains": ["Cloud", "Data"],
        "budget_min": 0,
        "budget_max": 0,
        "deadline_tolerance_days": 7,
        "enable_ai_learning": True,
    })


@app.post("/profile/preferences")
async def profile_preferences_save(request: Request, body: PreferencesRequest):
    user = require_auth(request)
    prefs = _load_preferences()
    prefs[user] = body.model_dump() if hasattr(body, "model_dump") else body.dict()
    _save_preferences(prefs)
    return {"ok": True}


@app.get("/profile/activity")
async def profile_activity(request: Request, limit: int = 50):
    user = require_auth(request)
    items = [e for e in _load_activity(limit=limit) if e.get("user") == user]
    return {"count": len(items), "items": items}


@app.post("/profile/activity")
async def profile_activity_add(request: Request, body: ActivityEventRequest):
    user = require_auth(request)
    event = {
        "user": user,
        "type": (body.type or "").strip(),
        "opportunity_id": (body.opportunity_id or "").strip() or None,
        "title": body.title,
        "message": body.message,
        "created_at": datetime.now().isoformat(),
    }
    _append_activity(event)
    return {"ok": True}


@app.get("/profile/security")
async def profile_security(request: Request):
    user = require_auth(request)
    audit = _load_auth_audit()
    last_login = (audit.get(user) or {}).get("last_login")

    token = request.cookies.get(AUTH_COOKIE_NAME) or ""
    payload = _verify_token(token) if token else None
    exp = int(payload.get("exp")) if isinstance(payload, dict) and payload.get("exp") else None

    return {
        "active_session": True,
        "username": user,
        "last_login": last_login,
        "session_expires": exp,
    }


async def _ensure_deadline_notifications(db: "Session", user_id: str, days: int = 5) -> None:
    """Create deadline notifications (best-effort, de-duplicated within ~24h)."""
    if not _DB_AVAILABLE or db is None:
        return

    try:
        current = await results_opportunities(include_excluded=False, user=user_id, db=db)  # type: ignore[arg-type]
        opps = current.get("opportunities") or []
    except Exception:
        return

    user_profile = str(_get_user_profile(str(user_id)).get("profile") or "GLOBAL").strip().upper()
    if user_profile == "CYBER":
        user_profile = "CYBERSECURITY"
    if user_profile not in {"GLOBAL", "AI", "DATA", "CLOUD", "DEV", "CYBERSECURITY"}:
        user_profile = "GLOBAL"
    admin_vis = _user_has_admin_visibility(str(user_id))

    now = datetime.utcnow()
    window_end = now + timedelta(days=days)
    cutoff = now - timedelta(hours=24)

    for o in opps:
        if not isinstance(o, dict):
            continue
        if (not admin_vis) and (not _opportunity_matches_user_profile(o, user_profile)):
            continue
        oid = str(o.get("id") or o.get("reference") or "").strip()
        if not oid:
            continue

        d = o.get("deadline")
        if not d:
            continue

        dd: Optional[datetime] = None
        try:
            if isinstance(d, str):
                dd = datetime.fromisoformat(d.replace("Z", "+00:00"))
            elif isinstance(d, date):
                dd = datetime(d.year, d.month, d.day)
        except Exception:
            dd = None

        if dd and dd.tzinfo is not None:
            dd = dd.astimezone(timezone.utc).replace(tzinfo=None)

        if not dd or not (now <= dd <= window_end):
            continue

        notif_profile = _notification_bucket_for_opportunity(o)
        exists = (
            db.query(Notification)
            .filter(Notification.user_id == user_id)
            .filter(Notification.type == "deadline_approaching")
            .filter(Notification.opportunity_id == oid)
            .filter(Notification.profile == notif_profile)
            .filter(Notification.created_at >= cutoff)
            .count()
        )
        if exists:
            continue

        title = (o.get("title") or oid)
        days_left = max(0, int((dd - now).total_seconds() // 86400))
        _create_notification(
            db,
            user_id=user_id,
            message=f"Deadline approaching (<5 days): {title} ({days_left}d)",
            ntype="deadline_approaching",
            opportunity_id=oid,
            profile=notif_profile,
        )

    try:
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


@app.get("/notifications")
async def get_notifications(
    request: Request,
    limit: int = 50,
    profile: Optional[str] = Query(
        None,
        description="Profile view filter (GLOBAL/AI/DATA/CLOUD/DEV/CYBERSECURITY). Defaults to the authenticated user's profile.",
    ),
    db=Depends(get_db) if _DB_AVAILABLE else None,
):
    user = require_auth(request)
    if not _DB_AVAILABLE or db is None:
        raise HTTPException(501, "DB not available")

    await _ensure_deadline_notifications(db, user_id=user, days=5)

    view_profile = (profile or (_get_user_profile(str(user)).get("profile") or "GLOBAL")).strip().upper()
    if view_profile == "CYBER":
        view_profile = "CYBERSECURITY"
    if view_profile not in {"GLOBAL", "AI", "DATA", "CLOUD", "DEV", "CYBERSECURITY", "ALL"}:
        view_profile = "GLOBAL"

    base_q = db.query(Notification).filter(Notification.user_id == user)
    vp = _normalize_profile_label(view_profile)
    if _user_has_admin_visibility(str(user)):
        filtered_q = base_q
    elif vp in {"GLOBAL", "ALL"}:
        filtered_q = base_q
    else:
        filtered_q = base_q.filter(
            or_(
                Notification.profile == vp,
                # Back-compat: older rows may not have `profile` populated; treat as GLOBAL bucket.
                Notification.profile.is_(None),
                Notification.profile == "",
            )
        )

    unread_count = int(filtered_q.filter(Notification.read == False).count())  # noqa: E712

    items = (
        filtered_q.order_by(Notification.created_at.desc())
        .limit(max(1, min(int(limit), 200)))
        .all()
    )

    def _ser(n: "Notification") -> dict:
        return {
            "id": n.id,
            "user_id": n.user_id,
            "profile": getattr(n, "profile", None) or "GLOBAL",
            "message": n.message,
            "type": n.type,
            "opportunity_id": n.opportunity_id,
            "read": bool(n.read),
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }

    return {
        "unread_count": unread_count,
        "count": len(items),
        "profile": vp,
        "admin_all_profiles": bool(_user_has_admin_visibility(str(user))),
        "notifications": [_ser(n) for n in items],
    }


@app.post("/notifications/read/{nid}")
async def read_notification(
    nid: int,
    request: Request,
    profile: Optional[str] = Query(None, description="Profile view filter (optional; avoids mismatched UI states)"),
    db=Depends(get_db) if _DB_AVAILABLE else None,
):
    user = require_auth(request)
    if not _DB_AVAILABLE or db is None:
        raise HTTPException(501, "DB not available")

    obj = db.query(Notification).filter(Notification.id == int(nid)).one_or_none()
    if not obj or obj.user_id != user:
        raise HTTPException(404, "Not found")

    if (not _user_has_admin_visibility(str(user))) and profile is not None and str(profile).strip():
        view_profile = str(profile).strip().upper()
        if view_profile == "CYBER":
            view_profile = "CYBERSECURITY"
        np = getattr(obj, "profile", None)
        if not _notification_matches_view(view_profile=view_profile, notif_profile=np):
            raise HTTPException(404, "Not found")

    obj.read = True
    db.commit()
    return {"ok": True}


@app.post("/notifications/read_all")
async def read_all_notifications(
    request: Request,
    profile: Optional[str] = Query(
        None,
        description="Profile view filter (GLOBAL/AI/DATA/CLOUD/DEV/CYBERSECURITY). Defaults to the authenticated user's profile.",
    ),
    db=Depends(get_db) if _DB_AVAILABLE else None,
):
    user = require_auth(request)
    if not _DB_AVAILABLE or db is None:
        raise HTTPException(501, "DB not available")

    view_profile = (profile or (_get_user_profile(str(user)).get("profile") or "GLOBAL")).strip().upper()
    if view_profile == "CYBER":
        view_profile = "CYBERSECURITY"
    if view_profile not in {"GLOBAL", "AI", "DATA", "CLOUD", "DEV", "CYBERSECURITY", "ALL"}:
        view_profile = "GLOBAL"

    q = db.query(Notification).filter(Notification.user_id == user).filter(Notification.read == False)  # noqa: E712
    vp = _normalize_profile_label(view_profile)
    if (not _user_has_admin_visibility(str(user))) and vp not in {"GLOBAL", "ALL"}:
        q = q.filter(
            or_(
                Notification.profile == vp,
                Notification.profile.is_(None),
                Notification.profile == "",
            )
        )

    q.update({"read": True})
    db.commit()
    return {"ok": True}


# ── Models ───────────────────────────────────────────────────────────────────

class ScrapeRequest(BaseModel):
    keywords: Optional[list] = None  # Override default keywords (optional)
    fast_mode: bool = False          # Skip enrichment (much faster)
    concurrency: int = 5             # Parallel tabs for enrichment
    webhook_url: Optional[str] = None  # Optional n8n resume URL


class PipelineRequest(BaseModel):
    csv_path: Optional[str] = None       # Use specific CSV (auto-detect if empty)
    generate_dossiers: bool = True       # Generate DOCX dossiers
    use_rag: bool = False                # Enable RAG/LLM enrichment
    enrich_cps: bool = True              # Enable CPS detail enrichment
    hot_only: bool = False               # Only HOT items
    all_priorities: bool = True          # HOT + WARM + COLD

class ScoreRequest(BaseModel):
    csv_path: Optional[str] = None
    # When true (default), `/pipeline/score` only returns items with a valid, non-expired deadline.
    # n8n email reports should typically set this to false and apply their own deadline rules in JS.
    require_valid_deadline: bool = True

class RAGRequest(BaseModel):
    csv_path: Optional[str] = None
    max_consultations: int = 50


class LikeRequest(BaseModel):
    # If omitted, the API toggles the like state.
    liked: Optional[bool] = None


def _find_latest(pattern: str, directory: str = "data") -> Optional[Path]:
    """Find the latest file matching a glob pattern in a directory."""
    data_dir = PROJECT_ROOT / directory
    files = sorted(data_dir.glob(pattern), reverse=True)
    return files[0] if files else None


def _find_latest_csv() -> Optional[Path]:
    """Find latest raw CSV (exclude filtered _IT variants)."""
    data_dir = PROJECT_ROOT / "data"
    for pattern in ["appels_offres_profond_*.csv", "appels_offres_multi_sources_*.csv"]:
        files = sorted(
            [f for f in data_dir.glob(pattern) if "_IT" not in f.stem],
            reverse=True
        )
        if files:
            return files[0]
    return None


def _normalize_buyer_label(value: str) -> str:
    s = str(value or "").strip()
    if not s:
        return ""
    s = re.sub(r"^\s*acheteur\s+public\b\s*[:\-]?\s*", "", s, flags=re.I).strip()
    s = re.sub(r"^\s*acheteur\b\s*[:\-]?\s*", "", s, flags=re.I).strip()
    return s


def _infer_buyer_from_objet(objet: str) -> str:
    text = str(objet or "").replace("\n", " ").replace("\r", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    # Common phrasing in scraped portals.
    m = re.search(r"\bpour\s+le\s+compte\s+de\s+(?:la|le|l['’]|du|des)\s+([^.;,]+)\b", text, flags=re.I)
    if m and m.group(1):
        return str(m.group(1)).strip()
    m2 = re.search(r"\bpour\s+le\s+compte\s+de\s+([^.;,]+)\b", text, flags=re.I)
    if m2 and m2.group(1):
        return str(m2.group(1)).strip()

    # "au profit du/de la ..." is common (beneficiary organization).
    m3 = re.search(r"\bau\s+profit\s+(?:de|du|de\s+la|de\s+l['’]|des)\s+([^.;,]+)\b", text, flags=re.I)
    if m3 and m3.group(1):
        return str(m3.group(1)).strip()

    # "destiné au/à la ... du/de la ..." -> take the organization after du/de la.
    m4 = re.search(
        r"\bdestin[ée]e?\s+(?:au|a\s+la|à\s+la|aux|a\s+l['’]|à\s+l['’])\s+.*?\s+(?:du|de\s+la|de\s+l['’]|des)\s+([^.;,]+)\b",
        text,
        flags=re.I,
    )
    if m4 and m4.group(1):
        return str(m4.group(1)).strip()

    # Some tenders explicitly mention well-known org phrases.
    m5 = re.search(r"\bdu\s+(Conseil\s+de\s+la\s+R[ée]gion\s+[^.;,]+)\b", text, flags=re.I)
    if m5 and m5.group(1):
        return str(m5.group(1)).strip()
    m6 = re.search(r"\bdu\s+(Centre\s+Hospitalier\s+[^.;,]+)\b", text, flags=re.I)
    if m6 and m6.group(1):
        return str(m6.group(1)).strip()
    m7 = re.search(r"\bdu\s+(Minist[èe]re\s+[^.;,]+)\b", text, flags=re.I)
    if m7 and m7.group(1):
        return str(m7.group(1)).strip()

    # Hospital wording: "CHP de X à Y" (Centre Hospitalier Provincial).
    m8 = re.search(r"\bCHP\s+de\s+([^.;,*]+)\b", text, flags=re.I)
    if m8 and m8.group(1):
        return ("CHP de " + str(m8.group(1)).strip()).strip()

    return ""


def _infer_buyer_from_title(title: str) -> str:
    raw = str(title or "")
    if not raw:
        return ""
    m = re.search(r"\bacheteur\s+public\b\s*[:\-]?\s*([^\n\r]+)\s*$", raw, flags=re.I)
    if not m:
        return ""
    return str(m.group(1) or "").strip()


def _load_latest_raw_scrape_index() -> dict[str, dict[str, str]]:
    """
    Build a small index from the latest raw scrape CSV:
    reference -> {acheteur, objet}
    Used to fill missing 'buyer' in pipeline_results exports.
    """
    csv_path = _find_latest_csv()
    if not csv_path or not csv_path.exists():
        return {}
    try:
        idx: dict[str, dict[str, str]] = {}
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            dr = csv.DictReader(f, delimiter=";")
            for row in dr:
                ref = str(row.get("reference") or "").strip()
                if not ref:
                    continue
                idx[ref] = {
                    "acheteur": str(row.get("acheteur") or "").strip(),
                    "objet": str(row.get("objet") or "").strip(),
                }
        return idx
    except Exception:
        return {}


def _count_csv_rows(csv_path: Path) -> int:
    with open(csv_path, encoding='utf-8-sig') as f:
        return sum(1 for _ in csv.reader(f, delimiter=';')) - 1


def _consultation_folder_name(consultation_id: str) -> str:
    """
    Must match `core/pipeline.py` dossier folder naming:
    ref_clean = re.sub(r'[^\\w\\-]', '_', consultation.reference or consultation.id)[:30]
    """
    return re.sub(r"[^\w\-]", "_", consultation_id)[:30]


def _parse_pipeline_budget(value: Optional[str]) -> float:
    if not value:
        return 0.0
    v = value.strip()
    if not v or v == "-":
        return 0.0

    # Keep only digits and separators, then normalize.
    v = re.sub(r"[^0-9,\\.]", "", v)
    if not v:
        return 0.0

    # If both separators exist, assume comma is thousands and dot is decimal (rare here) or vice-versa.
    if "," in v and "." in v:
        # Heuristic: last separator is decimal.
        if v.rfind(",") > v.rfind("."):
            v = v.replace(".", "").replace(",", ".")
        else:
            v = v.replace(",", "")
    else:
        # Single-separator cases:
        # - Portal often uses "984 000,00" -> "984000,00" after cleanup (comma is decimal)
        # - Some exports may use "984000.00" (dot is decimal)
        if "," in v and "." not in v:
            # Treat trailing ",dd" (or ",d") as decimal separator; otherwise assume thousands separators.
            if re.search(r",\d{1,2}$", v):
                v = v.replace(",", ".")
            else:
                v = v.replace(",", "")
        elif "." in v and "," not in v:
            # Treat trailing ".dd" as decimal; otherwise assume thousands separators.
            if re.search(r"\.\d{1,2}$", v):
                pass
            else:
                v = v.replace(".", "")

    try:
        return float(v)
    except ValueError:
        return 0.0


def _parse_pipeline_deadline(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = value.strip()
    if not v or v == "-":
        return None

    # Portal sometimes includes a time: "27/03/2026 10:00"
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(v, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_pipeline_deadline_date(value: Optional[str]):
    iso = _parse_pipeline_deadline(value)
    if not iso:
        return None


def _deadline_is_expired(deadline_iso: Optional[str], today: Optional[date] = None) -> bool:
    """
    Return True if deadline is strictly before today.
    Accepts ISO date strings (YYYY-MM-DD) or datetimes (YYYY-MM-DDTHH:MM:SS...).
    """
    if not deadline_iso:
        return False
    try:
        d = datetime.fromisoformat(str(deadline_iso)).date()
    except Exception:
        try:
            d = date.fromisoformat(str(deadline_iso)[:10])
        except Exception:
            return False
    t = today or date.today()
    return d < t
    try:
        return datetime.fromisoformat(iso).date()
    except ValueError:
        return None


def _compute_rag_status(
    *,
    priority: str = "",
    score: int = 0,
    similarity_score: float = 0.0,
    deadline_iso: Optional[str] = None,
    liked: bool = False,
    existing: Optional[str] = None,
) -> str:
    """
    Compute a deterministic lifecycle status for the Dashboard.
    Goal: status evolves automatically without requiring DB migrations.
    """
    try:
        pr = (priority or "").strip().upper()
    except Exception:
        pr = ""

    # Preserve explicit existing status when it's not the default placeholder.
    try:
        ex = (existing or "").strip().lower()
    except Exception:
        ex = ""
    if ex and ex not in {"nouveau", "new"}:
        return ex

    # Excluded items
    if pr == "EXCLUDED":
        return "exclu"

    # Deadline-based evolution
    now = datetime.now().date()
    d = None
    if deadline_iso:
        try:
            d = datetime.fromisoformat(str(deadline_iso)).date()
        except Exception:
            d = None
    if d is not None:
        if d < now:
            return "expire"
        days_left = (d - now).days
        if days_left <= 3:
            return "urgent"

    # Engagement / qualification
    if liked:
        return "suivi"

    try:
        sim = float(similarity_score or 0.0)
    except Exception:
        sim = 0.0

    s = int(score or 0)
    if sim >= 0.75 or s >= 15 or pr == "HOT":
        return "qualifie"

    return "nouveau"


def _parse_pipeline_score(qualification: Optional[str]) -> int:
    if not qualification:
        return 0
    m = re.search(r"\\bScore\\s+(\\d+)\\b", qualification)
    return int(m.group(1)) if m else 0


def _parse_pipeline_domains(qualification: Optional[str]) -> list[str]:
    """
    Extract domains from the pipeline 'Qualification' string.
    Examples:
      - "DEV / DATA - Score 7" -> ["DEV", "DATA"]
      - "CLOUD - Score 5"      -> ["CLOUD"]
      - "Score 0" / empty      -> []
    """
    if not qualification:
        return []

    base = qualification.split("- Score", 1)[0].strip()
    if not base:
        return []

    # Excluded items often show "Score 0" without any domain label.
    if base.lower().startswith("score"):
        return []

    parts = [p.strip() for p in base.split("/") if p.strip()]
    return [p.upper() for p in parts]


# --- Domain classification (profile filtering) ---
# We keep it lightweight and deterministic (keyword-based), reusing the same intent as scripts/filter_it.py.
DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "AI": [
        "intelligence artificielle", "machine learning", "deep learning",
        "artificial intelligence", "chatbot", "nlp", "neural",
        "apprentissage automatique", "vision par ordinateur", "computer vision",
        "réseau de neurones", "reseau de neurones", "traitement du langage",
    ],
    "DATA": [
        "big data", "data lake", "datawarehouse", "data warehouse",
        "entrepôt de données", "entrepot de donnees", "analytics",
        "etl", "sql", "nosql", "hadoop", "spark", "mongodb", "postgresql",
        "oracle", "base de données", "base de donnees", "migration de données", "migration de donnees",
        "gestion des données", "gestion des donnees",
    ],
    "DEV": [
        "développement", "developpement", "development", "logiciel", "software",
        "application web", "application mobile", "site web", "portail web",
        "frontend", "back-end", "backend", "api", "microservice", "erp", "crm",
        "intégration", "integration", "refonte", "digitalisation",
    ],
    "CLOUD": [
        "cloud", "saas", "paas", "iaas", "virtualisation", "datacenter", "data center",
        "vmware", "azure", "aws", "kubernetes", "docker", "conteneur",
        "migration cloud", "stockage cloud", "sauvegarde cloud",
    ],
    "CYBERSECURITY": [
        "cybersécurité", "cybersecurite", "sécurité informatique", "securite informatique",
        "firewall", "antivirus", "pare-feu", "pentest", "soc", "siem",
        "chiffrement", "cryptage", "audit sécurité", "audit securite",
        "ransomware", "protection des données", "protection des donnees",
    ],
}

DOMAIN_SHORT_KW = {"nlp", "etl", "sql", "api", "erp", "crm", "aws", "soc", "siem"}


def _classify_domains(text: str) -> list[str]:
    if not text:
        return []
    t = text.lower()
    matched: list[str] = []
    for dom, kws in DOMAIN_KEYWORDS.items():
        for kw in kws:
            k = kw.strip().lower()
            if not k:
                continue
            if k in DOMAIN_SHORT_KW:
                if re.search(r"\b" + re.escape(k) + r"\b", t):
                    matched.append(dom)
                    break
            else:
                if k in t:
                    matched.append(dom)
                    break
    # Keep stable ordering for UI.
    order = {"AI": 0, "DATA": 1, "CLOUD": 2, "DEV": 3, "CYBERSECURITY": 4}
    return sorted(set(matched), key=lambda d: order.get(d, 99))


# --- Domain classification v2 (more conservative, to keep Service labels coherent) ---
_DOMAIN_SHORT_KW_V2 = {"nlp", "etl", "bi", "sql", "api", "erp", "crm", "aws", "soc", "siem", "vpn"}

_DOMAIN_RULES_V2: dict[str, dict[str, list[str]]] = {
    "AI": {
        "strong": [
            "intelligence artificielle", "artificial intelligence",
            "machine learning", "deep learning",
            "apprentissage automatique", "computer vision", "vision par ordinateur",
            "neural", "reseau de neurones", "réseau de neurones",
            "traitement du langage",
        ],
        "weak": ["nlp", "chatbot"],
    },
    "DATA": {
        "strong": [
            "big data", "data lake", "datawarehouse", "data warehouse",
            "entrepot de donnees", "entrepôt de données",
            "etl", "bi", "power bi", "tableau", "analytics",
            "hadoop", "spark",
        ],
        "weak": [
            "sql", "nosql", "postgresql", "mongodb", "oracle",
            "base de donnees", "base de données",
            "migration de donnees", "migration de données",
            "gestion des donnees", "gestion des données",
        ],
    },
    "DEV": {
        "strong": [
            "application web", "application mobile", "site web", "portail web",
            "frontend", "back-end", "backend", "microservice",
            "api", "refonte", "integration", "intégration",
        ],
        "weak": ["developpement", "développement", "development", "logiciel", "software", "digitalisation"],
    },
    "CLOUD": {
        "strong": [
            "cloud", "saas", "paas", "iaas",
            "virtualisation", "datacenter", "data center",
            "vmware", "azure", "aws", "kubernetes", "docker", "devops",
            "migration cloud", "stockage cloud", "sauvegarde cloud",
        ],
        "weak": [],
    },
    "CYBERSECURITY": {
        "strong": [
            "cybersecurite", "cybersécurité", "securite informatique", "sécurité informatique",
            "firewall", "pare-feu", "antivirus", "soc", "siem", "pentest",
            "ransomware", "vpn", "chiffrement", "cryptage",
        ],
        "weak": ["audit securite", "audit sécurité", "protection des donnees", "protection des données"],
    },
}


def _deaccent_lower_v2(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii").lower()


def _is_maintenance_like_text_v2(text: str) -> bool:
    t = _deaccent_lower_v2(text)
    return bool(re.search(r"\b(maintenance|entretien|support|assistance|renouvellement|abonnement|licence|licences)\b", t))


def _classify_domains_v2(text: str) -> list[str]:
    if not text:
        return []
    t = _deaccent_lower_v2(text)

    scores: dict[str, int] = {}
    strong_hits: dict[str, int] = {}
    for dom, rules in _DOMAIN_RULES_V2.items():
        s = 0
        sh = 0
        for kw in rules.get("strong", []):
            k = _deaccent_lower_v2(kw).strip()
            if not k:
                continue
            if k in _DOMAIN_SHORT_KW_V2:
                if re.search(r"\b" + re.escape(k) + r"\b", t):
                    s += 2
                    sh += 1
            elif k in t:
                s += 2
                sh += 1
        for kw in rules.get("weak", []):
            k = _deaccent_lower_v2(kw).strip()
            if not k:
                continue
            if k in _DOMAIN_SHORT_KW_V2:
                if re.search(r"\b" + re.escape(k) + r"\b", t):
                    s += 1
            elif k in t:
                s += 1
        scores[dom] = s
        strong_hits[dom] = sh

    maintenance_like = _is_maintenance_like_text_v2(t)
    cyber_strong = strong_hits.get("CYBERSECURITY", 0) > 0 or scores.get("CYBERSECURITY", 0) >= 2

    if maintenance_like and strong_hits.get("DEV", 0) == 0:
        scores["DEV"] = 0
    if maintenance_like and strong_hits.get("DATA", 0) == 0:
        scores["DATA"] = 0
    if cyber_strong and strong_hits.get("DATA", 0) == 0:
        scores["DATA"] = 0

    order = {"AI": 0, "DATA": 1, "CLOUD": 2, "DEV": 3, "CYBERSECURITY": 4}
    matched = [d for d, s in scores.items() if s > 0]
    return sorted(set(matched), key=lambda d: order.get(d, 99))


def _postprocess_domains_v2(domains: list[str], text: str) -> list[str]:
    if not domains:
        return []
    t = _deaccent_lower_v2(text)
    maintenance_like = _is_maintenance_like_text_v2(t)
    has_cyber = "CYBERSECURITY" in [str(d).strip().upper() for d in domains] or bool(
        re.search(r"\b(antivirus|firewall|pare-feu|soc|siem|pentest|vpn)\b", t)
    )

    out = [str(d).strip().upper() for d in domains if d]

    def has_any_substr(keys: list[str]) -> bool:
        return any((_deaccent_lower_v2(k) in t) for k in keys if k)

    dev_strong = has_any_substr(_DOMAIN_RULES_V2["DEV"]["strong"])
    data_strong = has_any_substr(_DOMAIN_RULES_V2["DATA"]["strong"])

    if maintenance_like and not dev_strong and "DEV" in out:
        out = [d for d in out if d != "DEV"]
    if (maintenance_like or has_cyber) and not data_strong and "DATA" in out:
        out = [d for d in out if d != "DATA"]

    order = {"AI": 0, "DATA": 1, "CLOUD": 2, "DEV": 3, "CYBERSECURITY": 4}
    return sorted(set(out), key=lambda d: order.get(d, 99))


def _merge_domains(primary: list[str], inferred: list[str]) -> list[str]:
    # Normalize to upper-case canonical profile keys.
    out: list[str] = []
    for d in (primary or []) + (inferred or []):
        if not d:
            continue
        u = str(d).strip().upper()
        if u in {"CYBER", "CYBERSECURITE", "CYBERSECURITÉ"}:
            u = "CYBERSECURITY"
        if u in {"DATA", "AI", "DEV", "CLOUD", "CYBERSECURITY"} and u not in out:
            out.append(u)
    return out


def _detect_service(domains: list[str], title: str, domaines_activite: str, qualification: str) -> str:
    """
    Return a short "service" label for UI (used in the Service column + drawer).

    Preferred labels: AI / DATA / CLOUD / DEV, else IT.

    Notes:
    - Pipeline "domains" (parsed from Qualification) are not always reliable. We keep them,
      but we override DEV/DATA when the text clearly describes a generic maintenance/support
      purchase (ex: "ENTRETIEN / MAINTENANCE ... ANTIVIRUS").
    - Keyword matching is done on a de-accented string to better handle French text.
    """
    raw_text = f"{title or ''} {domaines_activite or ''} {qualification or ''}"
    text = unicodedata.normalize("NFKD", raw_text).encode("ascii", "ignore").decode("ascii").lower()

    def has_any_substr(keys: list[str]) -> bool:
        return any(k in text for k in keys)

    def has_any_re(patterns: list[str]) -> bool:
        return any(re.search(p, text) for p in patterns)

    # Generic "maintenance/support/renewal" procurements should stay IT unless there is
    # a strong Cloud/Ai/Data/Dev signal.
    is_maintenance_like = has_any_substr(
        [
            "maintenance",
            "entretien",
            "support",
            "assistance",
            "abonnement",
            "licence",
            "licences",
            "renouvel",
            "antivirus",
            "mise a jour",
            "mise a niveau",
            "correctif",
            "patch",
        ]
    )

    def keyword_label() -> str:
        # AI
        if has_any_re([r"\bia\b", r"intelligence artificielle", r"machine learning", r"deep learning", r"\bnlp\b", r"\bgenai\b", r"\bllm\b", r"\brag\b"]):
            return "AI"

        # CYBER
        if has_any_substr(["cyber", "securite", "sécurité", "firewall", "pare-feu", "antivirus", "soc", "siem", "pentest", "vpn"]) or has_any_re(
            [r"\bsiem\b", r"\bsoc\b", r"\bvpn\b"]
        ):
            return "CYBER"

        # CLOUD
        if has_any_substr(["cloud", "virtualis", "vmware", "kubernetes", "k8s", "azure", "aws", "gcp"]) or has_any_re(
            [r"\bdocker\b", r"\bsauvegarde\b", r"\bbackup\b"]
        ):
            return "CLOUD"

        # DATA (avoid "donnees" alone; require analytics/bi/etl/warehouse/etc.)
        if has_any_substr(
            [
                "business intelligence",
                "entrepot de donnees",
                "data warehouse",
                "datamart",
                "data lake",
                "big data",
                "data science",
                "science des donnees",
                "etl",
                "analytics",
                "analyse de donnees",
                "reporting",
                "power bi",
                "tableau",
                "hadoop",
                "spark",
            ]
        ) or has_any_re([r"\bbi\b", r"\betl\b", r"\bsql\b", r"\bnosql\b"]):
            return "DATA"

        # DEV (avoid classifying generic software purchase/maintenance as DEV)
        if has_any_substr(
            [
                "developpement",
                "devops",
                "integration",
                "conception",
                "realisation",
                "implementation",
                "refonte",
                "application web",
                "application mobile",
                "site web",
                "portail",
                "api",
                "microservice",
                "front-end",
                "back-end",
            ]
        ):
            return "DEV"

        return "IT"

    kw = keyword_label()

    # If pipeline gave us domains, keep them unless we have a strong reason to override.
    if domains:
        # Display-friendly alias: keep CYBERSECURITY for filtering, but show CYBER in the UI label.
        show = [("CYBER" if d == "CYBERSECURITY" else d) for d in domains]
        dom = " / ".join(show[:2]) if len(show) > 1 else show[0]

        # Maintenance-like procurements often get misclassified as DEV/DATA just because
        # they mention "logiciel" or "donnees". In that case, prefer the keyword label.
        if is_maintenance_like and dom in {"DEV", "DATA"} and kw == "IT":
            return "IT"

        return dom

    # No domains from pipeline -> keyword inference.
    # If it's maintenance-like and we did not detect a stronger domain, keep IT.
    if is_maintenance_like and kw in {"IT", "DEV", "DATA"}:
        # DEV/DATA require stronger signals; maintenance alone shouldn't force them.
        return "IT" if kw in {"DEV", "DATA"} else kw

    return kw


def _compute_similarity_score(priority: str, score: int) -> float:
    """
    Pipeline exports currently do not include an explicit similarity_score.
    We derive a stable proxy score for UI indicators (Recommended/Potential/Normal).
    """
    p = (priority or "").upper().strip()
    if p == "HOT":
        base = 0.82
    elif p == "WARM":
        base = 0.66
    elif p == "COLD":
        base = 0.55
    else:
        base = 0.0

    # Small lift from the qualification score (0..10 assumed).
    lift = max(0.0, min(float(score) / 20.0, 0.25))
    return round(min(1.0, base + lift), 3)


def _parse_pipeline_requirements(value: Optional[str]) -> list[str]:
    if not value:
        return []
    parts = [p.strip() for p in re.split(r"\s*\|\s*", value) if p.strip()]
    return parts


def _load_latest_pipeline_results_index() -> dict[str, dict]:
    """
    Index latest `data/pipeline_results_*.csv` by ID (reference) to enrich `/pipeline/score` output
    with descriptions/requirements/deadline/budget when available.
    """
    latest = _find_latest("pipeline_results_*.csv")
    if not latest or not latest.exists():
        return {}

    index: dict[str, dict] = {}
    with open(latest, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            key = (row.get("ID") or "").strip()
            if not key:
                continue
            index[key] = row
    return index


def _load_latest_pipeline_results_rows() -> list[dict]:
    latest = _find_latest("pipeline_results_*.csv")
    if not latest or not latest.exists():
        return []

    try:
        mtime = float(latest.stat().st_mtime)
    except Exception:
        mtime = 0.0

    with _cache_lock:
        if (
            _pipeline_rows_cache.get("path") == str(latest)
            and float(_pipeline_rows_cache.get("mtime") or 0.0) == mtime
            and isinstance(_pipeline_rows_cache.get("rows"), list)
        ):
            # Return a shallow copy to prevent accidental mutation.
            return list(_pipeline_rows_cache["rows"])  # type: ignore[list-item]

    rows: list[dict] = []
    with open(latest, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            rows.append(row)

    with _cache_lock:
        _pipeline_rows_cache["path"] = str(latest)
        _pipeline_rows_cache["mtime"] = mtime
        _pipeline_rows_cache["rows"] = rows
        # Drop derived caches when the source CSV changes.
        _opps_base_cache.clear()

    return list(rows)


def _load_latest_pipeline_titles_index() -> dict[str, str]:
    """Map opportunity ID -> title from latest pipeline export, when available."""
    latest = _find_latest("pipeline_results_*.csv")
    rows = _load_latest_pipeline_results_rows()
    index: dict[str, str] = {}
    for row in rows:
        key = (row.get("ID") or "").strip()
        if not key:
            continue
        title = (row.get("Titre") or "").strip()
        if title:
            index[key] = title
    return index


def _load_latest_pipeline_deadlines_index() -> dict[str, Optional[str]]:
    """Map opportunity ID -> ISO deadline date (YYYY-MM-DD) from latest pipeline export, when available."""
    rows = _load_latest_pipeline_results_rows()
    index: dict[str, Optional[str]] = {}
    for row in rows:
        key = (row.get("ID") or "").strip()
        if not key:
            continue
        index[key] = _parse_pipeline_deadline(row.get("Deadline"))
    return index


def _load_latest_pipeline_service_domains_index() -> dict[str, dict]:
    """
    Map opportunity ID -> {"domains": [...], "service": "..."} from latest pipeline export.
    This keeps Reports consistent with Dashboard classification.
    """
    rows = _load_latest_pipeline_results_rows()
    index: dict[str, dict] = {}
    for row in rows:
        oid = (row.get("ID") or "").strip()
        if not oid:
            continue
        qual = (row.get("Qualification") or "").strip()
        pipeline_domains = _parse_pipeline_domains(qual)
        title = (row.get("Titre") or "").strip()
        domaines_activite = (row.get("Domaines_Activite") or "").strip()
        desc_t = (row.get("Description_Technique") or "").strip()
        desc_f = (row.get("Description_Fonctionnelle") or "").strip()
        reqs = (row.get("Requirements") or "").strip()
        text_for_domains = " ".join([title, domaines_activite, qual, desc_t, desc_f, reqs])
        inferred_domains = _classify_domains_v2(text_for_domains)
        domains = _postprocess_domains_v2(_merge_domains(pipeline_domains, inferred_domains), text_for_domains)
        service = _detect_service(domains, title=title, domaines_activite=domaines_activite, qualification=qual)
        index[oid] = {"domains": domains, "service": service}
    return index


def _load_dossier_deadline_from_analysis(dossier_dir: Path) -> Optional[str]:
    """
    Best-effort fallback: read the per-opportunity analysis JSON stored in the dossier folder
    and extract the deadline/date_limite.
    """
    try:
        p = dossier_dir / f"analyse_{dossier_dir.name}.json"
        if not p.exists() or not p.is_file():
            # Fallback to any analyse_*.json in the folder (legacy naming)
            cand = sorted(dossier_dir.glob("analyse_*.json"))
            p = cand[0] if cand else None
        if not p:
            return None

        with open(p, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)

        raw = None
        if isinstance(data, dict):
            raw = (
                data.get("deadline")
                or data.get("date_limite")
                or data.get("date_et_heure_limite")
                or data.get("date_et_heure_limite_remise_plis")
            )
        if not raw:
            return None
        return _parse_pipeline_deadline(str(raw))
    except Exception:
        return None


def _opportunity_dict_from_pipeline_row(row: dict, raw_scrape_index: dict) -> Optional[dict]:
    """Build one Dashboard-shaped opportunity dict from a pipeline_results CSV row (no liked/rag_status)."""
    oid = (row.get("ID") or "").strip()
    if not oid:
        return None
    qual = (row.get("Qualification") or "").strip()
    score = _parse_pipeline_score(qual)
    priority = (row.get("Priorite") or "").strip()
    title = (row.get("Titre") or "").strip()
    domaines_activite = (row.get("Domaines_Activite") or "").strip()
    desc_t = (row.get("Description_Technique") or "").strip()
    desc_f = (row.get("Description_Fonctionnelle") or "").strip()
    reqs = (row.get("Requirements") or "").strip()

    domains_col = (row.get("Domains") or row.get("Domain") or "").strip()
    pipeline_domains = _parse_pipeline_domains(qual)
    if domains_col:
        pipeline_domains = _merge_domains(
            pipeline_domains,
            [p.strip() for p in domains_col.split("/") if p.strip()],
        )

    text_for_domains = " ".join([title, domaines_activite, qual, desc_t, desc_f, reqs])
    inferred_domains = _classify_domains_v2(text_for_domains)
    domains = _postprocess_domains_v2(_merge_domains(pipeline_domains, inferred_domains), text_for_domains)

    service = (row.get("Service") or "").strip() or _detect_service(
        domains, title=title, domaines_activite=domaines_activite, qualification=qual
    )
    similarity_score = _compute_similarity_score(priority=priority, score=score)

    buyer = (row.get("Client") or "").strip()
    buyer_norm = _normalize_buyer_label(buyer)
    if buyer_norm.lower() in {"", "non identifie", "non identifié", "-", "n/a"}:
        raw = raw_scrape_index.get(oid) or {}
        cand = _normalize_buyer_label(str(raw.get("acheteur") or "").strip())
        if not cand:
            cand = _normalize_buyer_label(_infer_buyer_from_objet(str(raw.get("objet") or "")))
        if not cand:
            cand = _normalize_buyer_label(_infer_buyer_from_title(title))
        buyer_norm = cand or buyer_norm

    objet = str((raw_scrape_index.get(oid) or {}).get("objet") or "").strip()

    return {
        "id": oid,
        "reference": oid,
        "priority": priority,
        "qualification": qual,
        "similarity_score": similarity_score,
        "domains": domains,
        "domain": domains,
        "sector": domains[0] if domains else "",
        "service": service,
        "title": title,
        "buyer": buyer_norm,
        "organization": buyer_norm,
        "objet": objet,
        "deadline": _parse_pipeline_deadline(row.get("Deadline")),
        "budget": _parse_pipeline_budget(row.get("Budget_Estime")),
        "score": score,
        "description_technique": desc_t,
        "description_fonctionnelle": desc_f,
        "requirements": _parse_pipeline_requirements(reqs),
        "url": (row.get("URL_Offre") or "").strip(),
        "cps_source": (row.get("CPS_Source") or "").strip(),
        "domaines_activite": domaines_activite,
    }


def _active_dossier_opportunity_ids() -> set[str]:
    """
    Opportunity IDs that have at least one generated dossier file on disk and a non-expired deadline
    (from pipeline CSV or analyse_*.json in the dossier folder). Matches Reports / dossiers index scope.
    """
    root = PROJECT_ROOT / "dossiers_generes"
    if not root.is_dir():
        return set()
    rows = _load_latest_pipeline_results_rows()
    if not rows:
        return set()

    deadlines_by_folder: dict[str, Optional[str]] = {}
    folder_to_id: dict[str, str] = {}
    for row in rows:
        oid = (row.get("ID") or "").strip()
        if not oid:
            continue
        fn = _consultation_folder_name(oid)
        folder_to_id[fn] = oid
        dl = _parse_pipeline_deadline(row.get("Deadline"))
        if dl:
            deadlines_by_folder[fn] = dl

    today = datetime.now().date()
    out: set[str] = set()
    for folder in root.iterdir():
        if not folder.is_dir():
            continue
        dl = deadlines_by_folder.get(folder.name) or _load_dossier_deadline_from_analysis(folder)
        if not dl:
            continue
        try:
            dl_date = datetime.fromisoformat(str(dl)).date()
        except ValueError:
            continue
        if dl_date < today:
            continue
        kids = [p for p in folder.iterdir() if p.is_file()]
        if not _pick_latest_dossiers(kids):
            continue
        oid = folder_to_id.get(folder.name)
        if oid:
            out.add(oid)
    return out


def _merge_opportunities_with_active_dossier_folders(
    out_items: list[dict],
    include_excluded: bool,
    include_expired: bool,
    likes: dict,
) -> list[dict]:
    """Append pipeline rows for opportunities that exist on disk in dossiers_generes but are missing from out_items."""
    try:
        rows = _load_latest_pipeline_results_rows()
    except Exception:
        return out_items
    if not rows:
        return out_items

    have = {
        str(o.get("id") or o.get("reference") or "").strip()
        for o in out_items
        if (o.get("id") or o.get("reference"))
    }
    try:
        want = _active_dossier_opportunity_ids()
    except Exception:
        return out_items

    missing = sorted(want - have)
    if not missing:
        return out_items

    raw_scrape_index = _load_latest_raw_scrape_index()
    rows_by_id = {(r.get("ID") or "").strip(): r for r in rows if (r.get("ID") or "").strip()}
    today = date.today()
    merged = list(out_items)

    for oid in missing:
        row = rows_by_id.get(oid)
        if not row:
            continue
        priority = (row.get("Priorite") or "").strip()
        if (not include_excluded) and priority.upper() == "EXCLUDED":
            continue
        o = _opportunity_dict_from_pipeline_row(row, raw_scrape_index)
        if not o:
            continue
        if not include_expired:
            if not o.get("deadline"):
                continue
            if _deadline_is_expired(o.get("deadline"), today=today):
                continue
        oid2 = str(o.get("id") or "").strip()
        liked = _is_liked(oid2, likes)
        merged.append({
            **o,
            "liked": liked,
            "rag_status": _compute_rag_status(
                priority=str(o.get("priority") or ""),
                score=int(o.get("score") or 0),
                similarity_score=float(o.get("similarity_score") or 0.0),
                deadline_iso=o.get("deadline"),
                liked=bool(liked),
                existing=o.get("rag_status"),
            ),
        })
    return merged


def _sync_db_from_pipeline_results(db: "Session") -> dict:
    """
    Upsert opportunities into SQLite from the latest `pipeline_results_*.csv` export.

    Note: pipeline_results is the canonical source for the Dashboard.
    """
    if not _DB_AVAILABLE:
        raise HTTPException(501, "DB not available (SQLAlchemy missing)")

    latest = _find_latest("pipeline_results_*.csv")
    if not latest or not latest.exists():
        raise HTTPException(404, "Aucun pipeline_results_*.csv trouvé")

    inserted = 0
    updated = 0
    new_hot_refs: list[tuple[str, str, list[str]]] = []  # (ref, title, domains)

    # SessionLocal has autoflush=False; without a local cache, duplicate refs in the same CSV
    # can create multiple pending rows and fail the UNIQUE(ref) constraint at commit time.
    by_ref: dict[str, Opportunity] = {}

    with open(latest, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            ref = (row.get("ID") or "").strip()
            if not ref:
                continue

            title = (row.get("Titre") or "").strip()
            buyer = (row.get("Client") or "").strip()
            level = (row.get("Priorite") or "").strip()
            qualification = (row.get("Qualification") or "").strip()

            budget = _parse_pipeline_budget(row.get("Budget_Estime"))
            deadline = _parse_pipeline_deadline_date(row.get("Deadline"))
            score = _parse_pipeline_score(qualification)

            desc_tech = (row.get("Description_Technique") or "").strip()
            desc_func = (row.get("Description_Fonctionnelle") or "").strip()
            requirements = (row.get("Requirements") or "").strip()
            url = (row.get("URL_Offre") or "").strip()

            pipeline_domains = _parse_pipeline_domains(qualification)
            domaines_activite = (row.get("Domaines_Activite") or "").strip()
            text_for_domains = " ".join([title, domaines_activite, qualification, desc_tech, desc_func, requirements])
            inferred_domains = _classify_domains_v2(text_for_domains)
            domains = _postprocess_domains_v2(_merge_domains(pipeline_domains, inferred_domains), text_for_domains)

            sector = domains[0] if domains else (qualification.split(" - ")[0].strip() if qualification else "")
            description = desc_func or desc_tech or title

            obj = by_ref.get(ref)
            if obj is None:
                obj = db.query(Opportunity).filter(Opportunity.ref == ref).one_or_none()
            if obj is None:
                obj = Opportunity(ref=ref)
                db.add(obj)
                inserted += 1
                if (level or "").strip().upper() == "HOT":
                    new_hot_refs.append((ref, title, domains))
            else:
                updated += 1
            by_ref[ref] = obj

            obj.title = title
            obj.buyer = buyer
            obj.budget = budget
            obj.deadline = deadline
            obj.score = float(score)
            obj.level = level
            obj.sector = sector
            obj.description = description
            obj.description_technique = desc_tech
            obj.description_fonctionnelle = desc_func
            obj.requirements = requirements
            obj.url = url
            # Store profile domains + derived service label for multi-profile filtering.
            try:
                obj.domains = json.dumps(domains, ensure_ascii=True)
            except Exception:
                obj.domains = " / ".join(domains) if domains else ""
            obj.service = _detect_service(domains, title=title, domaines_activite=domaines_activite, qualification=qualification)

    db.commit()

    # Create notifications for new HOT opportunities (best-effort).
    try:
        if new_hot_refs:
            users = _list_known_users()
            now = datetime.utcnow()
            cutoff = now - timedelta(hours=24)
            for ref, title, domains in new_hot_refs:
                o_stub = {"domains": domains, "service": "", "title": title, "qualification": ""}
                notif_profile = _notification_bucket_for_opportunity(o_stub)
                for u in users:
                    up = str(_get_user_profile(str(u)).get("profile") or "GLOBAL").strip().upper()
                    if up == "CYBER":
                        up = "CYBERSECURITY"
                    if up not in {"GLOBAL", "AI", "DATA", "CLOUD", "DEV", "CYBERSECURITY"}:
                        up = "GLOBAL"
                    if not _opportunity_matches_user_profile(o_stub, up):
                        continue

                    exists = (
                        db.query(Notification)
                        .filter(Notification.user_id == u)
                        .filter(Notification.type == "new_hot_opportunity")
                        .filter(Notification.opportunity_id == ref)
                        .filter(Notification.profile == notif_profile)
                        .filter(Notification.created_at >= cutoff)
                        .count()
                    )
                    if exists:
                        continue

                    _create_notification(
                        db,
                        user_id=u,
                        message=f"New HOT opportunity detected: {title or ref}",
                        ntype="new_hot_opportunity",
                        opportunity_id=ref,
                        profile=notif_profile,
                    )
            db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    return {"source": str(latest), "inserted": inserted, "updated": updated}


def _pick_latest_dossiers(files: list[Path]) -> list[Path]:
    """
    Keep only one file per (kind, ext): technique/admin x docx/pdf.

    This avoids duplicate variants created by multiple runs and keeps the UI consistent.
    """
    best: dict[tuple[str, str], Path] = {}

    for f in files:
        if not f.is_file() or f.name.startswith("~$"):
            continue

        ext = f.suffix.lower().lstrip(".")
        if ext not in ("docx", "pdf"):
            continue

        name_lower = f.name.lower()
        if "technique" in name_lower:
            kind = "technique"
        elif "administratif" in name_lower or "admin" in name_lower:
            kind = "administratif"
        else:
            continue

        key = (kind, ext)
        current = best.get(key)
        if current is None or f.stat().st_mtime > current.stat().st_mtime:
            best[key] = f

    # Stable ordering: technique first, then administratif; docx then pdf.
    order_kind = {"technique": 0, "administratif": 1}
    order_ext = {"docx": 0, "pdf": 1}
    return sorted(best.values(), key=lambda p: (order_kind.get("technique" if "technique" in p.name.lower() else "administratif", 9), order_ext.get(p.suffix.lower().lstrip("."), 9)))


# ── Scraping ─────────────────────────────────────────────────────────────────

async def _run_scrape(fast_mode: bool = False, concurrency: int = 5, webhook_url: Optional[str] = None):
    """Run the deep scraper asynchronously."""
    _status["scraping"]["running"] = True
    _status["scraping"]["error"] = None
    _status["scraping"]["started_at"] = datetime.now().isoformat()
    start = time.time()
    try:
        timeout_s = int(os.environ.get("SCRAPE_TIMEOUT_SEC", "1200"))  # default 20 min

        async def _do_work():
            from scripts.scrape_deep import DeepScraper
            scraper = DeepScraper(skip_enrich=fast_mode, concurrency=concurrency)
            try:
                await scraper.scrape_main_portal()
            except Exception as e:
                # Keep partial results if main portal had transient errors.
                logger.warning(f"Scrape main portal failed (continuing): {e}")

            # In fast mode, optionally skip the heavy BDC scan to ensure we always produce a CSV quickly.
            skip_bdc_fast = os.environ.get("SCRAPE_FAST_SKIP_BDC", "1").strip() != "0"
            if not (fast_mode and skip_bdc_fast):
                try:
                    # This step is synchronous and can take time.
                    await asyncio.to_thread(scraper.scrape_bdc_all_pages)
                except Exception as e:
                    logger.warning(f"Scrape BDC failed (continuing): {e}")

            # `fast_mode` must truly skip the heavy detail enrichment phase.
            if not fast_mode:
                try:
                    await scraper.enrich_main_portal_details()
                except Exception as e:
                    logger.warning(f"Enrich main portal details failed (continuing): {e}")

            try:
                scraper.display_stats()
            except Exception:
                pass

            # Always export if we have any results.
            if getattr(scraper, "results", None):
                return scraper.export_csv()
            raise RuntimeError("Aucun resultat scraping (0 consultations)")

        csv_file = await asyncio.wait_for(_do_work(), timeout=timeout_s)
        elapsed = time.time() - start
        _status["scraping"]["last_csv"] = csv_file
        _status["scraping"]["last_run"] = datetime.now().isoformat()
        logger.info(f"Scraping terminé en {elapsed:.0f}s → {csv_file}")
    except asyncio.TimeoutError:
        _status["scraping"]["error"] = f"Scraping timeout after {os.environ.get('SCRAPE_TIMEOUT_SEC','1200')}s"
        logger.exception("Scraping timeout")
    except Exception as e:
        _status["scraping"]["error"] = str(e)
        logger.exception("Scraping failed")
    finally:
        _status["scraping"]["running"] = False
        _status["scraping"]["started_at"] = None
        if webhook_url:
            try:
                import requests
                logger.info(f"Appel du webhook n8n: {webhook_url}")
                requests.post(webhook_url, json={"status": "done", "scraping": dict(_status["scraping"])}, timeout=10)
            except Exception as e:
                logger.error(f"Echec appel webhook: {e}")

@app.post("/scrape")
async def scrape(req: ScrapeRequest, background_tasks: BackgroundTasks):
    if _status["scraping"]["running"]:
        return {
            "status": "already_running",
            "message": "Scraping deja en cours",
            "scraping": dict(_status["scraping"]),
        }

    fast = req.fast_mode
    conc = req.concurrency
    background_tasks.add_task(asyncio.to_thread, lambda: asyncio.run(_run_scrape(fast_mode=fast, concurrency=conc, webhook_url=req.webhook_url)))
    mode = "rapide (sans enrichissement)" if fast else f"complet ({conc} tabs)"
    return {"status": "started", "message": f"Scraping lancé en arrière-plan - mode {mode}"}

@app.post("/scrape/sync")
async def scrape_sync(req: ScrapeRequest):
    if _status["scraping"]["running"]:
        return {
            "status": "already_running",
            "message": "Scraping deja en cours",
            "scraping": dict(_status["scraping"]),
        }
    fast = req.fast_mode
    conc = req.concurrency
    import asyncio
    await asyncio.to_thread(lambda: asyncio.run(_run_scrape(fast_mode=fast, concurrency=conc, webhook_url=req.webhook_url)))
    result = dict(_status["scraping"])
    from pathlib import Path
    # If last_csv was not set (edge cases), fall back to latest CSV in data/.
    if not result.get("last_csv"):
        csv_found = _find_latest_csv()
        if csv_found:
            _status["scraping"]["last_csv"] = str(csv_found)
            result["last_csv"] = str(csv_found)
    if result.get("last_csv") and Path(result["last_csv"]).exists():
        result["rows"] = _count_csv_rows(Path(result["last_csv"]))
    return {"status": "done", "scraping": result}


@app.get("/scrape")
async def scrape_info():
    """Endpoint d'aide (tests navigateur): indique comment lancer le scraping via POST."""
    return {
        "message": "Utilisez POST /scrape pour lancer le scraping.",
        "example_body": {"fast_mode": True, "concurrency": 5},
        "status_url": "/scrape/status",
    }


@app.get("/scrape/status")
async def scrape_status():
    """Statut du scraping."""
    result = dict(_status["scraping"])
    # Auto-heal: if scraping is stuck (running too long), reset it.
    if result.get("running") and result.get("started_at"):
        try:
            started = datetime.fromisoformat(str(result["started_at"]))
            timeout_s = int(os.environ.get("SCRAPE_TIMEOUT_SEC", "1200"))
            if (datetime.now() - started).total_seconds() > max(timeout_s, 300) + 30:
                _status["scraping"]["running"] = False
                _status["scraping"]["error"] = "Scraping was stuck and has been reset by /scrape/status"
                _status["scraping"]["started_at"] = None
                result = dict(_status["scraping"])
        except Exception:
            pass
    if result.get("last_csv") and Path(result["last_csv"]).exists():
        result["rows"] = _count_csv_rows(Path(result["last_csv"]))
    # If last_csv isn't tracked but a latest CSV exists, expose it for n8n/dashboard.
    if not result.get("last_csv"):
        csv_found = _find_latest_csv()
        if csv_found:
            result["last_csv"] = str(csv_found)
            try:
                result["rows"] = _count_csv_rows(csv_found)
            except Exception:
                pass
    return result


# ── Pipeline ─────────────────────────────────────────────────────────────────

def _run_pipeline_sync(req: PipelineRequest):
    """Run the full pipeline synchronously (called in thread)."""
    _status["pipeline"]["running"] = True
    _status["pipeline"]["error"] = None
    try:
        from core.pipeline import Pipeline, Priority

        csv_path = req.csv_path
        if not csv_path:
            csv_found = _find_latest_csv()
            if not csv_found:
                raise FileNotFoundError("Aucun CSV trouvé dans data/")
            csv_path = str(csv_found)

        min_priority = Priority.WARM
        if req.hot_only:
            min_priority = Priority.HOT
        elif req.all_priorities:
            min_priority = Priority.COLD

        pipeline = Pipeline(
            output_dir="dossiers_generes",
            use_nlp=True,
            enrich_cps=req.enrich_cps,
            use_rag=req.use_rag,
        )

        results = pipeline.run(
            csv_path=csv_path,
            generate=req.generate_dossiers,
            min_generate_priority=min_priority,
        )

        # Save report
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = f"data/pipeline_report_{ts}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)

        _status["pipeline"]["last_report"] = report_path
        _status["pipeline"]["last_run"] = datetime.now().isoformat()
        logger.info(f"Pipeline terminé → {report_path}")

        # Optional: persist latest export into SQLite for external queries/BI.
        if _DB_AVAILABLE:
            try:
                from app.database import SessionLocal

                session = SessionLocal()
                try:
                    _sync_db_from_pipeline_results(session)
                finally:
                    session.close()
            except Exception as e:
                logger.warning(f"DB sync skipped/failed: {e}")

        return results

    except Exception as e:
        _status["pipeline"]["error"] = str(e)
        logger.exception("Pipeline failed")
        raise
    finally:
        _status["pipeline"]["running"] = False


def _run_pipeline_lite_sync(req: PipelineRequest):
    """
    Fast path: scoring + export only.
    Goal: update dashboard/results quickly without running enrichment/RAG/dossiers.

    Note: We still generate template-based descriptions (tech/func/requirements) because:
    - they do NOT require spaCy/LLM
    - the dashboard relies on these fields being populated in exported results/DB
    """
    _status["pipeline"]["running"] = True
    _status["pipeline"]["error"] = None
    try:
        from core.pipeline import Pipeline, Priority, NLPAnalyzer

        csv_path = req.csv_path
        if not csv_path:
            csv_found = _find_latest_csv()
            if not csv_found:
                raise FileNotFoundError("Aucun CSV trouvé dans data/")
            csv_path = str(csv_found)

        pipeline = Pipeline(
            output_dir="dossiers_generes",
            use_nlp=False,
            enrich_cps=False,
            use_rag=False,
        )
        pipeline.load_csv(csv_path)
        score_stats = pipeline.score_all()

        # Generate descriptions/requirements for ALL opportunities (fast, no spaCy/LLM).
        # This makes sure the exported CSV/XLSX + DB have non-empty Description_* fields.
        try:
            _ = pipeline.analyze_nlp(min_priority=Priority.COLD)  # fills HOT/WARM/COLD

            # Also fill excluded items (or any remaining blanks) to keep dashboard consistent.
            desc_analyzer = NLPAnalyzer.__new__(NLPAnalyzer)
            desc_analyzer._nlp = None
            for c in pipeline.consultations:
                if (not (c.description_technique or "").strip()) or (not (c.description_fonctionnelle or "").strip()) or (not c.requirements):
                    try:
                        desc_analyzer.generate_descriptions(c)
                        # requirements are created by generate_descriptions()
                    except Exception:
                        # Never fail the lite pipeline because a single description failed.
                        pass
        except Exception as e:
            logger.warning(f"Descriptions generation skipped/failed (lite): {e}")

        # Export results (CSV + XLSX) so Dashboard can load `/results/opportunities`
        xlsx_out = pipeline.export_results()

        results = {
            "status": "completed",
            "csv": csv_path,
            "stages": {
                "score": score_stats,
                "descriptions": {"enabled": True},
                "export": {"xlsx": xlsx_out},
            },
            "summary": {
                "total": int(score_stats.get("total", 0) or 0),
                "relevant": int((score_stats.get("hot", 0) or 0) + (score_stats.get("warm", 0) or 0) + (score_stats.get("cold", 0) or 0)),
                "hot": int(score_stats.get("hot", 0) or 0),
                "warm": int(score_stats.get("warm", 0) or 0),
                "cold": int(score_stats.get("cold", 0) or 0),
            },
        }

        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = f"data/pipeline_report_lite_{ts}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)

        _status["pipeline"]["last_report"] = report_path
        _status["pipeline"]["last_run"] = datetime.now().isoformat()
        logger.info(f"Pipeline lite terminé: {report_path}")

        if _DB_AVAILABLE:
            try:
                from app.database import SessionLocal
                session = SessionLocal()
                try:
                    _sync_db_from_pipeline_results(session)
                finally:
                    session.close()
            except Exception as e:
                logger.warning(f"DB sync skipped/failed (lite): {e}")

        return results
    except Exception as e:
        _status["pipeline"]["error"] = str(e)
        logger.exception("Pipeline lite failed")
        raise
    finally:
        _status["pipeline"]["running"] = False


@app.post("/pipeline/run")
async def pipeline_run(req: PipelineRequest, background_tasks: BackgroundTasks):
    """Lance le pipeline complet en arrière-plan."""
    if _status["pipeline"]["running"]:
        raise HTTPException(409, "Pipeline already running")

    background_tasks.add_task(asyncio.to_thread, _run_pipeline_sync, req)
    return {"status": "started", "message": "Pipeline lancé en arrière-plan"}


@app.post("/pipeline/run-sync")
async def pipeline_run_sync(req: PipelineRequest):
    """Lance le pipeline et attend le résultat (pour n8n)."""
    if _status["pipeline"]["running"]:
        raise HTTPException(409, "Pipeline already running")

    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, _run_pipeline_sync, req)
    return results


@app.post("/pipeline/run-lite")
async def pipeline_run_lite(req: PipelineRequest, background_tasks: BackgroundTasks):
    """Lance le pipeline 'lite' en arrière-plan (scoring + export seulement)."""
    if _status["pipeline"]["running"]:
        raise HTTPException(409, "Pipeline already running")
    background_tasks.add_task(asyncio.to_thread, _run_pipeline_lite_sync, req)
    return {"status": "started", "mode": "lite"}


@app.post("/pipeline/run-lite-sync")
async def pipeline_run_lite_sync(req: PipelineRequest):
    """Lance le pipeline 'lite' et attend le résultat (pour n8n)."""
    if _status["pipeline"]["running"]:
        raise HTTPException(409, "Pipeline already running")
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, _run_pipeline_lite_sync, req)
    return results


@app.get("/pipeline/status")
async def pipeline_status():
    """Statut du pipeline."""
    result = dict(_status["pipeline"])
    if result.get("last_report") and Path(result["last_report"]).exists():
        with open(result["last_report"], encoding='utf-8') as f:
            result["report"] = json.load(f)
    return result


# ── Score only ───────────────────────────────────────────────────────────────

@app.post("/pipeline/score")
async def pipeline_score(
    req: ScoreRequest,
    request: Request,
    db=Depends(get_db) if _DB_AVAILABLE else None,
):
    """Scoring seul (rapide, ~1s)."""
    from core.pipeline import Pipeline, NLPAnalyzer

    # Optional auth: if a valid cookie is present, we can overlay per-user fields (liked).
    user: str = ""
    try:
        token = request.cookies.get(AUTH_COOKIE_NAME) or ""
        if not token:
            auth = request.headers.get("authorization") or request.headers.get("Authorization") or ""
            if auth.lower().startswith("bearer "):
                token = auth.split(" ", 1)[1].strip()
        payload = _verify_token(token) if token else None
        if isinstance(payload, dict):
            user = str(payload.get("u") or "")
    except Exception:
        user = ""

    liked_ids: set[str] = set()
    likes: dict[str, dict] = {}
    if user:
        if _DB_AVAILABLE and db is not None:
            try:
                _migrate_likes_file_to_db(db, user_id=str(user))
                liked_ids = _get_liked_ids_db(db, user_id=str(user))
            except Exception:
                liked_ids = set()
        else:
            try:
                with _likes_lock:
                    likes = _load_likes()
            except Exception:
                likes = {}

    csv_path = req.csv_path
    if not csv_path:
        csv_found = _find_latest_csv()
        if not csv_found:
            raise HTTPException(404, "Aucun CSV trouvé")
        csv_path = str(csv_found)

    pipeline = Pipeline(output_dir="dossiers_generes", use_nlp=False, enrich_cps=False)
    pipeline.load_csv(csv_path)
    stats = pipeline.score_all()

    # Fast local fallback: build template-based descriptions if export index is missing/empty.
    desc_analyzer = NLPAnalyzer.__new__(NLPAnalyzer)
    desc_analyzer._nlp = None

    # Optional enrichment from last pipeline export (descriptions/requirements/budget/deadline).
    pipeline_results_index = _load_latest_pipeline_results_index()

    # Collect scored consultations summary
    relevant = []
    today = date.today()
    for c in pipeline.consultations:
        if c.priority.value != "EXCLUDED":
            key = c.reference or c.id
            extra = pipeline_results_index.get(key, {})
            description_technique = (extra.get("Description_Technique") or "").strip()
            description_fonctionnelle = (extra.get("Description_Fonctionnelle") or "").strip()
            requirements = _parse_pipeline_requirements(extra.get("Requirements"))
            deadline_iso = _parse_pipeline_deadline(extra.get("Deadline"))
            budget = _parse_pipeline_budget(extra.get("Budget_Estime"))

            if bool(getattr(req, "require_valid_deadline", True)):
                # Only keep opportunities with a valid, non-expired deadline.
                if (not deadline_iso) or _deadline_is_expired(deadline_iso, today=today):
                    continue

            if (not description_technique) and (not description_fonctionnelle) and (not requirements):
                try:
                    desc_analyzer.generate_descriptions(c)
                    description_technique = (c.description_technique or "").strip()
                    description_fonctionnelle = (c.description_fonctionnelle or "").strip()
                    requirements = list(c.requirements or [])
                except Exception:
                    pass

            relevant.append({
                "id": c.id,
                "reference": c.reference,
                "objet": c.objet[:100],
                "acheteur": c.acheteur,
                "priority": c.priority.value,
                "score": c.score_total,
                "domains": c.matched_domains,
                "keywords": c.matched_keywords[:5],
                "description_technique": description_technique,
                "description_fonctionnelle": description_fonctionnelle,
                "requirements": requirements,
                "deadline": deadline_iso,
                "budget": budget,
                "url": ((extra.get("URL_Offre") or c.url or "").strip()),
                "liked": (key in liked_ids) if liked_ids else (_is_liked(str(key), likes) if user else False),
            })

    return {
        "csv": csv_path,
        "stats": stats,
        "relevant_consultations": sorted(relevant, key=lambda x: -x["score"]),
    }


# ── Filter IT ────────────────────────────────────────────────────────────────

class FilterRequest(BaseModel):
    csv_path: Optional[str] = None

class GenerateRequest(BaseModel):
    csv_path: Optional[str] = None
    references: Optional[list[str]] = None  # generate dossiers only for these opportunity references/ids
    use_rag: bool = True
    convert_pdf: bool = True
    rate_limit: float = 6.0
    # Optimization / selection (safe defaults: generate for HOT/WARM + liked only)
    min_priority: str = "WARM"          # HOT | WARM | COLD
    include_liked: bool = True          # Always include liked items (even if below min_priority)
    only_active: bool = True            # Skip expired deadlines
    max_consultations: int = 120        # Hard cap to avoid crashes/long runs
    skip_existing: bool = True          # Don't regenerate if dossiers already exist

@app.post("/pipeline/filter-it")
async def pipeline_filter_it(req: FilterRequest):
    """Filtre le CSV pour ne garder que les consultations IT (AI/Data/BI/Dev/Cloud/Cyber)."""
    try:
        from scripts.filter_it import filter_and_export
    except Exception as e:
        # Do not crash n8n workflows on optional dependency issues.
        return {
            "csv_source": None,
            "csv_filtered": None,
            "excel": None,
            "total_brutes": 0,
            "total_it": 0,
            "par_domaine": {"AI": 0, "Data": 0, "BI": 0, "Dev": 0, "Cloud": 0, "Cybersecurity": 0},
            "message": f"Filter module unavailable: {e}",
        }

    csv_path = (req.csv_path or "").strip() if isinstance(req.csv_path, str) or req.csv_path is not None else ""
    if str(csv_path).strip().lower() in {"undefined", "null", "none"}:
        csv_path = ""
    if not csv_path:
        # Prefer the last scrape output when available (avoids "Aucun CSV trouvé" after cleanup).
        try:
            last_csv = str(_status.get("scraping", {}).get("last_csv") or "").strip()
        except Exception:
            last_csv = ""
        if last_csv and Path(last_csv).exists():
            csv_path = last_csv
        else:
            csv_found = _find_latest_csv()
            if not csv_found:
                # Don't fail the whole workflow: return an empty result so n8n can route to "0 IT".
                return {
                    "csv_source": None,
                    "csv_filtered": None,
                    "excel": None,
                    "total_brutes": 0,
                    "total_it": 0,
                    "par_domaine": {"AI": 0, "Data": 0, "BI": 0, "Dev": 0, "Cloud": 0, "Cybersecurity": 0},
                    "message": "Aucun CSV trouvé (lancer /scrape avant /pipeline/filter-it).",
                }
            csv_path = str(csv_found)

    # If caller provided a csv_path but it doesn't exist, return empty result (avoid 500).
    try:
        if not Path(str(csv_path)).exists():
            return {
                "csv_source": str(csv_path),
                "csv_filtered": None,
                "excel": None,
                "total_brutes": 0,
                "total_it": 0,
                "par_domaine": {"AI": 0, "Data": 0, "BI": 0, "Dev": 0, "Cloud": 0, "Cybersecurity": 0},
                "message": f"CSV introuvable: {csv_path}",
            }
    except Exception:
        pass

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, filter_and_export, str(csv_path))
    except FileNotFoundError:
        return {
            "csv_source": str(csv_path),
            "csv_filtered": None,
            "excel": None,
            "total_brutes": 0,
            "total_it": 0,
            "par_domaine": {"AI": 0, "Data": 0, "BI": 0, "Dev": 0, "Cloud": 0, "Cybersecurity": 0},
            "message": f"CSV introuvable: {csv_path}",
        }
    except Exception as e:
        # Any other failure (including optional Excel export) should not break n8n.
        return {
            "csv_source": str(csv_path),
            "csv_filtered": None,
            "excel": None,
            "total_brutes": 0,
            "total_it": 0,
            "par_domaine": {"AI": 0, "Data": 0, "BI": 0, "Dev": 0, "Cloud": 0, "Cybersecurity": 0},
            "message": f"Erreur filtre IT: {e}",
        }
    if not result:
        # Same philosophy: return an empty result instead of crashing n8n pipeline.
        return {
            "csv_source": csv_path,
            "csv_filtered": None,
            "excel": None,
            "total_brutes": 0,
            "total_it": 0,
            "par_domaine": {"AI": 0, "Data": 0, "BI": 0, "Dev": 0, "Cloud": 0, "Cybersecurity": 0},
            "message": "Échec du filtrage IT (fichier introuvable ou illisible).",
        }
    return result


# ── Dossier generation (hybrid RAG + Pipeline) ─────────────────────────────

@app.post("/pipeline/generate-dossiers")
async def pipeline_generate_dossiers(req: GenerateRequest, request: Request):
    """Génère les dossiers DOCX+PDF hybrides (RAG Groq + templates)."""
    user = None
    try:
        user = require_auth(request)
    except Exception:
        user = None
    from scripts.generate_dossiers_hybrid import generate_dossiers_hybrid

    def _run_sync() -> dict:
        csv_path = req.csv_path
        # If caller provides a raw scrape CSV, prefer latest pipeline_results to keep "qualified only" behavior.
        if csv_path:
            try:
                p = Path(csv_path)
                if p.exists():
                    with open(p, "r", encoding="utf-8-sig") as f:
                        header = f.readline()
                    # pipeline_results has Priorite; legacy IT export has domaines_it.
                    if ("Priorite" not in header) and ("domaines_it" not in header):
                        csv_found = _find_latest("pipeline_results_*.csv")
                        if csv_found:
                            csv_path = str(csv_found)
            except Exception:
                pass
        if not csv_path:
            csv_found = _find_latest("pipeline_results_*.csv")
            if not csv_found:
                csv_found = _find_latest("appels_offres_*_IT.csv")
            if not csv_found:
                csv_found = _find_latest_csv()
            if not csv_found:
                raise HTTPException(404, "Aucun CSV trouve")
            csv_path = str(csv_found)

        liked_ids: list[str] = []
        if user and _DB_AVAILABLE:
            try:
                from app.database import SessionLocal
                session = SessionLocal()
                try:
                    liked_ids = sorted(_get_liked_ids_db(session, user_id=str(user)))
                finally:
                    session.close()
            except Exception:
                liked_ids = []

        _status["dossiers"]["running"] = True
        _status["dossiers"]["error"] = None
        try:
            result = generate_dossiers_hybrid(
                csv_path=csv_path,
                use_rag=req.use_rag,
                convert_pdf=req.convert_pdf,
                rate_limit=req.rate_limit,
                only_references=req.references,
                min_priority=req.min_priority,
                include_liked=req.include_liked,
                liked_ids=liked_ids,
                only_active=req.only_active,
                max_consultations=req.max_consultations,
                skip_existing=req.skip_existing,
            )
            _status["dossiers"]["last_result"] = result
            _status["dossiers"]["last_run"] = datetime.now().isoformat()
            return result
        finally:
            _status["dossiers"]["running"] = False

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _run_sync)
    if not result:
        raise HTTPException(500, "Échec de la génération")
    if user:
        try:
            _append_activity({
                "user": user,
                "type": "generated_document",
                "message": "Generated dossiers",
                "created_at": datetime.now().isoformat(),
            })
        except Exception:
            pass

    # Notification (best-effort)
    if _DB_AVAILABLE:
        try:
            from app.database import SessionLocal

            session = SessionLocal()
            try:
                target_users = [user] if user else _list_known_users()
                for u in target_users:
                    prof = "GLOBAL"
                    prof = str((_get_user_profile(str(u)).get("profile") or "GLOBAL")).strip().upper()
                    if prof == "CYBER":
                        prof = "CYBERSECURITY"
                    if prof not in {"GLOBAL", "AI", "DATA", "CLOUD", "DEV", "CYBERSECURITY"}:
                        prof = "GLOBAL"
                    _create_notification(
                        session,
                        user_id=u,
                        message="Dossier generation completed.",
                        ntype="dossier_generation_completed",
                        opportunity_id=None,
                        profile=prof,
                    )
                session.commit()
            finally:
                session.close()
        except Exception:
            pass
    return result


@app.post("/pipeline/generate-dossiers-async")
async def pipeline_generate_dossiers_async(req: GenerateRequest, request: Request, background_tasks: BackgroundTasks):
    """Démarre la génération des dossiers en arrière-plan (réponse immédiate pour n8n)."""
    if _status["dossiers"]["running"]:
        raise HTTPException(409, "Dossier generation already running")

    user = None
    try:
        user = require_auth(request)
    except Exception:
        user = None

    # Run generation in a worker thread without blocking the n8n workflow.
    def _bg():
        # Reuse the same sync logic as the blocking endpoint.
        from scripts.generate_dossiers_hybrid import generate_dossiers_hybrid

        csv_path = req.csv_path
        if csv_path:
            try:
                p = Path(csv_path)
                if p.exists():
                    with open(p, "r", encoding="utf-8-sig") as f:
                        header = f.readline()
                    if ("Priorite" not in header) and ("domaines_it" not in header):
                        csv_found = _find_latest("pipeline_results_*.csv")
                        if csv_found:
                            csv_path = str(csv_found)
            except Exception:
                pass
        if not csv_path:
            csv_found = _find_latest("pipeline_results_*.csv") or _find_latest("appels_offres_*_IT.csv") or _find_latest_csv()
            if not csv_found:
                raise FileNotFoundError("Aucun CSV trouve")
            csv_path = str(csv_found)

        liked_ids: list[str] = []
        if user and _DB_AVAILABLE:
            try:
                from app.database import SessionLocal
                session = SessionLocal()
                try:
                    liked_ids = sorted(_get_liked_ids_db(session, user_id=str(user)))
                finally:
                    session.close()
            except Exception:
                liked_ids = []

        _status["dossiers"]["running"] = True
        _status["dossiers"]["error"] = None
        try:
            result = generate_dossiers_hybrid(
                csv_path=csv_path,
                use_rag=req.use_rag,
                convert_pdf=req.convert_pdf,
                rate_limit=req.rate_limit,
                only_references=req.references,
                min_priority=req.min_priority,
                include_liked=req.include_liked,
                liked_ids=liked_ids,
                only_active=req.only_active,
                max_consultations=req.max_consultations,
                skip_existing=req.skip_existing,
            )
            _status["dossiers"]["last_result"] = result
            _status["dossiers"]["last_run"] = datetime.now().isoformat()
        except Exception as e:
            _status["dossiers"]["error"] = str(e)
            logger.exception("Dossier generation failed (async)")
        finally:
            _status["dossiers"]["running"] = False

    background_tasks.add_task(asyncio.to_thread, _bg)
    return {"status": "started"}


@app.get("/pipeline/dossiers/status")
async def pipeline_dossiers_status():
    """Statut de la génération de dossiers."""
    return dict(_status["dossiers"])


# ── RAG enrichment ──────────────────────────────────────────────────────────

@app.post("/pipeline/rag")
async def pipeline_rag(req: RAGRequest):
    """Lance l'enrichissement RAG (LLM)."""
    def _run():
        from generate_dossiers_rag import main as rag_main
        # This runs the full RAG enrichment
        rag_main()
        return {"status": "completed"}

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _run)
    return result


# ── Results ──────────────────────────────────────────────────────────────────

@app.get("/results/latest")
async def results_latest():
    """Retourne le dernier rapport pipeline."""
    report = _find_latest("pipeline_report_*.json")
    if not report:
        # Try pipeline_results
        report = _find_latest("pipeline_results_*.csv")
    if not report:
        raise HTTPException(404, "Aucun rapport trouvé")

    if report.suffix == '.json':
        with open(report, encoding='utf-8') as f:
            return json.load(f)
    else:
        return {"file": str(report)}


@app.on_event("startup")
def _startup_db():
    # Auth bootstrap does not depend on SQLAlchemy.
    try:
        _ensure_default_profile_users()
    except Exception:
        pass

    # Defensive reset: if the process previously crashed during scraping, don't stay stuck in running=true.
    try:
        if isinstance(_status.get("scraping"), dict):
            _status["scraping"]["running"] = False
            _status["scraping"]["started_at"] = None
            # Keep last_run/last_csv for observability, but clear transient error.
            if _status["scraping"].get("error"):
                _status["scraping"]["error"] = None
    except Exception:
        pass

    if not _DB_AVAILABLE:
        return
    try:
        ensure_db_schema()

        # Auto-sync on startup (can be disabled with DB_AUTO_SYNC=0).
        if os.environ.get("DB_AUTO_SYNC", "1").strip() != "0":
            from app.database import SessionLocal

            session = SessionLocal()
            try:
                # Only sync if DB is empty and an export exists.
                if session.query(Opportunity).count() == 0 and _find_latest("pipeline_results_*.csv"):
                    _sync_db_from_pipeline_results(session)
                # Migrate legacy likes.json into DB (best-effort).
                if AUTH_USERNAME:
                    _migrate_likes_file_to_db(session, user_id=str(AUTH_USERNAME))
            finally:
                session.close()
    except Exception as e:
        logger.warning(f"DB schema ensure failed: {e}")


@app.get("/results/report")
async def results_report(user=Depends(require_auth)):
    """Télécharge le dernier rapport pipeline (JSON) en tant que fichier."""
    report = _find_latest("pipeline_report_*.json")
    if not report:
        raise HTTPException(404, "Aucun rapport trouvÃ©")
    return FileResponse(
        path=str(report),
        filename=report.name,
        media_type="application/json",
    )


@app.get("/results/csv")
async def results_csv(user=Depends(require_auth)):
    """Télécharge le dernier CSV de résultats."""
    csv_path = _find_latest_csv()
    if not csv_path:
        raise HTTPException(404, "Aucun CSV trouvé")
    return FileResponse(
        path=str(csv_path),
        filename=csv_path.name,
        media_type="text/csv",
    )


@app.get("/results/excel")
async def results_excel(user=Depends(require_auth)):
    """Télécharge le dernier fichier Excel (filtré IT)."""
    xlsx = _find_latest("consultations_IT.xlsx") or _find_latest("consultations_completes.xlsx") or _find_latest("*.xlsx")
    if not xlsx:
        raise HTTPException(404, "Aucun Excel trouvé")
    return FileResponse(
        path=str(xlsx),
        filename=xlsx.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/results/opportunities")
async def results_opportunities(
    include_excluded: bool = False,
    include_expired: bool = False,
    user=Depends(require_auth),
    db=Depends(get_db) if _DB_AVAILABLE else None,
):
    """
    Retourne les opportunités depuis la base (si dispo) ou le dernier export `pipeline_results_*.csv`.

    Les opportunités présentes dans `dossiers_generes/` avec deadline non expirée mais absentes de la base
    sont ajoutées à partir du CSV pipeline, pour aligner le Dashboard avec la page Reports.
    """
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
            
            raw_scrape_index = _load_latest_raw_scrape_index()

            out_items = []
            today = date.today()
            for o in opps_db:
                oid = o.ref or str(getattr(o, "id", ""))
                if not include_expired:
                    dl = getattr(o, "deadline", None)
                    # Some DBs/schemas store deadline as datetime; normalize to date.
                    if isinstance(dl, datetime):
                        dl = dl.date()
                    if not dl:
                        continue
                    if dl and dl < today:
                        continue
                try:
                    domains = json.loads(getattr(o, "domains", "[]")) if getattr(o, "domains", None) else []
                except:
                    domains = [d.strip() for d in (str(getattr(o, "domains", "")) or "").split("/") if d.strip()]
                    
                reqs = [r.strip() for r in (str(getattr(o, "requirements", "")) or "").split('|') if r.strip()]
                similarity_score = getattr(o, "score", 0.0) / 20.0  # approximate, we'd rather use _compute_similarity_score
                similarity_score = _compute_similarity_score(priority=getattr(o, "level", ""), score=int(getattr(o, "score", 0.0) or 0))

                buyer_raw = str(getattr(o, "buyer", "") or "").strip()
                buyer_norm = _normalize_buyer_label(buyer_raw)
                if buyer_norm.lower() in {"", "non identifie", "non identifié", "-", "n/a"}:
                    raw = raw_scrape_index.get(str(oid)) or {}
                    cand = _normalize_buyer_label(str(raw.get("acheteur") or "").strip())
                    if not cand:
                        cand = _normalize_buyer_label(_infer_buyer_from_objet(str(raw.get("objet") or "")))
                    if not cand:
                        cand = _normalize_buyer_label(_infer_buyer_from_title(str(getattr(o, "title", "") or "")))
                    buyer_norm = cand or buyer_norm

                objet = str((raw_scrape_index.get(str(oid)) or {}).get("objet") or "").strip()
                
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
                    "buyer": buyer_norm,
                    "organization": buyer_norm,
                    "objet": objet,
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

            with _likes_lock:
                likes_merge = _load_likes()
            out_items = _merge_opportunities_with_active_dossier_folders(
                out_items, include_excluded, include_expired, likes_merge
            )

            return {
                "source": "PostgreSQL Database",
                "count": len(out_items),
                "opportunities": out_items,
            }
        except Exception as e:
            logger.warning(f"Fallback to CSV due to DB error: {e}")

    latest = _find_latest("pipeline_results_*.csv")
    rows = _load_latest_pipeline_results_rows()
    if not rows:
        raise HTTPException(404, "Aucun pipeline_results_*.csv trouvé")

    try:
        latest_path = str(latest) if latest else ""
        latest_mtime = float(latest.stat().st_mtime) if latest else 0.0
    except Exception:
        latest_path = str(latest) if latest else ""
        latest_mtime = 0.0

    liked_ids: set[str] = set()
    likes: dict[str, dict] = {}
    # Always read likes from file store for UI stability.
    with _likes_lock:
        likes = _load_likes()

    cache_key = (latest_path, latest_mtime, bool(include_excluded))
    with _cache_lock:
        base_items = _opps_base_cache.get(cache_key)

    if base_items is None:
        raw_scrape_index = _load_latest_raw_scrape_index()
        computed: list[dict] = []
        for row in rows:
            priority = (row.get("Priorite") or "").strip()
            if (not include_excluded) and priority.upper() == "EXCLUDED":
                continue
            rec = _opportunity_dict_from_pipeline_row(row, raw_scrape_index)
            if rec:
                computed.append(rec)

        base_items = computed
        with _cache_lock:
            _opps_base_cache[cache_key] = base_items

    # Overlay per-user like state on top of cached base items.
    out_items: list[dict] = []
    today = date.today()
    for o in base_items:
        oid = str(o.get("id") or "").strip()
        if not include_expired:
            if not o.get("deadline"):
                continue
        if (not include_expired) and _deadline_is_expired(o.get("deadline"), today=today):
            continue
        liked = _is_liked(oid, likes)
        out_items.append({
            **o,
            "liked": liked,
            "rag_status": _compute_rag_status(
                priority=str(o.get("priority") or ""),
                score=int(o.get("score") or 0),
                similarity_score=float(o.get("similarity_score") or 0.0),
                deadline_iso=o.get("deadline"),
                liked=bool(liked),
                existing=o.get("rag_status"),
            ),
        })

    out_items = _merge_opportunities_with_active_dossier_folders(
        out_items, include_excluded, include_expired, likes
    )

    return {
        "source": latest_path or str(_find_latest("pipeline_results_*.csv")),
        "count": len(out_items),
        "opportunities": out_items,
    }


@app.get("/opportunities")
async def opportunities_by_profile(
    profile: str = "GLOBAL",
    include_excluded: bool = False,
    user=Depends(require_auth),
    db=Depends(get_db) if _DB_AVAILABLE else None,
):
    """
    Profile-based filtered opportunities.
    profile: GLOBAL | AI | DATA | CLOUD | DEV | CYBER | CYBERSECURITY
    """
    current = await results_opportunities(include_excluded=include_excluded, user=user, db=db)
    items = current.get("opportunities") or []

    p = (profile or "GLOBAL").strip().upper()
    if p in {"GLOBAL", "ALL"}:
        return {**current, "profile": "GLOBAL"}
    if p == "CYBER":
        p = "CYBERSECURITY"

    filtered = []
    for o in items:
        if not isinstance(o, dict):
            continue
        doms = o.get("domains") or o.get("domain") or []
        if isinstance(doms, str):
            doms = [d.strip().upper() for d in doms.split("/") if d.strip()]
        if any(str(d).strip().upper() == p for d in (doms or [])):
            filtered.append(o)

    return {
        "source": current.get("source"),
        "profile": p,
        "count": len(filtered),
        "opportunities": filtered,
    }


@app.post("/like/{opportunity_id:path}")
async def like_opportunity(
    opportunity_id: str,
    req: LikeRequest = Body(default=LikeRequest()),
    user=Depends(require_auth),
    db=Depends(get_db) if _DB_AVAILABLE else None,
):
    """
    Toggle or set the "liked" state for an opportunity.

    Body (optional): {"liked": true|false}
    If omitted, the state is toggled.
    """
    # NOTE: Likes are persisted in a simple file store to avoid intermittent DB/locking issues
    # on Windows/SQLite. This keeps the "like" UX reliable.
    oid = (opportunity_id or "").strip()
    if not oid:
        raise HTTPException(400, "Invalid id")

    with _likes_lock:
        likes = _load_likes()
        current = _is_liked(oid, likes)
        new_state = (not current) if req.liked is None else bool(req.liked)
        likes[oid] = {"liked": new_state, "updated_at": datetime.now().isoformat()}
        _save_likes(likes)

    try:
        _append_activity({
            "user": user,
            "type": "liked_opportunity" if new_state else "unliked_opportunity",
            "opportunity_id": oid,
            "created_at": datetime.now().isoformat(),
        })
    except Exception:
        pass

    return {"id": oid, "liked": new_state}


@app.get("/liked")
async def liked_opportunities(user=Depends(require_auth), db=Depends(get_db) if _DB_AVAILABLE else None):
    """Return liked opportunities (enriched with latest /results/opportunities data when available)."""
    liked_ids: list[str] = []
    with _likes_lock:
        likes = _load_likes()
    liked_ids = [k for k, v in likes.items() if isinstance(v, dict) and v.get("liked")]

    current = await results_opportunities(include_excluded=True, user=user, db=db)
    by_id = {o.get("id"): o for o in (current.get("opportunities") or [])}
    items = [by_id.get(i, {"id": i, "reference": i, "liked": True}) for i in liked_ids]
    return {"count": len(items), "opportunities": items}


@app.get("/recommended")
async def recommended_opportunities(threshold: float = 0.75, user=Depends(require_auth), db=Depends(get_db) if _DB_AVAILABLE else None):
    """Return opportunities with similarity_score above threshold."""
    current = await results_opportunities(include_excluded=False, user=user, db=db)
    opps = current.get("opportunities") or []
    items = [o for o in opps if float(o.get("similarity_score") or 0.0) > float(threshold)]
    return {"threshold": threshold, "count": len(items), "opportunities": items}


@app.get("/results/dossiers")
async def results_dossiers(user=Depends(require_auth)):
    """Liste les dossiers DOCX et PDF générés (recherche récursive)."""
    dossiers_dir = PROJECT_ROOT / "dossiers_generes"
    if not dossiers_dir.exists():
        return {"dossiers": [], "count": 0, "count_pdf": 0}

    docx_files = sorted(dossiers_dir.rglob("*.docx"), key=lambda f: f.stat().st_mtime, reverse=True)
    pdf_files = sorted(dossiers_dir.rglob("*.pdf"), key=lambda f: f.stat().st_mtime, reverse=True)

    def _info(f: Path) -> dict:
        return {
            "name": f.name,
            "path": str(f.relative_to(dossiers_dir)),
            "size_kb": round(f.stat().st_size / 1024, 1),
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        }

    return {
        "count": len(docx_files),
        "count_pdf": len(pdf_files),
        "dossiers": [_info(f) for f in docx_files[:100]],
        "pdf": [_info(f) for f in pdf_files[:100]],
    }


@app.get("/results/dossiers/index")
async def results_dossiers_index(
    user=Depends(require_auth),
    profile: Optional[str] = Query(None, description="Optional domain/profile filter (AI/DATA/CLOUD/DEV/CYBERSECURITY/GLOBAL)"),
):
    """
    Index des dossiers générés par opportunité, pour l'affichage "Reports" du Dashboard.

    Retourne: titre (si disponible via pipeline_results), types de documents, date de génération (mtime), liens de téléchargement.
    """
    dossiers_root = PROJECT_ROOT / "dossiers_generes"
    if not dossiers_root.exists():
        return {"count": 0, "items": []}

    titles = _load_latest_pipeline_titles_index()
    deadlines = _load_latest_pipeline_deadlines_index()
    svc = _load_latest_pipeline_service_domains_index()
    titles_by_folder: dict[str, str] = {}
    deadlines_by_folder: dict[str, Optional[str]] = {}
    service_by_folder: dict[str, str] = {}
    domains_by_folder: dict[str, list[str]] = {}
    ids_by_folder: dict[str, str] = {}
    for opportunity_id, title in titles.items():
        folder_name = _consultation_folder_name(opportunity_id)
        titles_by_folder.setdefault(folder_name, title)
        ids_by_folder.setdefault(folder_name, opportunity_id)

    for opportunity_id, dl in deadlines.items():
        folder_name = _consultation_folder_name(opportunity_id)
        deadlines_by_folder.setdefault(folder_name, dl)
        ids_by_folder.setdefault(folder_name, opportunity_id)

    for opportunity_id, sd in svc.items():
        folder_name = _consultation_folder_name(opportunity_id)
        if isinstance(sd, dict):
            service_by_folder.setdefault(folder_name, str(sd.get("service") or ""))
            doms = sd.get("domains") or []
            if isinstance(doms, list):
                domains_by_folder.setdefault(folder_name, [str(d).upper() for d in doms if d])
        ids_by_folder.setdefault(folder_name, opportunity_id)

    # Apply profile filter (profile is selected at login). Allow override via query for admin/debug.
    effective_profile = (profile or (_get_user_profile(str(user)).get("profile") or "")).strip().upper()
    if effective_profile == "CYBER":
        effective_profile = "CYBERSECURITY"
    if effective_profile and effective_profile not in {"GLOBAL", "ALL"}:
        # Normalize to the supported profile set
        if effective_profile not in {"AI", "DATA", "CLOUD", "DEV", "CYBERSECURITY"}:
            effective_profile = "GLOBAL"

    items = []
    removed_expired = 0
    removed_unknown_deadline = 0
    today = datetime.now().date()
    for folder in sorted([d for d in dossiers_root.iterdir() if d.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True):
        # Prune dossiers where the opportunity deadline is already past (keeps Reports clean).
        dl = deadlines_by_folder.get(folder.name) or _load_dossier_deadline_from_analysis(folder)
        if dl:
            try:
                dl_date = datetime.fromisoformat(dl).date()
            except ValueError:
                dl_date = None
        else:
            dl_date = None

        # If we can't determine the deadline, don't show the dossier in Reports.
        # This avoids keeping "old" dossiers that can't be validated as active.
        if dl_date is None:
            removed_unknown_deadline += 1
            continue

        if dl_date < today:
            try:
                shutil.rmtree(folder)
                removed_expired += 1
            except Exception as e:
                logging.warning("Failed to remove expired dossiers folder '%s': %s", str(folder), e)
            continue

        selected = _pick_latest_dossiers(list(folder.iterdir()))
        if not selected:
            continue

        latest_mtime = max(f.stat().st_mtime for f in selected)

        files = []
        for f in selected:
            name_lower = f.name.lower()
            kind = "technique" if "technique" in name_lower else "administratif"
            mtime = f.stat().st_mtime
            files.append({
                "name": f.name,
                "ext": f.suffix.lower().lstrip("."),
                "kind": kind,
                "modified": datetime.fromtimestamp(mtime).isoformat(),
                "url": f"/download/dossier/{folder.name}/{f.name}",
            })

        # Try to recover the original ID from folder name (best effort).
        # Folder naming comes from core/pipeline.py ref_clean; we keep folder as primary identifier.
        title = titles_by_folder.get(folder.name, "")
        deadline_iso = deadlines_by_folder.get(folder.name) or dl

        item = {
            "folder": folder.name,
            "opportunity_id": ids_by_folder.get(folder.name, ""),
            "title": title,
            "service": service_by_folder.get(folder.name, ""),
            "domains": domains_by_folder.get(folder.name, []),
            "deadline": deadline_iso,
            "generated_at": datetime.fromtimestamp(latest_mtime).isoformat() if latest_mtime else None,
            "documents": sorted(
                files,
                key=lambda x: (
                    0 if x["kind"] == "technique" else 1,
                    0 if x["ext"] == "docx" else 1,
                    x["name"],
                ),
            ),
        }

        if effective_profile and effective_profile not in {"GLOBAL", "ALL"}:
            doms = [str(d).upper() for d in (item.get("domains") or []) if d]
            svc_str = str(item.get("service") or "").upper()
            match = (effective_profile in doms) or (effective_profile == "CYBERSECURITY" and "CYBER" in svc_str) or (effective_profile in svc_str)
            if not match:
                continue

        items.append(item)

    return {
        "count": len(items),
        "items": items,
        "removed_expired": removed_expired,
        "removed_unknown_deadline": removed_unknown_deadline,
        "profile": effective_profile or "GLOBAL",
    }


@app.get("/results/dossiers/{consultation_id:path}")
async def get_consultation_dossiers(consultation_id: str, user=Depends(require_auth)):
    """Retourne la liste des dossiers générés pour une consultation."""
    # Keep folder naming aligned with `core/pipeline.py` (sanitization + truncation).
    folder = _consultation_folder_name(consultation_id)
    dossiers_dir = PROJECT_ROOT / "dossiers_generes" / folder

    # Backward-compat fallback for older folder naming (only invalid path chars replaced).
    if not dossiers_dir.exists() or not dossiers_dir.is_dir():
        legacy_folder = re.sub(r'[\\/*?:"<>|]', '_', consultation_id)
        legacy_dir = PROJECT_ROOT / "dossiers_generes" / legacy_folder
        if legacy_dir.exists() and legacy_dir.is_dir():
            folder = legacy_folder
            dossiers_dir = legacy_dir
        else:
            return {"files": []}
        
    selected = _pick_latest_dossiers(list(dossiers_dir.iterdir()))

    files = []
    for f in selected:
        files.append({
            "name": f.name,
            "type": f.suffix.lower().strip('.'),
            "url": f"/download/dossier/{folder}/{f.name}"
        })
            
    # Keep technical dossiers first, then administratif.
    files.sort(key=lambda x: (not ('technique' in x['name'].lower()), x['type'], x['name']))
    return {"files": files}


@app.get("/download/dossier/{folder}/{filename:path}")
async def download_dossier(folder: str, filename: str, user=Depends(require_auth)):
    """Télécharge un fichier spécifique."""
    file_path = PROJECT_ROOT / "dossiers_generes" / folder / filename
    
    # Security check: ensure the file is strictly inside dossiers_generes
    try:
        if not file_path.resolve().is_relative_to((PROJECT_ROOT / "dossiers_generes").resolve()):
            raise HTTPException(403, "Accès refusé")
    except AttributeError:
        # Fallback for Python < 3.9 if resolving fails
        pass

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(404, "Fichier introuvable")
        
    media_types = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    }
    mtype = media_types.get(file_path.suffix.lower(), "application/octet-stream")
        
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type=mtype
    )


# ── Health ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check pour n8n / monitoring."""
    csv_found = _find_latest_csv()
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "scraping": _status["scraping"],
        "pipeline": _status["pipeline"],
        "latest_csv": str(csv_found) if csv_found else None,
        "latest_csv_rows": _count_csv_rows(csv_found) if csv_found else 0,
    }


@app.get("/db/status")
async def db_status(db=Depends(get_db) if _DB_AVAILABLE else None, user=Depends(require_auth)):
    if not _DB_AVAILABLE:
        return {"enabled": False}
    from app.database import DB_PATH

    total = db.query(Opportunity).count()
    latest_export = _find_latest("pipeline_results_*.csv")
    export_rows = 0
    if latest_export and latest_export.exists():
        try:
            export_rows = _count_csv_rows(latest_export)
        except Exception:
            export_rows = 0

    return {
        "enabled": True,
        "db_path": str(Path(DB_PATH).resolve()),
        "total_opportunities": total,
        "latest_pipeline_results": str(latest_export) if latest_export else None,
        "latest_pipeline_results_rows": export_rows,
    }


@app.post("/db/sync-latest")
async def db_sync_latest(db=Depends(get_db) if _DB_AVAILABLE else None, user=Depends(require_auth)):
    if not _DB_AVAILABLE:
        raise HTTPException(501, "DB not available (SQLAlchemy missing)")
    return _sync_db_from_pipeline_results(db)


# ── Startup ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        # Bind on IPv6 so localhost (::1) works on Windows (dual-stack)
        host="::",
        port=int(os.environ.get("PORT", "8001")),
        reload=True,
        log_level="info",
    )
