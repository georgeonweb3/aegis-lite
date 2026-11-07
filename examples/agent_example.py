#!/usr/bin/env python3
"""Python example: check with Aegis Lite BEFORE spending. Stdlib only."""
import json
import os
import urllib.request

AEGIS_URL = os.environ.get("AEGIS_URL", "http://127.0.0.1:8000/check")


def aegis_check(agent_id, recipient, amount_usd, action="purchase", **extra):
    payload = {"agent_id": agent_id, "recipient": recipient,
               "amount_usd": amount_usd, "action": action, **extra}
    req = urllib.request.Request(
        AEGIS_URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def spend(amount, recipient):
    print(f"💸 Actually spending ${amount} -> {recipient} (your real spend code goes here)")


if __name__ == "__main__":
    # 1) Clean purchase
    result = aegis_check("my-agent", "0xMerchant123", 42, reference_price_usd=42, quoted_price_usd=42)
    print("Check 1:", result["verdict"], result["reasons"])
    if result["verdict"] == "ALLOW":
        spend(42, "0xMerchant123")

    # 2) Dangerous approval - will be blocked, spend never runs
    result = aegis_check("my-agent", "0xMerchant123", 0, action="setApprovalForAll")
    print("Check 2:", result["verdict"], result["reasons"])
    if result["verdict"] == "ALLOW":
        spend(0, "0xMerchant123")
    else:
        print("   -> Blocked, agent did NOT get unlimited approval.")
