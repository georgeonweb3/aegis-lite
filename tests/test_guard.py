import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import unittest
from aegis_lite import Guard

# Temp stores created by make_guard()/temp_guard() are closed and deleted
# in tearDownModule, so the suite never touches the real aegis_lite.db.
_TMP_GUARDS: list[Guard] = []
_TMP_PATHS: list[str] = []


def _temp_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    _TMP_PATHS.append(path)
    return path


def _register(g: Guard) -> Guard:
    _TMP_GUARDS.append(g)
    return g


def tearDownModule() -> None:
    for g in _TMP_GUARDS:
        try:
            g.close()
        except Exception:
            pass
    _TMP_GUARDS.clear()
    for path in _TMP_PATHS:
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(path + suffix)
            except OSError:
                pass
    _TMP_PATHS.clear()


def make_guard():
    return _register(Guard(
        per_tx_limit_usd=1000,
        daily_limit_usd=500,
        blocklist=["0xScamWallet"],
        max_price_deviation_pct=10,
        store_path=_temp_db(),
    ))


def temp_guard(**kwargs):
    defaults = dict(
        per_tx_limit_usd=1000,
        daily_limit_usd=500,
        max_price_deviation_pct=10,
    )
    defaults.update(kwargs)
    return _register(Guard(store_path=_temp_db(), **defaults))


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
        g = temp_guard(daily_limit_usd=100)
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
        g = temp_guard(allowlist=["0xOnlyThis"])
        r = g.check({"agent_id": "a1", "recipient": "0xOther", "amount_usd": 10, "action": "purchase"})
        self.assertEqual(r["verdict"], "BLOCK")
        r2 = g.check({"agent_id": "a1", "recipient": "0xOnlyThis", "amount_usd": 10, "action": "purchase"})
        self.assertEqual(r2["verdict"], "ALLOW")

    def test_blocked_does_not_count_toward_daily(self):
        g = make_guard()
        g.check({"agent_id": "a1", "recipient": "0xScamWallet", "amount_usd": 20, "action": "purchase"})
        self.assertEqual(g.daily_spent("a1"), 0)


class TestPersistence(unittest.TestCase):
    def test_restart_keeps_daily_spent(self):
        shared = _temp_db()
        g1 = _register(Guard(per_tx_limit_usd=1000, daily_limit_usd=100,
                             store_path=shared))
        g1.check({"agent_id": "a1", "recipient": "0xGood", "amount_usd": 42, "action": "purchase"})
        g1.check({"agent_id": "a1", "recipient": "0xGood", "amount_usd": 30, "action": "purchase"})
        self.assertEqual(g1.daily_spent("a1"), 72)
        g1.close()  # simulate a restart
        g2 = _register(Guard(per_tx_limit_usd=1000, daily_limit_usd=100,
                             store_path=shared))
        self.assertEqual(g2.daily_spent("a1"), 72)
        # The reopened guard enforces the spend it inherited.
        r = g2.check({"agent_id": "a1", "recipient": "0xGood", "amount_usd": 30, "action": "purchase"})
        self.assertEqual(r["verdict"], "BLOCK")
        self.assertTrue(any("daily limit" in x for x in r["reasons"]))

    def test_two_instances_share_one_store(self):
        shared = _temp_db()
        g1 = _register(Guard(per_tx_limit_usd=1000, daily_limit_usd=500,
                             store_path=shared))
        g2 = _register(Guard(per_tx_limit_usd=1000, daily_limit_usd=500,
                             store_path=shared))
        g1.check({"agent_id": "a1", "recipient": "0xGood", "amount_usd": 60, "action": "purchase"})
        # Second instance sees the first instance's spend immediately.
        self.assertEqual(g2.daily_spent("a1"), 60)
        r = g2.check({"agent_id": "a1", "recipient": "0xGood", "amount_usd": 450, "action": "purchase"})
        self.assertEqual(r["verdict"], "BLOCK")

    def test_new_utc_day_resets_to_zero(self):
        g = temp_guard(daily_limit_usd=100)
        g.check({"agent_id": "a1", "recipient": "0xGood", "amount_usd": 60,
                 "action": "purchase", "payment_id": "p-day"})
        self.assertEqual(g.daily_spent("a1"), 60)
        g._today = lambda: "2099-01-01"  # next UTC day
        self.assertEqual(g.daily_spent("a1"), 0)
        # Yesterday's payment no longer counts; retry is a fresh payment.
        r = g.check({"agent_id": "a1", "recipient": "0xGood", "amount_usd": 60,
                     "action": "purchase", "payment_id": "p-day"})
        self.assertEqual(r["verdict"], "ALLOW")
        self.assertEqual(r["attempts"], 1)
        self.assertEqual(g.daily_spent("a1"), 60)

    def test_store_fallback_when_unopenable(self):
        g = _register(Guard(store_path="/nonexistent-dir-xyz/aegis.db"))
        self.assertIsNone(g._conn)  # fell back to in-memory tracking
        r = g.check({"agent_id": "a1", "recipient": "0xGood", "amount_usd": 10, "action": "purchase"})
        self.assertEqual(r["verdict"], "ALLOW")
        self.assertEqual(g.daily_spent("a1"), 10)


class TestIdempotency(unittest.TestCase):
    def _pay(self, g, pid, amount=42, **extra):
        req = {"agent_id": "a1", "recipient": "0xGood", "amount_usd": amount,
               "action": "purchase", "payment_id": pid}
        req.update(extra)
        return g.check(req)

    def test_idempotent_retry_counted_once(self):
        g = temp_guard(daily_limit_usd=500)
        r1 = self._pay(g, "p1")
        self.assertEqual(r1["verdict"], "ALLOW")
        self.assertEqual(r1["attempts"], 1)
        self.assertEqual(g.daily_spent("a1"), 42)
        r2 = self._pay(g, "p1")
        self.assertEqual(r2["verdict"], "ALLOW")
        self.assertEqual(r2["attempts"], 2)
        self.assertEqual(g.daily_spent("a1"), 42)  # not 84

    def test_third_retry_blocked(self):
        g = temp_guard(daily_limit_usd=500)
        self._pay(g, "p1")
        self.assertEqual(self._pay(g, "p1")["attempts"], 2)
        self.assertEqual(self._pay(g, "p1")["attempts"], 3)
        r = self._pay(g, "p1")
        self.assertEqual(r["verdict"], "BLOCK")
        self.assertTrue(any("retry limit exceeded" in x for x in r["reasons"]))
        self.assertEqual(g.daily_spent("a1"), 42)

    def test_retry_blocked_when_budget_eaten(self):
        # Two instances share one store; the first records other spending
        # that leaves no room under the second instance's lower cap.
        shared = _temp_db()
        g1 = _register(Guard(per_tx_limit_usd=1000, daily_limit_usd=500,
                             store_path=shared))
        g2 = _register(Guard(per_tx_limit_usd=1000, daily_limit_usd=100,
                             store_path=shared))
        self._pay(g1, "pa", amount=60)
        g1.check({"agent_id": "a1", "recipient": "0xGood", "amount_usd": 400, "action": "purchase"})
        self.assertEqual(g2.daily_spent("a1"), 460)
        r = self._pay(g2, "pa", amount=60)
        self.assertEqual(r["verdict"], "BLOCK")
        self.assertTrue(any("daily limit" in x for x in r["reasons"]))
        # Blocked retry did not consume an attempt.
        self.assertEqual(r["attempts"], 1)

    def test_payment_id_reuse_with_different_payload_blocked(self):
        g = temp_guard(daily_limit_usd=500)
        self._pay(g, "p1", amount=42)
        r = self._pay(g, "p1", amount=43)
        self.assertEqual(r["verdict"], "BLOCK")
        self.assertTrue(any("different payload" in x for x in r["reasons"]))
        r2 = g.check({"agent_id": "a1", "recipient": "0xOther", "amount_usd": 42,
                      "action": "purchase", "payment_id": "p1"})
        self.assertEqual(r2["verdict"], "BLOCK")
        self.assertEqual(g.daily_spent("a1"), 42)

    def test_blocked_retry_does_not_consume_attempt(self):
        g = temp_guard(daily_limit_usd=500)
        self._pay(g, "p1")
        # Retry blocked on price deviation: no budget used, no attempt used.
        r = self._pay(g, "p1", reference_price_usd=100, quoted_price_usd=150)
        self.assertEqual(r["verdict"], "BLOCK")
        self.assertEqual(r["attempts"], 1)
        self.assertEqual(g.daily_spent("a1"), 42)
        # A clean retry still works and is attempt 2.
        r2 = self._pay(g, "p1")
        self.assertEqual(r2["verdict"], "ALLOW")
        self.assertEqual(r2["attempts"], 2)
        self.assertEqual(g.daily_spent("a1"), 42)

    def test_no_payment_id_behaves_as_before(self):
        g = temp_guard(daily_limit_usd=500)
        r1 = g.check({"agent_id": "a1", "recipient": "0xGood", "amount_usd": 42, "action": "purchase"})
        r2 = g.check({"agent_id": "a1", "recipient": "0xGood", "amount_usd": 42, "action": "purchase"})
        self.assertEqual(r1["verdict"], "ALLOW")
        self.assertEqual(r2["verdict"], "ALLOW")
        self.assertEqual(g.daily_spent("a1"), 84)  # counted twice, as before
        self.assertNotIn("payment_id", r1)


if __name__ == "__main__":
    unittest.main()
