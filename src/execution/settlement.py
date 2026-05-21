from __future__ import annotations

from datetime import datetime, timezone

from src.storage.db import Database


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class SettlementEngine:
    def __init__(self, db: Database) -> None:
        self.db = db

    def settle_expired_positions(self, now: datetime | None = None) -> int:
        current = now.astimezone(timezone.utc) if now is not None else datetime.now(timezone.utc)
        positions = self.db.open_positions(limit=1000)
        settled = 0
        for position in positions:
            expiry = _parse_iso(position["expiry_at"])
            if expiry is None or expiry > current:
                continue
            invested = float(position["invested_usd"])
            payout = float(position["expected_payout_usd"])
            realized_pnl = payout - invested
            balance = self.db.latest_balance() or 0.0
            with self.db.transaction():
                self.db.update_position(
                    int(position["id"]),
                    status="resolved",
                    realized_pnl=realized_pnl,
                    resolved_at=current.isoformat(),
                )
                self.db.update_trade(
                    int(position["trade_id"]),
                    status="resolved",
                    finished_at=current.isoformat(),
                    realized_pnl=realized_pnl,
                )
                self.db.snapshot_balance(balance + payout, note=f"paper settle trade_id={position['trade_id']}")
            settled += 1
        return settled
