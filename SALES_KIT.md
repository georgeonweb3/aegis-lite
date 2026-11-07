# Aegis Lite - Sales Kit

## One-line pitch

Your agent can be prompt-injected, fed a bad price, or tricked into an unlimited approval in one call. Aegis Lite sits in front of the spend and says BLOCK before the money moves.

## 30-second pitch (for a call or voice note)

> Every agent builder I talk to has the same fear: my agent holds a wallet, what stops it going rogue or getting drained? I built Aegis for my own agents on Base for exactly that. Aegis Lite is the lightweight version. Five lines of code, it checks every spend against your per-tx limit, daily limit, blocklist, and price drift, and it auto-blocks unlimited approvals and setApprovalForAll. You get an ALLOW or BLOCK with a reason before any transaction happens. Hosted is $29 a month per project. Or I do a $149 audit where I wire it in and attack-test your agent live.

## Who feels this pain most

1. Hackathon teams demoing with a real wallet (one drain = dead demo)
2. Trading / sniping / mint agents that quote prices from external sources
3. Agents paying via x402, APIs, or other agents (many small spends that add up)
4. Builders who gave an agent a token approval and never revoked it

## DM script - cold (X / Farcaster / Discord)

> Hey [name], saw your [project] agent - clean build.
> Quick q: what stops it if it gets a bad quote or tries to spend over budget in a loop?
> I built a tiny spend guard for my own agents (Aegis Lite) - 5 lines, blocks over-limit spends, blocklisted wallets, unlimited approvals, and quotes 10%+ off reference. Happy to run your agent through 6 attack scenarios free and show you the verdicts, no pitch if it all passes.
> Want me to test it?

## DM script - warm (someone you already replied to)

> Update on that guard I mentioned - Lite version is live now. Send me your typical spend call (amount, recipient, action) and I will run it plus 5 attack variants through it today and send you the ALLOW/BLOCK log. If it catches anything, hosted cover is $29/mo, or I can wire it in for you.

## Objection handling

- "I already check amounts in my code." -> Cool, that is per-tx. What about daily total in a loop, a blocklisted recipient, or setApprovalForAll at $0? Aegis covers the paths builders forget, in one place you can audit.
- "Too expensive." -> One blocked drain pays for years of $29. The self-host version is free and MIT, start there.
- "Will it slow my agent?" -> One local check or one HTTP call, under 10ms locally. It only runs before a spend, not on every prompt.
- "I do not trust another service with my keys." -> It never touches keys. It only sees amount, recipient, and action, and returns a verdict. Your agent still signs, or does not.

## Where to find the first 10 buyers

1. **Your own hackathon circles (highest conversion):** Telegraph Season II builders, PayPal AI Hackathon teams, Agentware teams. You already have context and replies with several of them. Start with builders whose agents move money.
2. **Base builder community:** Farcaster /base-builds and Base Discord. Post the demo log, not a sales pitch: "6 attacks on my agent, 4 blocked, here is why."
3. **Robinhood Chain builders:** New chain, honeypot wave, no safety tooling yet. Offer the scanner + guard bundle angle.
4. **X search:** `building an AI agent` + `wallet`, `autonomous agent` + `payments`, `x402` builders. Reply with a specific risk in their design first, DM second.
5. **Hackathon Discords this month:** Any team in Apps & Agents / DeFi tracks with a live demo wallet.
6. **Agent directories:** Teams listed on agentusecases.ai and similar directories, especially any with a payments use case.
7. **Your Alpha Toolkit audience:** Short: "I attacked my own money agent 6 ways" with the demo output on screen, link in description.

## First 10 target list - workflow

For each prospect, log: name, project, agent spend path, risk you spotted, DM date, free test offered (Y/N), result.
Goal: 30 DMs -> 10 free tests -> 3 paid ($29/mo or $149 audit). Do not pitch price before showing a BLOCK on their own scenario.

## Launch post draft (X / Farcaster)

> I attacked my own AI agent 6 ways today.
> $42 clean buy: ALLOW
> $5,000 spend: BLOCK, over limit
> Scam wallet: BLOCK, blocklisted
> Unlimited approval: BLOCK
> Quote 35% over market: BLOCK
> Small repeat buy: ALLOW
> That guard is now a tiny SDK anyone can drop in. Aegis Lite, 5 lines of code. DM me your agent spend call and I will attack-test it free this week.

## Pricing recap to quote

- Self-host Lite: free, MIT
- Hosted: $29/month per project
- Audit + integration: $149 one-time
