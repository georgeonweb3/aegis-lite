import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import unittest
from aegis_lite import Guard


def make_guard():
    return Guard(
        per_tx_limit_usd=1000,
        daily_limit_usd=500,
        blocklist=["0xScamWallet"],
        max_price_deviation_pct=10,
    )


class TestGuard(unittest.TestCase):
    def test_1_clean_purchase_allow(self):
        g = make_guard()
        r = g.check({"agent_id": "a1", "recipient": "0xMerchant123", "amount_usd": 42,
                     "action": "purchase", "reference_price_usd": 42, "quoted_price_usd": 42})
        self.assertEqual(r["verdict"], "ALLOW")
        self.assertTrue(r["allowed"])

    def test_2_over_per_tx_block(self):
        g = make_guard()
        r = g.check({"agent_id": "a1", "recipient": "0xMerchant123", "amount_usd": 5000, "action": "purchase"})
        self.assertEqual(r["verdict"], "BLOCK")
        self.assertTrue(any("per-tx" in x for x in r["reasons"]))

    def test_3_blocklisted_block(self):
        g = make_guard()
        r = g.check({"agent_id": "a1", "recipient": "0xScamWallet", "amount_usd": 20, "action": "purchase"})
        self.assertEqual(r["verdict"], "BLOCK")
        self.assertTrue(any("blocklisted" in x for x in r["reasons"]))

    def test_4_unlimited_approval_block(self):
        g = make_guard()
        r = g.check({"agent_id": "a1", "recipient": "0xMerchant123", "amount_usd": 0, "action": "unlimited_approval"})
        self.assertEqual(r["verdict"], "BLOCK")
        self.assertTrue(any("blocked action" in x for x in r["reasons"]))

    def test_4b_set_approval_for_all_block(self):
        g = make_guard()
        r = g.check({"agent_id": "a1", "recipient": "0xMerchant123", "amount_usd": 0, "action": "setApprovalForAll"})
        self.assertEqual(r["verdict"], "BLOCK")

    def test_5_price_deviation_block(self):
        g = make_guard()
        r = g.check({"agent_id": "a1", "recipient": "0xMerchant123", "amount_usd": 135,
                     "action": "purchase", "reference_price_usd": 100, "quoted_price_usd": 135})
        self.assertEqual(r["verdict"], "BLOCK")
        self.assertTrue(any("price deviation" in x for x in r["reasons"]))

    def test_6_small_repeat_within_daily_allow(self):
        g = make_guard()
        r1 = g.check({"agent_id": "a1", "recipient": "0xMerchant123", "amount_usd": 42, "action": "purchase"})
        self.assertEqual(r1["verdict"], "ALLOW")
        r2 = g.check({"agent_id": "a1", "recipient": "0xMerchant123", "amount_usd": 30, "action": "purchase"})
        self.assertEqual(r2["verdict"], "ALLOW")
        self.assertEqual(r2["daily_spent_usd"], 72)

    def test_daily_limit_exhaustion(self):
        g = Guard(per_tx_limit_usd=1000, daily_limit_usd=100, max_price_deviation_pct=10)
        r1 = g.check({"agent_id": "a1", "recipient": "0xGood", "amount_usd": 60, "action": "purchase"})
        self.assertEqual(r1["verdict"], "ALLOW")
        r2 = g.check({"agent_id": "a1", "recipient": "0xGood", "amount_usd": 30, "action": "purchase"})
        self.assertEqual(r2["verdict"], "ALLOW")
        r3 = g.check({"agent_id": "a1", "recipient": "0xGood", "amount_usd": 20, "action": "purchase"})
        self.assertEqual(r3["verdict"], "BLOCK")
        self.assertTrue(any("daily limit" in x for x in r3["reasons"]))
        # BLOCK should not increase spent
        self.assertEqual(g.daily_spent("a1"), 90)

    def test_allowlist(self):
        g = Guard(per_tx_limit_usd=1000, daily_limit_usd=500, allowlist=["0xOnlyThis"])
        r = g.check({"agent_id": "a1", "recipient": "0xOther", "amount_usd": 10, "action": "purchase"})
        self.assertEqual(r["verdict"], "BLOCK")
        r2 = g.check({"agent_id": "a1", "recipient": "0xOnlyThis", "amount_usd": 10, "action": "purchase"})
        self.assertEqual(r2["verdict"], "ALLOW")

    def test_blocked_does_not_count_toward_daily(self):
        g = make_guard()
        g.check({"agent_id": "a1", "recipient": "0xScamWallet", "amount_usd": 20, "action": "purchase"})
        self.assertEqual(g.daily_spent("a1"), 0)


if __name__ == "__main__":
    unittest.main()
