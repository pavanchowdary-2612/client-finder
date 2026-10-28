import json
import sqlite3
import time
from pathlib import Path

# Resolve data/ directory at project root
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DB_PATH = DATA_DIR / "leads.db"


def _connect():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            website TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            location TEXT,
            category TEXT,
            evidence TEXT,
            research_notes TEXT,
            source_url TEXT,
            contact_email TEXT,
            contact_phone TEXT,
            phone_source TEXT,
            other_emails TEXT,
            email_source TEXT,
            contact_page TEXT,
            fit_score INTEGER DEFAULT 0,
            fit_reasons TEXT DEFAULT '[]',
            sources TEXT DEFAULT '[]',
            draft_subject TEXT DEFAULT '',
            draft TEXT,
            draft_type TEXT,
            found_at TEXT,
            status TEXT DEFAULT 'Needs review',
            opted_out INTEGER DEFAULT 0,
            notes TEXT DEFAULT ''
        )""")
        existing = {row[1] for row in db.execute("PRAGMA table_info(leads)")}
        additions = {
            "research_notes": "TEXT DEFAULT ''", "email_source": "TEXT DEFAULT ''",
            "contact_phone": "TEXT DEFAULT ''", "phone_source": "TEXT DEFAULT ''",
            "draft_subject": "TEXT DEFAULT ''",
            "fit_reasons": "TEXT DEFAULT '[]'", "sources": "TEXT DEFAULT '[]'",
            "draft_type": "TEXT DEFAULT ''", "opted_out": "INTEGER DEFAULT 0", "notes": "TEXT DEFAULT ''",
        }
        for name, sql_type in additions.items():
            if name not in existing:
                db.execute(f"ALTER TABLE leads ADD COLUMN {name} {sql_type}")
        db.execute("""CREATE TABLE IF NOT EXISTS suppression (
            email TEXT PRIMARY KEY COLLATE NOCASE,
            reason TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS chat_intent_cache (
            cache_key TEXT PRIMARY KEY,
            response_json TEXT NOT NULL,
            expires_at REAL NOT NULL
        )""")


def get_cached_chat_intent(cache_key: str):
    """Return a non-expired interpreted intent brief, if one is cached."""
    with _connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS chat_intent_cache (
            cache_key TEXT PRIMARY KEY,
            response_json TEXT NOT NULL,
            expires_at REAL NOT NULL
        )""")
        row = db.execute(
            "SELECT response_json, expires_at FROM chat_intent_cache WHERE cache_key=?",
            (cache_key,),
        ).fetchone()
        if not row:
            return None
        if row["expires_at"] <= time.time():
            db.execute("DELETE FROM chat_intent_cache WHERE cache_key=?", (cache_key,))
            return None
        try:
            return json.loads(row["response_json"])
        except json.JSONDecodeError:
            db.execute("DELETE FROM chat_intent_cache WHERE cache_key=?", (cache_key,))
            return None


def cache_chat_intent(cache_key: str, response: dict, ttl_seconds: int = 30 * 24 * 60 * 60):
    """Persist an intent result locally for 30 days by default."""
    with _connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS chat_intent_cache (
            cache_key TEXT PRIMARY KEY,
            response_json TEXT NOT NULL,
            expires_at REAL NOT NULL
        )""")
        db.execute(
            "INSERT INTO chat_intent_cache(cache_key, response_json, expires_at) VALUES (?, ?, ?) "
            "ON CONFLICT(cache_key) DO UPDATE SET response_json=excluded.response_json, expires_at=excluded.expires_at",
            (cache_key, json.dumps(response, ensure_ascii=False), time.time() + ttl_seconds),
        )
        db.execute("DELETE FROM chat_intent_cache WHERE expires_at <= ?", (time.time(),))


def _decode(row):
    item = dict(row)
    for field in ("fit_reasons", "sources"):
        try:
            item[field] = json.loads(item.get(field) or "[]")
        except json.JSONDecodeError:
            item[field] = []
    item["opted_out"] = bool(item.get("opted_out", False))
    return item


def save_leads(leads):
    fields = (
        "website", "name", "location", "category", "evidence", "research_notes",
        "source_url", "contact_email", "contact_phone", "phone_source", "other_emails", "email_source", "contact_page",
        "fit_score", "fit_reasons", "sources", "draft_subject", "draft", "draft_type", "found_at", "status",
    )
    with _connect() as db:
        for lead in leads:
            values = [json.dumps(lead.get(field, [])) if field in {"fit_reasons", "sources"} else lead.get(field, "") for field in fields]
            db.execute(
                f"INSERT INTO leads ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)}) "
                "ON CONFLICT(website) DO UPDATE SET " + ",".join(f"{field}=excluded.{field}" for field in fields[1:]), values,
            )


def list_leads():
    with _connect() as db:
        return [_decode(row) for row in db.execute("SELECT * FROM leads ORDER BY fit_score DESC, id DESC")]


def get_lead(lead_id: int):
    with _connect() as db:
        row = db.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        return _decode(row) if row else None


def update_lead(lead_id: int, **fields):
    allowed = {"name", "contact_email", "contact_phone", "draft_subject", "draft", "status", "notes", "opted_out"}
    payload = {key: value for key, value in fields.items() if key in allowed}
    if not payload:
        return
    clause = ", ".join(f"{key}=?" for key in payload)
    with _connect() as db:
        db.execute(f"UPDATE leads SET {clause} WHERE id=?", (*payload.values(), lead_id))


def add_suppression(email: str, reason: str = ""):
    email = email.strip().lower()
    if not email or "@" not in email:
        return
    with _connect() as db:
        db.execute("INSERT INTO suppression(email, reason) VALUES (?, ?) ON CONFLICT(email) DO UPDATE SET reason=excluded.reason", (email, reason))
        db.execute("UPDATE leads SET opted_out=1, status='Suppressed' WHERE lower(contact_email)=lower(?)", (email,))


def list_suppressed():
    with _connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM suppression ORDER BY created_at DESC")]


def is_suppressed(email: str) -> bool:
    with _connect() as db:
        return db.execute("SELECT 1 FROM suppression WHERE email=? COLLATE NOCASE", (email.strip(),)).fetchone() is not None


def delete_leads():
    with _connect() as db:
        db.execute("DELETE FROM leads")
