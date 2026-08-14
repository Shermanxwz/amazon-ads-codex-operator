from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .state import Store, now_iso

UTC = timezone.utc


class BudgetError(ValueError):
    pass


# Unknown/uncertain outcomes remain charged for the whole local day. A merely
# issued reservation may expire because the Amazon write was never authorized.
COUNTABLE = {
    "reserved",
    "pending",
    "unknown",
    "uncertain",
    "executed",
    "verified",
    "verification_failed",
}


class BudgetLedger:
    def __init__(self, store: Store, policy: dict[str, Any]):
        self.store = store
        self.policy = policy

    def _timezone_name(self) -> str:
        configured = str(self.policy.get("_account_timezone") or "").strip()
        if configured:
            try:
                ZoneInfo(configured)
                return configured
            except (ZoneInfoNotFoundError, ValueError):
                pass

        # Production runtime.db and owner.db are siblings. Reading the Owner
        # document here keeps the hard monetary day boundary independent of the
        # Planner and requires no Controller-supplied model data.
        owner_db = self.store.path.with_name("owner.db")
        if owner_db.exists():
            try:
                with sqlite3.connect(owner_db, timeout=2) as conn:
                    row = conn.execute(
                        "SELECT body_json FROM owner_documents WHERE kind='operator'"
                    ).fetchone()
                if row:
                    value = json.loads(row[0] or "{}")
                    timezone_name = str(value.get("timezone") or "UTC")
                    ZoneInfo(timezone_name)
                    return timezone_name
            except Exception:
                pass
        return "UTC"

    def day_key(self, at: datetime | None = None) -> str:
        current = at or datetime.now(UTC)
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        return current.astimezone(ZoneInfo(self._timezone_name())).date().isoformat()

    @staticmethod
    def _cleanup_expired(conn) -> None:
        # Only an unconsumed/never-executed reservation is time-reclaimable.
        # Once execution can have occurred, retain the amount for the local day
        # so delayed Amazon reporting cannot reopen Owner monetary capacity.
        conn.execute(
            "UPDATE reservations SET status='expired' "
            "WHERE status='reserved' AND expires_at<=?",
            (datetime.now(UTC).isoformat(),),
        )

    def reserved_total(self, day_key: str | None = None) -> float:
        day_key = day_key or self.day_key()
        marks = ",".join("?" for _ in COUNTABLE)
        with self.store.connection() as conn:
            self._cleanup_expired(conn)
            row = conn.execute(
                f"SELECT COALESCE(SUM(amount),0) total FROM reservations "
                f"WHERE day_key=? AND status IN ({marks})",
                (day_key, *sorted(COUNTABLE)),
            ).fetchone()
            return float(row["total"] or 0)

    def reserve(self, action_hash: str, amount: float, observed_spend: float) -> None:
        if amount <= 0:
            return
        ceiling = self.policy["money"].get("owner_daily_spend_ceiling")
        if ceiling is None:
            raise BudgetError(
                "owner_daily_spend_ceiling must be configured before autonomous spend increases"
            )
        buffer = float(self.policy["money"].get("platform_buffer_pct") or 0) / 100.0
        effective = float(ceiling) * (1.0 - buffer)
        day = self.day_key()
        expires = (
            datetime.now(UTC)
            + timedelta(seconds=int(self.policy["money"]["reservation_hold_seconds"]))
        ).isoformat()
        marks = ",".join("?" for _ in COUNTABLE)

        with self.store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._cleanup_expired(conn)
            existing = conn.execute(
                "SELECT status,amount FROM reservations WHERE action_hash=?",
                (action_hash,),
            ).fetchone()
            if existing:
                if existing["status"] in COUNTABLE:
                    return
                raise BudgetError(
                    f'action already has non-countable reservation status {existing["status"]}'
                )
            row = conn.execute(
                f"SELECT COALESCE(SUM(amount),0) total FROM reservations "
                f"WHERE day_key=? AND status IN ({marks})",
                (day, *sorted(COUNTABLE)),
            ).fetchone()
            reserved = float(row["total"] or 0)
            current = max(0.0, float(observed_spend)) + reserved
            if current + amount > effective:
                raise BudgetError(
                    f"daily spend envelope exceeded: {current+amount:.2f} > {effective:.2f}"
                )
            conn.execute(
                "INSERT INTO reservations(day_key,action_hash,amount,status,expires_at,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (day, action_hash, float(amount), "reserved", expires, now_iso()),
            )

    def mark(self, action_hash: str, status: str) -> None:
        with self.store.connection() as conn:
            conn.execute(
                "UPDATE reservations SET status=? WHERE action_hash=?",
                (status, action_hash),
            )

    def release(self, action_hash: str, reason: str = "cancelled") -> None:
        with self.store.connection() as conn:
            conn.execute(
                "UPDATE reservations SET status=? WHERE action_hash=? AND status='reserved'",
                (reason, action_hash),
            )
