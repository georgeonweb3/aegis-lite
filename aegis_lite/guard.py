"""Aegis Lite - Agent Spend Guard. Python stdlib only."""
from __future__ import annotations

import re
from datetime import datetime, timezone

DEFAULT_BLOCKED_ACTIONS = [
    "unlimited_approval",
    "approve_unlimited",
    "unlimited_token_approval",
    "setApprovalForAll",
    "set_approval_for_all",
]


def _norm(value: str) -> str:
    """Normalize for comparison: lower, strip non-alnum."""
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


# Normalized forms of default blocked actions
_DEFAULT_BLOCKED_NORM = {_norm(a) for a in DEFAULT_BLOCKED_ACTIONS}


class Guard:
    """
    Pre-flight spend guard for AI agents.

    Config:
        per_tx_limit_usd: max for a single transaction
        daily_limit_usd: max total per agent per UTC day (in-memory)
        blocklist: recipients that are always blocked (case-insensitive)
        allowlist: if non-empty, only these recipients are allowed
        blocked_actions: action names that are always blocked
        max_price_deviation_pct: max allowed |quoted-ref|/ref * 100

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
        # {agent_id: {"date": "YYYY-MM-DD", "spent": float}}
        self._daily: dict[str, dict] = {}

    # -- daily tracking -------------------------------------------------
    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def daily_spent(self, agent_id: str) -> float:
        entry = self._daily.get(agent_id)
        if not entry or entry["date"] != self._today():
            return 0.0
        return float(entry["spent"])

    def _record_spend(self, agent_id: str, amount: float) -> None:
        today = self._today()
        entry = self._daily.get(agent_id)
        if not entry or entry["date"] != today:
            self._daily[agent_id] = {"date": today, "spent": float(amount)}
        else:
            entry["spent"] += float(amount)

    def reset_daily(self, agent_id: str | None = None) -> None:
        if agent_id is None:
            self._daily.clear()
        else:
            self._daily.pop(agent_id, None)

    # -- main check -----------------------------------------------------
    def check(self, request: dict) -> dict:
        reasons: list[str] = []

        if not isinstance(request, dict):
            return self._verdict(False, ["request must be an object"], request)

        agent_id = str(request.get("agent_id") or "unknown")
        recipient = str(request.get("recipient") or "")
        action = str(request.get("action") or "")
        amount = request.get("amount_usd")

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

        # Daily limit
        spent_so_far = self.daily_spent(agent_id)
        if amount_f is not None and (spent_so_far + amount_f) > self.daily_limit_usd:
            reasons.append(
                f"daily limit exceeded: spent ${spent_so_far:,.2f} + ${amount_f:,.2f} "
                f"> daily limit ${self.daily_limit_usd:,.2f}"
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

        allowed = len(reasons) == 0
        if allowed:
            self._record_spend(agent_id, amount_f)
            spent_after = self.daily_spent(agent_id)
            return {
                "verdict": "ALLOW",
                "allowed": True,
                "reasons": ["all checks passed"],
                "agent_id": agent_id,
                "recipient": recipient,
                "action": action,
                "amount_usd": amount_f,
                "daily_spent_usd": spent_after,
                "daily_limit_usd": self.daily_limit_usd,
                "per_tx_limit_usd": self.per_tx_limit_usd,
            }
        else:
            return {
                "verdict": "BLOCK",
                "allowed": False,
                "reasons": reasons,
                "agent_id": agent_id,
                "recipient": recipient,
                "action": action,
                "amount_usd": amount_f,
                "daily_spent_usd": spent_so_far,
                "daily_limit_usd": self.daily_limit_usd,
                "per_tx_limit_usd": self.per_tx_limit_usd,
            }

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
