import sqlite3
import json
import os
import time

DB_PATH = os.path.join(os.path.dirname(__file__), "smartcctv.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # Alerts Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS alerts (
        id TEXT PRIMARY KEY,
        timestamp REAL,
        camera_id TEXT,
        camera_name TEXT,
        location TEXT,
        risk_score REAL,
        risk_level TEXT,
        status TEXT,
        types TEXT,
        reasons TEXT,
        zone TEXT,
        entity TEXT,
        clip_sha256 TEXT,
        evidence_path TEXT,
        snapshot_url TEXT,
        decided_by TEXT,
        decided_at TEXT,
        notes TEXT,
        hash_prev TEXT,
        hash_self TEXT
    )
    """)

    # Cameras Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cameras (
        id TEXT PRIMARY KEY,
        name TEXT,
        location TEXT,
        zone_type TEXT,
        status TEXT,
        fps REAL,
        rtsp_url TEXT,
        stream_url TEXT,
        protocol TEXT DEFAULT 'mjpeg',
        enabled INTEGER DEFAULT 1,
        map_x REAL,
        map_y REAL,
        zones TEXT,
        last_seen TEXT
    )
    """)

    # Ensure stream_url, protocol, and enabled columns exist in cameras table
    cursor.execute("PRAGMA table_info(cameras)")
    cam_cols = {row[1] for row in cursor.fetchall()}
    if "stream_url" not in cam_cols:
        cursor.execute("ALTER TABLE cameras ADD COLUMN stream_url TEXT")
    if "protocol" not in cam_cols:
        cursor.execute("ALTER TABLE cameras ADD COLUMN protocol TEXT DEFAULT 'mjpeg'")
    if "enabled" not in cam_cols:
        cursor.execute("ALTER TABLE cameras ADD COLUMN enabled INTEGER DEFAULT 1")

    # Analysis Jobs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS analysis_jobs (
        id TEXT PRIMARY KEY,
        filename TEXT,
        file_path TEXT,
        status TEXT,
        created_at TEXT,
        zones TEXT,
        progress REAL,
        current_frame INTEGER,
        total_frames INTEGER,
        peak_risk_score REAL,
        no_alert_reason TEXT,
        alerts_generated TEXT,
        result_json TEXT,
        live_tracks TEXT,
        live_alerts TEXT
    )
    """)
    # Migrate existing DBs: add columns if missing
    for col in ["live_tracks", "live_alerts"]:
        try:
            cursor.execute(f"ALTER TABLE analysis_jobs ADD COLUMN {col} TEXT")
        except Exception:
            pass  # Column already exists

    # Settings Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    # Audit Logs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id TEXT PRIMARY KEY,
        timestamp TEXT,
        actor TEXT,
        action TEXT,
        resource TEXT,
        details TEXT,
        hash_prev TEXT,
        hash_self TEXT
    )
    """)

    # Topology Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS topology (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    # Simple Audit Log Table (for settings changes, operational events)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action TEXT,
        user_name TEXT,
        object_type TEXT,
        object_id TEXT,
        detail TEXT,
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
