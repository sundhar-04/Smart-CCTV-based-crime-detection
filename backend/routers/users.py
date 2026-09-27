from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import time
import uuid
import json
from backend.database import get_db

router = APIRouter(prefix="/api/users", tags=["users"])


class UserCreate(BaseModel):
    username: str
    display_name: str
    role: str = "Operator"
    email: Optional[str] = ""


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None
    active: Optional[bool] = None


def _ensure_users_table():
    """Create users table if not exists."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT DEFAULT 'Operator',
            email TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    # Seed default admin if empty
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        default_users = [
            ("USR-ADMIN", "admin", "System Administrator", "Admin", "admin@meridian.local", 1, now, now),
            ("USR-OP1", "operator1", "Primary Operator", "Operator", "op1@meridian.local", 1, now, now),
            ("USR-AUD1", "auditor1", "Compliance Auditor", "Auditor", "auditor@meridian.local", 1, now, now),
        ]
        cursor.executemany(
            "INSERT INTO users (id, username, display_name, role, email, active, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            default_users
        )
    conn.commit()
    conn.close()


_ensure_users_table()


@router.get("")
def list_users():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users ORDER BY created_at")
    users = [dict(r) for r in cursor.fetchall()]
    conn.close()
    for u in users:
        u["active"] = bool(u.get("active", 1))
    return users


@router.get("/{user_id}")
def get_user(user_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    r = cursor.fetchone()
    conn.close()
    if not r:
        raise HTTPException(status_code=404, detail="User not found")
    u = dict(r)
    u["active"] = bool(u.get("active", 1))
    return u


@router.post("")
def create_user(body: UserCreate):
    user_id = f"USR-{uuid.uuid4().hex[:6].upper()}"
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (id, username, display_name, role, email, active, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (user_id, body.username, body.display_name, body.role, body.email, 1, now, now)
        )
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Could not create user: {e}")

    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    u = dict(cursor.fetchone())
    u["active"] = bool(u.get("active", 1))
    conn.close()
    return {"status": "created", "user": u}


@router.put("/{user_id}")
def update_user(user_id: str, body: UserUpdate):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    r = cursor.fetchone()
    if not r:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    existing = dict(r)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    updates = {}
    if body.display_name is not None:
        updates["display_name"] = body.display_name
    if body.role is not None:
        updates["role"] = body.role
    if body.email is not None:
        updates["email"] = body.email
    if body.active is not None:
        updates["active"] = 1 if body.active else 0
    updates["updated_at"] = now

    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [user_id]
        cursor.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
        conn.commit()

    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    u = dict(cursor.fetchone())
    u["active"] = bool(u.get("active", 1))
    conn.close()
    return {"status": "updated", "user": u}


@router.delete("/{user_id}")
def deactivate_user(user_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    r = cursor.fetchone()
    if not r:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    cursor.execute("UPDATE users SET active = 0, updated_at = ? WHERE id = ?", (now, user_id))
    conn.commit()
    conn.close()
    return {"status": "deactivated", "user_id": user_id}
