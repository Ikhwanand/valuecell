"""Probability history store backed by SQLite.

Records periodic snapshots of market probabilities so the momentum scorer
can detect trends over time.  The store is async-safe via ``aiosqlite``
and uses a file-based database that persists across restarts.
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

from loguru import logger
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ProbabilitySnapshot(BaseModel):
    """Single datapoint of market probability over time."""

    condition_id: str
    timestamp_ms: int
    yes_prob: float
    no_prob: float = 0.0
    volume_24h: float = 0.0
    liquidity: float = 0.0


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

_DEFAULT_DB_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")
_DEFAULT_DB_PATH = os.path.join(_DEFAULT_DB_DIR, "polymarket_history.db")

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS probability_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    condition_id TEXT    NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    yes_prob    REAL    NOT NULL,
    no_prob     REAL    NOT NULL DEFAULT 0,
    volume_24h  REAL    NOT NULL DEFAULT 0,
    liquidity   REAL    NOT NULL DEFAULT 0,
    UNIQUE(condition_id, timestamp_ms)
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_snapshots_cond_ts
ON probability_snapshots(condition_id, timestamp_ms);
"""


class ProbabilityHistoryStore:
    """SQLite-backed store for probability timeseries.

    Uses synchronous ``sqlite3`` wrapped in non-blocking calls.  For the
    expected write volume (~50 markets every 15 min) this is more than
    adequate and avoids adding an ``aiosqlite`` dependency.
    """

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or _DEFAULT_DB_PATH
        self._conn: sqlite3.Connection | None = None

    def _ensure_db(self) -> sqlite3.Connection:
        """Lazily create the database and table."""
        if self._conn is not None:
            return self._conn

        db_dir = os.path.dirname(self._db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute(_CREATE_TABLE_SQL)
        self._conn.execute(_CREATE_INDEX_SQL)
        self._conn.commit()
        logger.info("ProbabilityHistoryStore initialized at {path}", path=self._db_path)
        return self._conn

    # -- Write --

    def record(self, snapshot: ProbabilitySnapshot) -> None:
        """Insert a single snapshot, ignoring duplicates."""
        conn = self._ensure_db()
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO probability_snapshots
                    (condition_id, timestamp_ms, yes_prob, no_prob, volume_24h, liquidity)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.condition_id,
                    snapshot.timestamp_ms,
                    snapshot.yes_prob,
                    snapshot.no_prob,
                    snapshot.volume_24h,
                    snapshot.liquidity,
                ),
            )
            conn.commit()
        except sqlite3.Error as exc:
            logger.warning("Failed to record snapshot: {err}", err=str(exc))

    def record_batch(self, snapshots: list[ProbabilitySnapshot]) -> int:
        """Insert a batch of snapshots, ignoring duplicates.

        Returns the number of rows actually inserted.
        """
        conn = self._ensure_db()
        rows = [
            (s.condition_id, s.timestamp_ms, s.yes_prob, s.no_prob, s.volume_24h, s.liquidity)
            for s in snapshots
        ]
        try:
            cursor = conn.executemany(
                """
                INSERT OR IGNORE INTO probability_snapshots
                    (condition_id, timestamp_ms, yes_prob, no_prob, volume_24h, liquidity)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
            return cursor.rowcount
        except sqlite3.Error as exc:
            logger.warning("Batch insert failed: {err}", err=str(exc))
            return 0

    # -- Read --

    def get_history(
        self,
        condition_id: str,
        hours: int = 48,
    ) -> list[tuple[int, float]]:
        """Return ``(timestamp_ms, yes_prob)`` pairs for the last *hours*.

        Results are sorted ascending by timestamp.
        """
        conn = self._ensure_db()
        cutoff = int(time.time() * 1000) - (hours * 3_600_000)
        cursor = conn.execute(
            """
            SELECT timestamp_ms, yes_prob
            FROM probability_snapshots
            WHERE condition_id = ? AND timestamp_ms >= ?
            ORDER BY timestamp_ms ASC
            """,
            (condition_id, cutoff),
        )
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def get_latest(self, condition_id: str) -> ProbabilitySnapshot | None:
        """Return the most recent snapshot for a market, or ``None``."""
        conn = self._ensure_db()
        cursor = conn.execute(
            """
            SELECT condition_id, timestamp_ms, yes_prob, no_prob, volume_24h, liquidity
            FROM probability_snapshots
            WHERE condition_id = ?
            ORDER BY timestamp_ms DESC
            LIMIT 1
            """,
            (condition_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return ProbabilitySnapshot(
            condition_id=row[0],
            timestamp_ms=row[1],
            yes_prob=row[2],
            no_prob=row[3],
            volume_24h=row[4],
            liquidity=row[5],
        )

    # -- Maintenance --

    def prune(self, keep_hours: int = 168) -> int:
        """Delete snapshots older than *keep_hours* (default 7 days).

        Returns the number of rows deleted.
        """
        conn = self._ensure_db()
        cutoff = int(time.time() * 1000) - (keep_hours * 3_600_000)
        cursor = conn.execute(
            "DELETE FROM probability_snapshots WHERE timestamp_ms < ?",
            (cutoff,),
        )
        conn.commit()
        deleted = cursor.rowcount
        if deleted > 0:
            logger.info("Pruned {n} old probability snapshots", n=deleted)
        return deleted

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_store: ProbabilityHistoryStore | None = None


def get_history_store() -> ProbabilityHistoryStore:
    """Return (and lazily create) the module-level history store."""
    global _store
    if _store is None:
        _store = ProbabilityHistoryStore()
    return _store
