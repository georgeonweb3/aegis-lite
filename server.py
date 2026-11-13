#!/usr/bin/env python3
"""
Aegis Lite API server. Python stdlib only.
Run: python3 server.py   (PORT env, default 8000)
Store: sqlite file, AEGIS_LITE_DB env or the default aegis_lite.db next
to the aegis_lite module. Daily spend and payment records persist
across restarts and are shared by every instance using the same file.
Endpoints:
  POST /check  -> JSON verdict (body may include payment_id for
                  idempotent retries: max 2 retries per payment_id)
  GET  /health -> {"status":"ok"}
  GET  /       -> HTML dashboard (recent checks, in-memory)
  GET  /api/log -> JSON log
"""
import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from aegis_lite import Guard

guard = Guard(
    per_tx_limit_usd=1000,
    daily_limit_usd=500,
    blocklist=["0xScamWallet", "scam@example.com"],
    max_price_deviation_pct=10,
    store_path=os.environ.get("AEGIS_LITE_DB") or None,
)

LOG: list[dict] = []
MAX_LOG = 100


def dashboard_html() -> str:
    rows = ""
    for entry in reversed(LOG):
        v = entry["result"]["verdict"]
        color = "#16a34a" if v == "ALLOW" else "#dc2626"
        rows += (
            f"<tr><td>{entry['ts']}</td>"
            f"<td>{entry['request'].get('agent_id','')}</td>"
            f"<td>{entry['request'].get('recipient','')}</td>"
            f"<td>${entry['request'].get('amount_usd','')}</td>"
            f"<td>{entry['request'].get('action','')}</td>"
            f"<td style='color:{color};font-weight:700'>{v}</td>"
            f"<td>{'; '.join(entry['result']['reasons'])}</td></tr>"
        )
    if not rows:
        rows = "<tr><td colspan='7' style='text-align:center;color:#666'>No checks yet. POST to /check</td></tr>"
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="5"><title>Aegis Lite Dashboard</title>
<style>body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;margin:0;padding:24px}}
h1{{margin:0 0 4px}} .sub{{color:#94a3b8;margin-bottom:20px}} table{{width:100%;border-collapse:collapse;background:#1e293b;border-radius:12px;overflow:hidden}}
th,td{{padding:10px 12px;text-align:left;border-bottom:1px solid #334155;font-size:14px}} th{{background:#020617}}
code{{background:#1e293b;padding:2px 6px;border-radius:6px}} .card{{background:#1e293b;padding:16px;border-radius:12px;margin-bottom:20px}}</style></head>
<body><h1>🛡️ Aegis Lite</h1><div class="sub">Agent Spend Guard &bull; per-tx $1,000 &bull; daily $500 &bull; max deviation 10% &bull; auto-refresh 5s</div>
<div class="card">Try it: <code>curl -X POST localhost:8000/check -H 'Content-Type: application/json' -d '{{"agent_id":"my-agent","recipient":"0xMerchant123","amount_usd":42,"action":"purchase"}}'</code></div>
<table><thead><tr><th>Time (UTC)</th><th>Agent</th><th>Recipient</th><th>Amount</th><th>Action</th><th>Verdict</th><th>Reasons</th></tr></thead><tbody>{rows}</tbody></table>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # quieter logs
        print(f"{self.address_string()} - {fmt % args}")

    def _send_json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, code, html):
        body = html.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "service": "aegis-lite", "checks_logged": len(LOG)})
        elif self.path == "/api/log":
            self._send_json(200, {"log": LOG})
        elif self.path == "/" or self.path == "/dashboard":
            self._send_html(200, dashboard_html())
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/check":
            self._send_json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode() or "{}")
        except Exception:
            self._send_json(400, {"verdict": "BLOCK", "allowed": False, "reasons": ["invalid JSON body"]})
            return
        result = guard.check(data)
        LOG.append({
            "ts": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "request": data,
            "result": result,
        })
        if len(LOG) > MAX_LOG:
            del LOG[: len(LOG) - MAX_LOG]
        self._send_json(200, result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"Aegis Lite running on http://127.0.0.1:{port}  (dashboard at /, health at /health)")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
