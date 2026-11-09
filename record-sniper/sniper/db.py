"""SQLite: remembers what you've already been alerted about, and caches price lookups."""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path


class Store:
    def __init__(self, path: str | Path):
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                key TEXT PRIMARY KEY,
                want TEXT, title TEXT, url TEXT, source TEXT, tier TEXT,
                total REAL, local INTEGER,
                first_alerted TEXT, last_alerted TEXT
            );
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY, value TEXT, fetched_at REAL
            );
            """
        )

    # --- alerts -----------------------------------------------------------
    def should_alert(self, key: str, total: float, drop_pct: float) -> bool:
        row = self.conn.execute("SELECT total FROM alerts WHERE key=?", (key,)).fetchone()
        if row is None:
            return True
        # Re-alert only if the price dropped meaningfully since we last told you.
        return total <= row["total"] * (1 - drop_pct / 100)

    def record_alert(self, deal) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        l = deal.listing
        self.conn.execute(
            """INSERT INTO alerts (key, want, title, url, source, tier, total, local, first_alerted, last_alerted)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(key) DO UPDATE SET total=excluded.total, tier=excluded.tier,
                 last_alerted=excluded.last_alerted""",
            (l.key, deal.want.label, l.title, l.url, l.source, deal.tier, deal.total, int(l.local), now, now),
        )
        self.conn.commit()

    def recent_alerts(self, limit: int = 50) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM alerts ORDER BY last_alerted DESC LIMIT ?", (limit,)
        ).fetchall()

    # --- cache ------------------------------------------------------------
    def cache_get(self, key: str, ttl_hours: float | None):
        row = self.conn.execute("SELECT value, fetched_at FROM cache WHERE key=?", (key,)).fetchone()
        if row is None:
            return None
        if ttl_hours is not None and time.time() - row["fetched_at"] > ttl_hours * 3600:
            return None
        return json.loads(row["value"])

    def cache_set(self, key: str, value) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO cache (key, value, fetched_at) VALUES (?,?,?)",
            (key, json.dumps(value), time.time()),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
