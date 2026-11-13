# Aegis Lite - Agent Spend Guard

**Your AI agent should not spend or sign blind.**

Aegis Lite is a tiny pre-flight guard you drop in front of any agent that moves money. Before the agent spends, it asks Aegis: ALLOW or BLOCK, with reasons. One bad call stopped is worth more than 100 good calls made faster.

Built by George Agbe. Lightweight version of Aegis (spend control for AI agents on Base) + tgp-guard (pre-flight guard). No contracts, no dependencies. Python stdlib only.

## What it blocks

- Spend over your per-transaction limit
- Spend over your daily limit (tracked per agent, persisted in SQLite, shared across restarts and instances)
- Payments to blocklisted recipients, or anyone not on your allowlist
- Unlimited token approvals and `setApprovalForAll` - even at $0
- Quotes that drift too far from the reference price (default 10%)
- A payment retried past its retry cap, or a `payment_id` reused with a different payload

## Retries, done safely

Pass a `payment_id` (any idempotency key, e.g. your payment UUID) in the check request. The first check records the spend once. If the payment fails and your agent retries with the same `payment_id`, the guard re-runs every check with that payment's own amount excluded from daily spend, so it cannot double-count. At most 2 retries per `payment_id` (3 checks total); a 3rd retry is blocked, and reusing a `payment_id` with a different amount, recipient or action is blocked. If other spending has eaten the daily budget since, the retry is blocked too. Blocked checks never consume budget and never count toward the retry cap. Without a `payment_id`, behaviour is exactly as before — but a retried payment can then double-count or skip re-check, so use one whenever your agent retries.

## Quick start

```bash
python3 demo.py                 # 6 scenarios, no server needed
python3 -m unittest discover -s tests -v
python3 server.py               # API + dashboard on http://127.0.0.1:8000
```

## Integration in 5 lines of code

```python
from aegis_lite import Guard
guard = Guard(per_tx_limit_usd=1000, daily_limit_usd=500, blocklist=["0xScam"], max_price_deviation_pct=10)
result = guard.check({"agent_id": "my-agent", "recipient": "0xMerchant", "amount_usd": 42, "action": "purchase"})
if result["verdict"] == "ALLOW":
    do_the_spend()  # only runs if Aegis said yes
```

Or via the API (any language):

```bash
curl -X POST http://127.0.0.1:8000/check \
  -H 'Content-Type: application/json' \
  -d '{"agent_id":"my-agent","recipient":"0xMerchant123","amount_usd":42,"action":"purchase"}'
# {"verdict": "ALLOW", "allowed": true, "reasons": ["all checks passed"], ...}
```

JS example in `examples/agent_example.js`, Python API example in `examples/agent_example.py`.

## Request shape

```json
{
  "agent_id": "my-agent",
  "recipient": "0xMerchant123",
  "amount_usd": 42,
  "action": "purchase",
  "token": "USDC",
  "payment_id": "pay_01J…",
  "reference_price_usd": 100,
  "quoted_price_usd": 102
}
```

`token`, `payment_id`, `reference_price_usd`, and `quoted_price_usd` are optional. Price check only runs when both prices are present. `payment_id` is your idempotency key for retries (see above); omit it only if your agent never retries a payment.

## API

| Endpoint | What |
|---|---|
| `POST /check` | Send a request, get `{"verdict": "ALLOW"\|"BLOCK", "reasons": [...]}` |
| `GET /health` | `{"status": "ok"}` |
| `GET /` | Dashboard with recent checks (in-memory log, auto-refresh) |
| `GET /api/log` | Same log as JSON |

## Config

| Option | Default | Meaning |
|---|---|---|
| `per_tx_limit_usd` | 1000 | Max single spend |
| `daily_limit_usd` | 500 | Max per agent per UTC day |
| `blocklist` | [] | Recipients always blocked |
| `allowlist` | [] | If set, only these recipients pass |
| `blocked_actions` | unlimited approval + setApprovalForAll | Actions always blocked |
| `max_price_deviation_pct` | 10 | Max quoted vs reference drift |
| `store_path` | `aegis_lite.db` next to the module | SQLite file for daily spend + payment records; the server reads `AEGIS_LITE_DB` instead. `":memory:"` keeps it per-instance |
| `max_retries` | 2 | Retries allowed per `payment_id` after the first check (3 checks total) |

Daily tracking is persisted in SQLite (WAL mode). Restarting the guard keeps today's spend, and two instances using the same store file share one budget — the check-and-record runs in a single transaction, so two instances cannot both pass the cap at once. A new UTC day still resets to zero. If the store file cannot be opened, the guard logs a warning and falls back to in-memory tracking (restarts will reset daily spend, as before).

## Pricing

- **$29/month per project** - hosted API, persistent daily limits, dashboard, blocklist management, email alerts on BLOCK.
- **$149 one-time audit** - I review your agent spend paths, set your limits and blocklists, wire Aegis into your code, and test 6 attack scenarios live with you.

Free self-host: this repo, MIT. Use it, ship safer agents.

## Who buys this

Hackathon teams shipping an agent in a weekend who do not want a drained wallet in their demo. Indie agent builders on Base and Robinhood Chain. Anyone whose agent holds a key, approves tokens, or pays for APIs, data, or x402 services. If your agent can spend, you need a guard in front of it.

## Files

```
aegis_lite/guard.py    core Guard class
aegis_lite/__init__.py exports Guard
aegis_lite.db          sqlite store, created at runtime (gitignored)
server.py              http.server API + dashboard
demo.py                7 scenarios
examples/              Python + JS integration examples
tests/test_guard.py    unittest, all scenarios + daily exhaustion + persistence/retries
SALES_KIT.md           pitch, DM script, first 10 buyers
```

## License

MIT
