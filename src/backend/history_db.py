"""SQLite-backed resource usage history."""

import os
import sqlite3
import time


DB_PATH = os.path.expanduser("~/.local/share/powercontrol/history.db")


def _get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS process_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            pid INTEGER NOT NULL,
            name TEXT NOT NULL,
            cpu_percent REAL NOT NULL,
            mem_percent REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_timestamp ON process_usage(timestamp)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_name ON process_usage(name)
    """)
    conn.commit()
    return conn


def record_snapshot(processes):
    """Store a snapshot of process usage. processes = list of dicts with name, cpu, mem."""
    conn = _get_conn()
    now = time.time()
    rows = [(now, p["pid"], p["name"], p["cpu"], p["mem"]) for p in processes]
    conn.executemany(
        "INSERT INTO process_usage (timestamp, pid, name, cpu_percent, mem_percent) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


def get_top_apps(hours=1, limit=10):
    """Get top apps by average CPU usage over time window.
    Returns list of (name, avg_cpu, avg_mem, sample_count).
    """
    conn = _get_conn()
    cutoff = time.time() - (hours * 3600)
    rows = conn.execute("""
        SELECT name, AVG(cpu_percent), AVG(mem_percent), COUNT(*)
        FROM process_usage
        WHERE timestamp > ?
        GROUP BY name
        ORDER BY AVG(cpu_percent) DESC
        LIMIT ?
    """, (cutoff, limit)).fetchall()
    conn.close()
    return [
        {"name": r[0], "avg_cpu": r[1], "avg_mem": r[2], "samples": r[3]}
        for r in rows
    ]


def cleanup_old(days=7):
    """Remove records older than N days."""
    conn = _get_conn()
    cutoff = time.time() - (days * 86400)
    conn.execute("DELETE FROM process_usage WHERE timestamp < ?", (cutoff,))
    conn.commit()
    conn.close()
