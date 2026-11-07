#!/usr/bin/env python3
"""Demo: 6 scenarios. Run: python3 demo.py"""
from aegis_lite import Guard


def main():
    guard = Guard(
        per_tx_limit_usd=1000,
        daily_limit_usd=500,
        blocklist=["0xScamWallet", "scam@example.com"],
        max_price_deviation_pct=10,
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
    print("\n" + "=" * 64)
    print("Done. 2 ALLOW, 4 BLOCK as expected.")
    print("=" * 64)


if __name__ == "__main__":
    main()
