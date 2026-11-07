// JS example: check with Aegis Lite BEFORE spending. Node 18+ (global fetch).
// Run the server first: python3 server.py
// Then: node examples/agent_example.js

const AEGIS_URL = process.env.AEGIS_URL || "http://127.0.0.1:8000/check";

async function aegisCheck({ agent_id, recipient, amount_usd, action = "purchase", ...extra }) {
  const res = await fetch(AEGIS_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agent_id, recipient, amount_usd, action, ...extra }),
  });
  return res.json();
}

function spend(amount, recipient) {
  console.log(`💸 Actually spending $${amount} -> ${recipient} (your real spend code goes here)`);
}

const result = await aegisCheck({
  agent_id: "my-agent",
  recipient: "0xMerchant123",
  amount_usd: 42,
  action: "purchase",
  reference_price_usd: 42,
  quoted_price_usd: 42,
});

console.log("Check:", result.verdict, result.reasons);
if (result.verdict === "ALLOW") {
  spend(42, "0xMerchant123");
} else {
  console.log("Blocked. Agent stopped before spending.");
}

// Dangerous case
const blocked = await aegisCheck({
  agent_id: "my-agent",
  recipient: "0xMerchant123",
  amount_usd: 5000,
  action: "purchase",
});
console.log("Check 2:", blocked.verdict, blocked.reasons);
