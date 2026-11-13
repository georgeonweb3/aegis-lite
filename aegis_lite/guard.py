"""Aegis Lite - Agent Spend Guard. Python stdlib only."""
from __future__ import annotations

import os
import re
import sqlite3
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_BLOCKED_ACTIONS = [
    "unlimited_approval",
    "approve_unlimited",
    "unlimited_token_approval",
    "setApprovalForAll",
    "set_approval_for_all",
]

# Default sqlite store, created next to this module. One file is shared by
# every Guard instance (and every process) that points at it, so the daily
# budget survives restarts and is enforced across instances.
DEFAULT_STORE_FILENAME = "aegis_lite.db"

# Retries allowed per payment_id after the first check (3 checks total).
MAX_RETRIES = 2


def _norm(value: str) -> str:
    """Normalize for comparison: lower, strip non-alnum."""
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


# Normalized forms of default blocked actions
_DEFAULT_BLOCKED_NORM = {_norm(a) for a in DEFAULT_BLOCKED_ACTIONS}


def _default_store_path() -> str:
    return str(Path(__file__).resolve().parent / DEFAULT_STORE_FILENAME)


class Guard:
    """
    Pre-flight spend guard for AI agents.

    Config:
        per_tx_limit_usd: max for a single transaction
        daily_limit_usd: max total per agent per UTC day (persisted in
            sqlite, shared across restarts and instances)
        blocklist: recipients that are always blocked (case-insensitive)
        allowlist: if non-empty, only these recipients are allowed
        blocked_actions: action names that are always blocked
        max_price_deviation_pct: max allowed |quoted-ref|/ref * 100
        store_path: sqlite file for daily spend + payment records.
            Default aegis_lite.db next to this module. ":memory:" keeps
            everything in a per-instance sqlite db. If the store cannot
            be opened, the guard falls back to in-memory tracking and
            logs a warning (restarts will reset daily spend).
        max_retries: retries allowed per payment_id after the first
            check (default 2, i.e. 3 checks total per payment).

    Retries / idempotency:
        Pass "payment_id" in the check request to make a payment
        retry-safe. The first check records the spend once. A retry
        with the same payment_id re-runs every check with the payment's
        own amount excluded from daily spend (it is already counted),
        so it cannot double-count; a 3rd retry is blocked, and reusing
        a payment_id with a different amount/recipient/action is
        blocked. Blocked checks never consume budget and never count
        toward the retry cap. Without a payment_id, behaviour is
        exactly as before (no double-count protection possible).

    Usage:
        guard = Guard(per_tx_limit_usd=1000, daily_limit_usd=500,
                      blocklist=["0xScam"], max_price_deviation_pct=10)
        result = guard.check({...})
        if result["verdict"] == "ALLOW": ...
    """

    def __init__(
        self,
        per_tx_limit_usd: float = 1000.0,
        daily_limit_usd: float = 500.0,
        blocklist=None,
        allowlist=None,
        blocked_actions=None,
        max_price_deviation_pct: float = 10.0,
        store_path: str | None = None,
        max_retries: int = MAX_RETRIES,
    ):
        self.per_tx_limit_usd = float(per_tx_limit_usd)
        self.daily_limit_usd = float(daily_limit_usd)
        self.blocklist = {str(x).lower() for x in (blocklist or [])}
        self.allowlist = {str(x).lower() for x in (allowlist or [])}
        raw_blocked = blocked_actions if blocked_actions is not None else DEFAULT_BLOCKED_ACTIONS
        self.blocked_actions = list(raw_blocked)
        self._blocked_norm = {_norm(a) for a in self.blocked_actions} | _DEFAULT_BLOCKED_NORM if blocked_actions is None else {_norm(a) for a in self.blocked_actions}
        # If caller supplied custom list, still always block the two critical ones
        self._blocked_norm |= {"setapprovalforall"}
        self.max_price_deviation_pct = float(max_price_deviation_pct)
        self.max_retries = int(max_retries)
        # Serializes threads in-process; BEGIN IMMEDIATE serializes
        # processes sharing the same store file.
        self._lock = threading.RLock()
        # In-memory fallback state (used only when the store cannot open).
        # {agent_id: {"date": "YYYY-MM-DD", "spent": float}}
        self._daily: dict[str, dict] = {}
        # {payment_id: {"agent_id", "day", "recipient", "action", "amount", "attempts"}}
        self._payments: dict[str, dict] = {}
        self._store_path = store_path if store_path is not None else _default_store_path()
        self._conn = self._open_store(self._store_path)
        if self._conn is None:
            print(
                f"aegis-lite: could not open store {self._store_path!r}; "
                "using in-memory tracking (restarts will reset daily spend)",
                file=sys.stderr,
            )

    # -- store ----------------------------------------------------------
    def _open_store(self, path: str):
        try:
            conn = sqlite3.connect(
                path, timeout=5.0, isolation_level=None, check_same_thread=False
            )
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS daily_spend (
                    agent_id TEXT NOT NULL,
                    day TEXT NOT NULL,
                    spent REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY (agent_id, day))"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS payments (
                    payment_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    day TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    action TEXT NOT NULL,
                    amount REAL NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 1)"""
            )
            return conn
        except sqlite3.Error:
            return None

    def close(self) -> None:
        """Close the store connection (safe to call repeatedly)."""
        conn, self._conn = self._conn, None
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass

    # -- daily tracking -------------------------------------------------
    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def daily_spent(self, agent_id: str) -> float:
        with self._lock:
            if self._conn is not None:
                row = self._conn.execute(
                    "SELECT spent FROM daily_spend WHERE agent_id = ? AND day = ?",
                    (agent_id, self._today()),
                ).fetchone()
                return float(row[0]) if row else 0.0
            entry = self._daily.get(agent_id)
            if not entry or entry["date"] != self._today():
                return 0.0
            return float(entry["spent"])

    def _record_spend(self, agent_id: str, amount: float) -> None:
        # Legacy helper kept for the in-memory fallback; the store path
        # records spend inside the check transaction instead.
        today = self._today()
        entry = self._daily.get(agent_id)
        if not entry or entry["date"] != today:
            self._daily[agent_id] = {"date": today, "spent": float(amount)}
        else:
            entry["spent"] += float(amount)

    def reset_daily(self, agent_id: str | None = None) -> None:
        """Clear recorded spend (and payment records) for an agent, or all."""
        with self._lock:
            if self._conn is not None:
                if agent_id is None:
                    self._conn.execute("DELETE FROM daily_spend")
                    self._conn.execute("DELETE FROM payments")
                else:
                    self._conn.execute(
                        "DELETE FROM daily_spend WHERE agent_id = ?", (agent_id,)
                    )
                    self._conn.execute(
                        "DELETE FROM payments WHERE agent_id = ?", (agent_id,)
                    )
            else:
                if agent_id is None:
                    self._daily.clear()
                    self._payments.clear()
                else:
                    self._daily.pop(agent_id, None)
                    for pid in [
                        p for p, row in self._payments.items()
                        if row["agent_id"] == agent_id
                    ]:
                        del self._payments[pid]

    # -- store/memory backend primitives (call with self._lock held) ----
    def _tx_begin(self) -> None:
        if self._conn is not None:
            self._conn.execute("BEGIN IMMEDIATE")

    def _tx_commit(self) -> None:
        if self._conn is not None:
            self._conn.execute("COMMIT")

    def _tx_rollback(self) -> None:
        if self._conn is not None:
            self._conn.execute("ROLLBACK")

    def _get_payment(self, payment_id: str) -> dict | None:
        if self._conn is not None:
            row = self._conn.execute(
                "SELECT agent_id, day, recipient, action, amount, attempts"
                " FROM payments WHERE payment_id = ?",
                (payment_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "agent_id": row[0],
                "day": row[1],
                "recipient": row[2],
                "action": row[3],
                "amount": float(row[4]),
                "attempts": int(row[5]),
            }
        row = self._payments.get(payment_id)
        return dict(row) if row is not None else None

    def _get_spent(self, agent_id: str, day: str) -> float:
        if self._conn is not None:
            row = self._conn.execute(
                "SELECT spent FROM daily_spend WHERE agent_id = ? AND day = ?",
                (agent_id, day),
            ).fetchone()
            return float(row[0]) if row else 0.0
        entry = self._daily.get(agent_id)
        if not entry or entry["date"] != day:
            return 0.0
        return float(entry["spent"])

    def _add_spent(self, agent_id: str, day: str, amount: float) -> None:
        if self._conn is not None:
            self._conn.execute(
                "INSERT INTO daily_spend (agent_id, day, spent) VALUES (?, ?, ?)"
                " ON CONFLICT(agent_id, day) DO UPDATE SET spent = spent + excluded.spent",
                (agent_id, day, float(amount)),
            )
        else:
            entry = self._daily.get(agent_id)
            if not entry or entry["date"] != day:
                self._daily[agent_id] = {"date": day, "spent": float(amount)}
            else:
                entry["spent"] += float(amount)

    def _put_payment(self, payment_id: str, row: dict) -> None:
        if self._conn is not None:
            self._conn.execute(
                "INSERT INTO payments"
                " (payment_id, agent_id, day, recipient, action, amount, attempts)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(payment_id) DO UPDATE SET"
                " agent_id = excluded.agent_id, day = excluded.day,"
                " recipient = excluded.recipient, action = excluded.action,"
                " amount = excluded.amount, attempts = excluded.attempts",
                (
                    payment_id,
                    row["agent_id"],
                    row["day"],
                    row["recipient"],
                    row["action"],
                    float(row["amount"]),
                    int(row["attempts"]),
                ),
            )
        else:
            self._payments[payment_id] = dict(row)

    # -- main check -----------------------------------------------------
    def check(self, request: dict) -> dict:
        if not isinstance(request, dict):
            return self._verdict(False, ["request must be an object"], request)

        agent_id = str(request.get("agent_id") or "unknown")
        recipient = str(request.get("recipient") or "")
        action = str(request.get("action") or "")
        amount = request.get("amount_usd")
        payment_id = request.get("payment_id")
        payment_id = str(payment_id) if payment_id else None

        reasons: list[str] = []

        # Amount validation
        try:
            amount_f = float(amount) if amount is not None else None
        except (TypeError, ValueError):
            amount_f = None

        if amount_f is None:
            reasons.append("missing or invalid amount_usd")
            amount_f = 0.0
        elif amount_f < 0:
            reasons.append("amount_usd cannot be negative")
        elif amount_f == 0 and _norm(action) not in _DEFAULT_BLOCKED_NORM:
            # zero amount non-approval is odd but not blocked by itself
            pass

        # Blocked actions (check first - even $0 unlimited approval is dangerous)
        action_norm = _norm(action)
        is_blocked_action = False
        if action_norm in self._blocked_norm:
            is_blocked_action = True
        elif "setapprovalforall" in action_norm:
            is_blocked_action = True
        elif "unlimited" in action_norm and "approv" in action_norm:
            is_blocked_action = True

        if is_blocked_action:
            reasons.append(f"blocked action: {action}")

        # Recipient blocklist / allowlist
        recip_lower = recipient.lower()
        if not recipient:
            reasons.append("missing recipient")
        else:
            if recip_lower in self.blocklist:
                reasons.append(f"recipient is blocklisted: {recipient}")
            if self.allowlist and recip_lower not in self.allowlist:
                reasons.append(f"recipient is not in allowlist: {recipient}")

        # Per-tx limit
        if amount_f is not None and amount_f > self.per_tx_limit_usd:
            reasons.append(
                f"amount ${amount_f:,.2f} exceeds per-tx limit ${self.per_tx_limit_usd:,.2f}"
            )

        # Price deviation
        ref = request.get("reference_price_usd")
        quoted = request.get("quoted_price_usd")
        if ref is not None and quoted is not None:
            try:
                ref_f = float(ref)
                quoted_f = float(quoted)
                if ref_f > 0:
                    deviation = abs(quoted_f - ref_f) / ref_f * 100.0
                    if deviation > self.max_price_deviation_pct:
                        reasons.append(
                            f"price deviation {deviation:.1f}% exceeds max "
                            f"{self.max_price_deviation_pct:.1f}% "
                            f"(reference ${ref_f:,.2f}, quoted ${quoted_f:,.2f})"
                        )
                else:
                    reasons.append("reference_price_usd must be > 0")
            except (TypeError, ValueError):
                reasons.append("invalid reference_price_usd / quoted_price_usd")

        # Daily limit + idempotency + record: one atomic step, so two
        # instances cannot both pass the cap at once and a retry cannot
        # double-count.
        with self._lock:
            return self._check_atomic(
                agent_id, recipient, action, amount_f, reasons, payment_id
            )

    def _check_atomic(
        self,
        agent_id: str,
        recipient: str,
        action: str,
        amount_f: float,
        reasons: list[str],
        payment_id: str | None,
    ) -> dict:
        today = self._today()
        existing = self._get_payment(payment_id) if payment_id else None
        is_retry = False
        attempts = 0

        if existing is not None:
            if existing["day"] != today:
                # A new UTC day: the old record no longer counts toward
                # today's budget, so this is a fresh payment.
                existing = None
            elif (
                existing["agent_id"] != agent_id
                or existing["recipient"] != recipient.lower()
                or existing["action"] != _norm(action)
                or existing["amount"] != amount_f
            ):
                attempts = existing["attempts"]
                reasons.append(
                    "payment_id already used with a different payload"
                    " (agent, recipient, action or amount changed)"
                )
            elif existing["attempts"] > self.max_retries:
                attempts = existing["attempts"]
                reasons.append(
                    f"retry limit exceeded: payment_id already checked "
                    f"{existing['attempts']} times (max {self.max_retries} retries)"
                )
            else:
                is_retry = True
                attempts = existing["attempts"]

        # Daily limit: a retry's own amount is already counted, so it is
        # excluded from the spend under test.
        spent_so_far = self._get_spent(agent_id, today)
        effective_spent = spent_so_far - existing["amount"] if is_retry else spent_so_far
        if amount_f is not None and (effective_spent + amount_f) > self.daily_limit_usd:
            reasons.append(
                f"daily limit exceeded: spent ${effective_spent:,.2f} + ${amount_f:,.2f} "
                f"> daily limit ${self.daily_limit_usd:,.2f}"
            )

        base_result = {
            "agent_id": agent_id,
            "recipient": recipient,
            "action": action,
            "amount_usd": amount_f,
            "daily_limit_usd": self.daily_limit_usd,
            "per_tx_limit_usd": self.per_tx_limit_usd,
        }
        if payment_id is not None:
            base_result["payment_id"] = payment_id

        if reasons:
            # BLOCK: no state changes. Blocked checks never consume
            # budget and never count toward the retry cap.
            result = {
                "verdict": "BLOCK",
                "allowed": False,
                "reasons": reasons,
                "daily_spent_usd": spent_so_far,
                **base_result,
            }
            if payment_id is not None:
                result["attempts"] = attempts
            return result

        # ALLOW: record spend + payment atomically.
        self._tx_begin()
        try:
            if payment_id is not None:
                if is_retry:
                    self._put_payment(
                        payment_id,
                        {
                            "agent_id": agent_id,
                            "day": today,
                            "recipient": recipient.lower(),
                            "action": _norm(action),
                            "amount": amount_f,
                            "attempts": attempts + 1,
                        },
                    )
                    attempts = attempts + 1
                else:
                    self._put_payment(
                        payment_id,
                        {
                            "agent_id": agent_id,
                            "day": today,
                            "recipient": recipient.lower(),
                            "action": _norm(action),
                            "amount": amount_f,
                            "attempts": 1,
                        },
                    )
                    attempts = 1
                    self._add_spent(agent_id, today, amount_f)
            else:
                self._add_spent(agent_id, today, amount_f)
            self._tx_commit()
        except Exception:
            self._tx_rollback()
            return {
                "verdict": "BLOCK",
                "allowed": False,
                "reasons": ["internal error recording the check; nothing was spent"],
                "daily_spent_usd": spent_so_far,
                **base_result,
            }

        spent_after = self._get_spent(agent_id, today)
        if is_retry:
            allow_reasons = [
                f"all checks passed (retry {attempts - 1} of {self.max_retries};"
                " spend already counted)"
            ]
        else:
            allow_reasons = ["all checks passed"]
        result = {
            "verdict": "ALLOW",
            "allowed": True,
            "reasons": allow_reasons,
            "daily_spent_usd": spent_after,
            **base_result,
        }
        if payment_id is not None:
            result["attempts"] = attempts
        return result

    def _verdict(self, allowed: bool, reasons: list[str], request) -> dict:
        return {
            "verdict": "ALLOW" if allowed else "BLOCK",
            "allowed": allowed,
            "reasons": reasons,
            "agent_id": str((request or {}).get("agent_id") or "unknown") if isinstance(request, dict) else "unknown",
            "amount_usd": 0,
            "daily_spent_usd": 0,
            "daily_limit_usd": self.daily_limit_usd,
            "per_tx_limit_usd": self.per_tx_limit_usd,
        }
