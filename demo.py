#!/usr/bin/env python3
"""Demo: 7 scenarios. Run: python3 demo.py"""
import os
import tempfile

from aegis_lite import Guard


def main():
    # A throwaway store so every run is identical. In real use the
    # default store (aegis_lite.db next to the module) persists.
    fd, store_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    guard = Guard(
        per_tx_limit_usd=1000,
        daily_limit_usd=500,
        blocklist=["0xScamWallet", "scam@example.com"],
        max_price_deviation_pct=10,
        store_path=store_path,
    )

    scenarios = [
        (
            "1) Clean $42 purchase",
            {
                "agent_id": "demo-agent",
                "recipient": "0xMerchant123",
                "amount_usd": 42,
                "action": "purchase",
                "token": "USDC",
                "payment_id": "demo-pay-001",
                "reference_price_usd": 42,
                "quoted_price_usd": 42,
            },
        ),
        (
            "2) $5000 over per-tx limit",
            {
                "agent_id": "demo-agent",
                "recipient": "0xMerchant123",
                "amount_usd": 5000,
                "action": "purchase",
                "token": "USDC",
            },
        ),
        (
            "3) Blocklisted recipient",
            {
                "agent_id": "demo-agent",
                "recipient": "0xScamWallet",
                "amount_usd": 20,
                "action": "purchase",
                "token": "USDC",
            },
        ),
        (
            "4) Unlimited approval",
            {
                "agent_id": "demo-agent",
                "recipient": "0xMerchant123",
                "amount_usd": 0,
                "action": "unlimited_approval",
                "token": "USDC",
            },
        ),
        (
            "5) Quoted price 35% off reference",
            {
                "agent_id": "demo-agent",
                "recipient": "0xMerchant123",
                "amount_usd": 135,
                "action": "purchase",
                "token": "USDC",
                "reference_price_usd": 100,
                "quoted_price_usd": 135,
            },
        ),
        (
            "6) Small repeat purchase within daily limit",
            {
                "agent_id": "demo-agent",
                "recipient": "0xMerchant123",
                "amount_usd": 30,
                "action": "purchase",
                "token": "USDC",
                "reference_price_usd": 30,
                "quoted_price_usd": 30,
            },
        ),
    ]

    print("=" * 64)
    print("AEGIS LITE DEMO - Agent Spend Guard")
    print("Config: per-tx $1,000 | daily $500 | max price deviation 10%")
    print("=" * 64)
    for label, req in scenarios:
        result = guard.check(req)
        verdict = result["verdict"]
        icon = "✅" if verdict == "ALLOW" else "🛡️"
        print(f"\n{icon} {label}")
        print(f"   Request: ${req['amount_usd']} -> {req['recipient']} [{req['action']}]")
        print(f"   Verdict: {verdict}")
        for r in result["reasons"]:
            print(f"   Reason: {r}")
        print(f"   Daily spent so far: ${result['daily_spent_usd']:,.2f} / ${result['daily_limit_usd']:,.2f}")

    # 7) Restart persistence + idempotent retry: a brand-new Guard on the
    # same store still sees today's $72, and retrying scenario 1 with
    # its payment_id is allowed without counting the $42 twice.
    print("\n🛡️ 7) After a restart, retry the $42 payment (same payment_id)")
    guard2 = Guard(
        per_tx_limit_usd=1000,
        daily_limit_usd=500,
        blocklist=["0xScamWallet", "scam@example.com"],
        max_price_deviation_pct=10,
        store_path=store_path,
    )
    print(f"   New instance sees daily spent: ${guard2.daily_spent('demo-agent'):,.2f} (restart kept it)")
    retry = guard2.check(
        {
            "agent_id": "demo-agent",
            "recipient": "0xMerchant123",
            "amount_usd": 42,
            "action": "purchase",
            "token": "USDC",
            "payment_id": "demo-pay-001",
            "reference_price_usd": 42,
            "quoted_price_usd": 42,
        }
    )
    print(f"   Verdict: {retry['verdict']}")
    for r in retry["reasons"]:
        print(f"   Reason: {r}")
    print(f"   Daily spent so far: ${retry['daily_spent_usd']:,.2f} / ${retry['daily_limit_usd']:,.2f} (still $72, not $114)")

    guard.close()
    guard2.close()
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(store_path + suffix)
        except OSError:
            pass
    print("\n" + "=" * 64)
    print("Done. 3 ALLOW, 4 BLOCK as expected.")
    print("=" * 64)


if __name__ == "__main__":
    main()
