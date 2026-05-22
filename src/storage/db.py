from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None, timeout=30.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, open(SCHEMA_PATH, encoding="utf-8") as file:
            self._conn.executescript(file.read())

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                yield self._conn
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def insert_opportunity(self, **fields: object) -> int:
        fields.setdefault("detected_at", _utcnow_iso())
        cols = ", ".join(fields.keys())
        placeholders = ", ".join(f":{key}" for key in fields)
        with self._lock:
            cur = self._conn.execute(f"INSERT INTO opportunities ({cols}) VALUES ({placeholders})", fields)
            return int(cur.lastrowid or 0)

    def insert_event(self, level: str, message: str, context: dict[str, object] | None = None) -> int:
        payload = None if context is None else json.dumps(context, ensure_ascii=False, default=str)
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO bot_events (created_at, level, message, context_json) VALUES (?, ?, ?, ?)",
                (_utcnow_iso(), level, message, payload),
            )
            return int(cur.lastrowid or 0)

    def recent_opportunities(self, limit: int = 100) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute("SELECT * FROM opportunities ORDER BY detected_at DESC LIMIT ?", (limit,)).fetchall()

    def recent_events(self, limit: int = 100) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute("SELECT * FROM bot_events ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()

    def recent_scan_events(self, limit: int = 100) -> list[dict[str, object]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT created_at, level, message, context_json FROM bot_events WHERE message = 'scan telemetry' ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out: list[dict[str, object]] = []
        for row in rows:
            payload = self._parse_context_json(row["context_json"])
            payload.update({"created_at": row["created_at"], "level": row["level"], "message": row["message"]})
            out.append(payload)
        return out

    def recent_near_arb_markets(self, limit: int = 100) -> list[dict[str, object]]:
        scan_events = self.recent_scan_events(limit=limit)
        out: list[dict[str, object]] = []
        for event in scan_events:
            created_at = event.get("created_at")
            markets = event.get("best_markets")
            if not isinstance(markets, list):
                continue
            for market in markets:
                if not isinstance(market, dict):
                    continue
                row = dict(market)
                row["created_at"] = created_at
                out.append(row)
        out.sort(key=lambda row: (row.get("sum_asks") is None, row.get("sum_asks", 999)))
        return out[:limit]

    def recent_preorder_events(self, limit: int = 100) -> list[dict[str, object]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT created_at, level, message, context_json FROM bot_events WHERE message = 'preorder telemetry' ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out: list[dict[str, object]] = []
        for row in rows:
            payload = self._parse_context_json(row["context_json"])
            payload.update({"created_at": row["created_at"], "level": row["level"], "message": row["message"]})
            out.append(payload)
        return out

    def recent_preorder_results(self, limit: int = 100) -> list[dict[str, object]]:
        events = self.recent_preorder_events(limit=limit)
        out: list[dict[str, object]] = []
        for event in events:
            created_at = event.get("created_at")
            results = event.get("results")
            if not isinstance(results, list):
                continue
            for result in results:
                if not isinstance(result, dict):
                    continue
                row = dict(result)
                row["created_at"] = created_at
                out.append(row)
        return out[:limit]

    def recent_preorder_candidates(self, limit: int = 100) -> list[dict[str, object]]:
        events = self.recent_preorder_events(limit=limit)
        out: list[dict[str, object]] = []
        for event in events:
            created_at = event.get("created_at")
            candidates = event.get("best_candidates")
            if not isinstance(candidates, list):
                continue
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                row = dict(candidate)
                row["created_at"] = created_at
                out.append(row)
        return out[:limit]

    def recent_mm_events(self, limit: int = 100) -> list[dict[str, object]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT created_at, level, message, context_json FROM bot_events WHERE message = 'mm telemetry' ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out: list[dict[str, object]] = []
        for row in rows:
            payload = self._parse_context_json(row["context_json"])
            payload.update({"created_at": row["created_at"], "level": row["level"], "message": row["message"]})
            out.append(payload)
        return out

    def recent_mm_results(self, limit: int = 100) -> list[dict[str, object]]:
        events = self.recent_mm_events(limit=limit)
        out: list[dict[str, object]] = []
        for event in events:
            created_at = event.get("created_at")
            results = event.get("results")
            if not isinstance(results, list):
                continue
            for result in results:
                if not isinstance(result, dict):
                    continue
                row = dict(result)
                row["created_at"] = created_at
                out.append(row)
        return out[:limit]

    def recent_mm_ws_events(self, limit: int = 100) -> list[dict[str, object]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT created_at, level, message, context_json FROM bot_events WHERE message = 'mm ws telemetry' ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out: list[dict[str, object]] = []
        for row in rows:
            payload = self._parse_context_json(row["context_json"])
            payload.update({"created_at": row["created_at"], "level": row["level"], "message": row["message"]})
            out.append(payload)
        return out

    def recent_mm_ws_results(self, limit: int = 100) -> list[dict[str, object]]:
        events = self.recent_mm_ws_events(limit=limit)
        out: list[dict[str, object]] = []
        for event in events:
            created_at = event.get("created_at")
            results = event.get("results")
            if not isinstance(results, list):
                continue
            for result in results:
                if not isinstance(result, dict):
                    continue
                row = dict(result)
                row["created_at"] = created_at
                out.append(row)
        return out[:limit]

    def recent_ws_signal_events(self, limit: int = 100) -> list[dict[str, object]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT created_at, level, message, context_json FROM bot_events WHERE message = 'ws signal telemetry' ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out: list[dict[str, object]] = []
        for row in rows:
            payload = self._parse_context_json(row["context_json"])
            payload.update({"created_at": row["created_at"], "level": row["level"], "message": row["message"]})
            out.append(payload)
        return out

    def recent_ws_signal_results(self, limit: int = 100) -> list[dict[str, object]]:
        events = self.recent_ws_signal_events(limit=limit)
        out: list[dict[str, object]] = []
        for event in events:
            created_at = event.get("created_at")
            results = event.get("results")
            if not isinstance(results, list):
                continue
            for result in results:
                if not isinstance(result, dict):
                    continue
                row = dict(result)
                row["created_at"] = created_at
                out.append(row)
        return out[:limit]

    def recent_pair_mm_events(self, limit: int = 100) -> list[dict[str, object]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT created_at, level, message, context_json FROM bot_events WHERE message = 'pair mm telemetry' ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out: list[dict[str, object]] = []
        for row in rows:
            payload = self._parse_context_json(row["context_json"])
            payload.update({"created_at": row["created_at"], "level": row["level"], "message": row["message"]})
            out.append(payload)
        return out

    def recent_pair_mm_results(self, limit: int = 100) -> list[dict[str, object]]:
        events = self.recent_pair_mm_events(limit=limit)
        out: list[dict[str, object]] = []
        for event in events:
            created_at = event.get("created_at")
            results = event.get("results")
            if not isinstance(results, list):
                continue
            for result in results:
                if not isinstance(result, dict):
                    continue
                row = dict(result)
                row["created_at"] = created_at
                out.append(row)
        return out[:limit]

    def recent_reward_market_events(self, limit: int = 100) -> list[dict[str, object]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT created_at, level, message, context_json FROM bot_events WHERE message = 'reward market telemetry' ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out: list[dict[str, object]] = []
        for row in rows:
            payload = self._parse_context_json(row["context_json"])
            payload.update({"created_at": row["created_at"], "level": row["level"], "message": row["message"]})
            out.append(payload)
        return out

    def recent_reward_market_results(self, limit: int = 100) -> list[dict[str, object]]:
        events = self.recent_reward_market_events(limit=limit)
        out: list[dict[str, object]] = []
        for event in events:
            created_at = event.get("created_at")
            results = event.get("results")
            if not isinstance(results, list):
                continue
            for result in results:
                if not isinstance(result, dict):
                    continue
                row = dict(result)
                row["created_at"] = created_at
                out.append(row)
        return out[:limit]

    def insert_trade(self, opportunity_id: int, mode: str, status: str = "pending", expected_pnl: float | None = None, notes: str | None = None) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO trades (opportunity_id, started_at, mode, status, expected_pnl, notes) VALUES (?, ?, ?, ?, ?, ?)",
                (opportunity_id, _utcnow_iso(), mode, status, expected_pnl, notes),
            )
            return int(cur.lastrowid or 0)

    def update_trade(self, trade_id: int, **fields: object) -> None:
        if not fields:
            return
        sets = ", ".join(f"{key} = :{key}" for key in fields)
        fields["trade_id"] = trade_id
        with self._lock:
            self._conn.execute(f"UPDATE trades SET {sets} WHERE id = :trade_id", fields)

    def insert_leg(self, **fields: object) -> int:
        fields.setdefault("submitted_at", _utcnow_iso())
        cols = ", ".join(fields.keys())
        placeholders = ", ".join(f":{key}" for key in fields)
        with self._lock:
            cur = self._conn.execute(f"INSERT INTO legs ({cols}) VALUES ({placeholders})", fields)
            return int(cur.lastrowid or 0)

    def insert_position(self, **fields: object) -> int:
        cols = ", ".join(fields.keys())
        placeholders = ", ".join(f":{key}" for key in fields)
        with self._lock:
            cur = self._conn.execute(f"INSERT INTO positions ({cols}) VALUES ({placeholders})", fields)
            return int(cur.lastrowid or 0)

    def snapshot_balance(self, balance_usd: float, note: str | None = None) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO balance_snapshots (captured_at, balance_usd, note) VALUES (?, ?, ?)",
                (_utcnow_iso(), balance_usd, note),
            )
            return int(cur.lastrowid or 0)

    def latest_balance(self) -> float | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT balance_usd FROM balance_snapshots ORDER BY captured_at DESC LIMIT 1"
            ).fetchone()
            return float(row["balance_usd"]) if row else None

    def open_exposure_usd(self) -> float:
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(invested_usd), 0.0) AS s FROM positions WHERE status = 'open'"
            ).fetchone()
            return float(row["s"]) if row else 0.0

    def recent_trades(self, limit: int = 100) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute("SELECT * FROM trades ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()

    def open_positions(self, limit: int = 200) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(
                "SELECT * FROM positions WHERE status = 'open' ORDER BY expiry_at ASC LIMIT ?",
                (limit,),
            ).fetchall()

    def resolved_positions(self, limit: int = 200) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(
                "SELECT * FROM positions WHERE status = 'resolved' ORDER BY resolved_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

    def update_position(self, position_id: int, **fields: object) -> None:
        if not fields:
            return
        sets = ", ".join(f"{key} = :{key}" for key in fields)
        fields["position_id"] = position_id
        with self._lock:
            self._conn.execute(f"UPDATE positions SET {sets} WHERE id = :position_id", fields)

    def realized_pnl_total(self) -> float:
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(realized_pnl), 0.0) AS s FROM trades WHERE realized_pnl IS NOT NULL"
            ).fetchone()
            return float(row["s"]) if row else 0.0

    def equity_curve(self, limit: int = 1000) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(
                "SELECT captured_at, balance_usd, note FROM balance_snapshots ORDER BY captured_at ASC LIMIT ?",
                (limit,),
            ).fetchall()

    @staticmethod
    def _parse_context_json(value: object) -> dict[str, object]:
        if not isinstance(value, str) or not value:
            return {}
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
