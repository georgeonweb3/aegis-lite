# Aegis Lite - Agent Spend Guard

**Your AI agent should not spend or sign blind.**

Aegis Lite is a tiny pre-flight guard you drop in front of any agent that moves money. Before the agent spends, it asks Aegis: ALLOW or BLOCK, with reasons. One bad call stopped is worth more than 100 good calls made faster.

Built by George Agbe. Lightweight version of Aegis (spend control for AI agents on Base) + tgp-guard (pre-flight guard). No contracts, no dependencies. Python stdlib only.

## What it blocks

- Spend over your per-transaction limit
- Spend over your daily limit (tracked per agent, in memory)
- Payments to blocklisted recipients, or anyone not on your allowlist
- Unlimited token approvals and `setApprovalForAll` - even at $0
- Quotes that drift too far from the reference price (default 10%)

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
  "reference_price_usd": 100,
  "quoted_price_usd": 102
}
```

`token`, `reference_price_usd`, and `quoted_price_usd` are optional. Price check only runs when both prices are present.

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

Note: daily tracking is in-memory in this Lite version. Restart clears it. The hosted version persists it per project.

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
server.py              http.server API + dashboard
demo.py                6 scenarios
examples/              Python + JS integration examples
tests/test_guard.py    unittest, all scenarios + daily exhaustion
SALES_KIT.md           pitch, DM script, first 10 buyers
```

## License

MIT
