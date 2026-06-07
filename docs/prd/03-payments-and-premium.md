# PRD 03 — Payments (USDT micropayments) & inference.club Premium

> **Status:** Draft for review. Not yet implemented.
>
> **Author:** Brian (spec) · drafted with Claude Code.
>
> **Scope:** Give inference.club a money layer. Two related but separable
> pieces: **(A) usage-based micropayments** so consumers can pay for
> inference and providers can get paid out, settled in **USDT on a
> testnet first**, exposed to AI agents through a standard
> **agent-payments protocol**; and **(B) inference.club Premium**, a
> recurring subscription (billed in fiat via **Stripe**, with a crypto
> path later) that unlocks higher limits, priority routing, support, and
> **payout eligibility**.
>
> **Explicitly out of scope (this PRD):** real-money mainnet launch
> (testnet only until a separate go-live PRD), KYC/AML program design,
> tax reporting, fiat bank payouts, multi-currency fiat pricing, and
> on-chain smart-contract escrow. We deliberately keep custody and chain
> complexity to a minimum — see §4.

---

## 1. Summary (and a plain-English crypto primer)

Today inference.club routes inference for free. Consumers spend nothing;
providers (people running GPUs on their own agents) earn nothing. This
PRD adds a **credit balance** to every account and two ways to fund it,
two ways to spend it, and one way to cash out.

Because the author is new to crypto, here is the whole mental model in
six sentences, then we never re-explain it:

1. **USDT** ("Tether") is a *stablecoin* — a crypto token that is always
   meant to be worth **$1.00**. 10 USDT ≈ $10. So we can price in USDT
   and reason in dollars.
2. A stablecoin lives on a **blockchain** (a public ledger). The same
   USDT exists on several chains (Ethereum, Tron, Polygon, Base…); they
   are not interchangeable without a bridge, so **we pick one chain and
   stick to it**.
3. A **testnet** is a free, fake-money clone of a blockchain used for
   development. Test-USDT has no value; you get it from a "faucet" (a
   free dispenser). **We build and demo entirely on testnet** and flip
   to mainnet only in a later, deliberate step.
4. A **wallet** is just a keypair: a public **address** (like an account
   number you can share) and a private **key** (the password — whoever
   has it controls the money). "Custodial" means *we* hold the key for
   the user; "non-custodial" means the *user* holds it. We start
   custodial-lite (§4) to keep UX a one-click.
5. **Tracking a payment** = watching the chain for a transaction that
   moved USDT *to our address* and crediting the right account. A
   transaction has a unique **tx hash** (receipt id); confirmation means
   the network has accepted it.
6. **Gas** is the small network fee to send a transaction, paid in the
   chain's native coin (e.g. ETH), *not* in USDT. We choose a cheap
   chain so gas is fractions of a cent, and we sponsor it where we can.

That's it. Everything below is plumbing around those six ideas.

This PRD introduces:

1. A **credit ledger** (`Wallet` + `LedgerEntry`) — the single source of
   truth for "how much does this account have / owe," denominated in
   **USDT-cents (micro-USDT)**, append-only, double-entry.
2. **Funding (top-up):** (a) **crypto deposit** — user sends test-USDT to
   a deposit address, we detect it and credit them; (b) **Stripe** — pay
   by card, we credit them (fiat → credits, no crypto for the user).
3. **Spending (metered debit):** every billable `InferenceRequest`
   debits the consumer's wallet by a transparent, per-modality price.
4. **Agent-native pay-per-call** via the **x402** protocol (HTTP `402
   Payment Required`) so autonomous agents can pay for `/v1/...` calls
   with no human in the loop — the agent-payment story.
5. **Provider earnings & payout:** providers accrue earnings per served
   request; **Premium** providers can **withdraw** to their own USDT
   address on testnet.
6. **inference.club Premium:** a Stripe subscription (monthly/annual)
   that raises limits, enables priority routing, dedicated/reserved
   capacity hints, support SLA, and **unlocks payout**.

---

## 2. Current state (grounded in code)

- **Accounts.** `accounts.CustomUser` (GitHub OAuth via `social_django`).
  Has `routing_preference`, `default_request_visibility`,
  `public_profile_enabled`. **No balance, no plan, no Stripe id today.**
- **One API key per user** (MVP) used for both agent heartbeat and
  OpenAI-client inference (see MVP-scope memory). Billing must attach to
  *the key's owner*.
- **Requests are already metered.** `inference.InferenceRequest` stores
  `prompt_tokens` / `completion_tokens` / `total_tokens`,
  `audio_seconds`, `image_count`, `latency_ms`, `ttft_ms`, `status`,
  `inference_type`, `provider`, `model_name`. **This is exactly the data
  a billing engine needs** — we price off these fields after a request
  completes.
- **Providers & services.** `Provider` (per user) exposes
  `ProviderService`s of type `llm` / `stt` / `tts` / `image`, each with an
  `access_policy` (`PRIVATE` / `AUTHENTICATED` / `RESTRICTED`). A served
  request already knows which provider/service handled it → we know *who
  to pay*.
- **Leaderboard.** `dashboard/leaderboard` aggregates token consumption
  over time windows — proves we can aggregate per-user usage cheaply.
- **No money code exists.** Grep for `stripe|usdt|payment|wallet` finds
  only unrelated 3D scene components and tokens-as-in-LLM-tokens. Green
  field.

**Implication:** we are not retrofitting billing onto an un-metered
system — the meter already runs. We are adding a *ledger*, *funding
rails*, and *pricing*.

---

## 3. Goals & non-goals

**Goals**

- A correct, auditable, append-only **credit ledger** — never lose or
  double-count money; balance is always `SUM(ledger)`.
- **Fund with test-USDT** end to end: deposit address → on-chain detect →
  credit, fully on **testnet**.
- **Fund with a card** via Stripe (fiat → credits) for users who don't
  want to touch crypto at all.
- **Meter and debit** real inference transparently, per modality.
- **Agents can pay autonomously** for `/v1` calls via x402.
- **Providers earn and can withdraw** test-USDT (Premium-gated).
- **Premium** subscription live via Stripe with clearly differentiated
  perks (§9).
- Keep crypto **custody risk near zero** in the testnet phase.

**Non-goals (this PRD)**

- Mainnet real money, KYC/AML, tax/1099, fiat bank withdrawals.
- On-chain escrow / smart contracts (we settle off-chain in our ledger;
  chain is only deposit + payout rails).
- Holding user funds as an investment / yield. We are a payment ledger,
  not a custodian-of-record.
- Price *discovery* / provider-set dynamic pricing (flat platform price
  table first; provider-set pricing is a fast-follow, §11).

---

## 4. Crypto choices, made simple (the decisions)

These are the only crypto decisions that matter; everything else
follows.

### 4.1 Which chain — **Base Sepolia (testnet) → Base (mainnet later)**

We need: cheap gas (micropayments), strong stablecoin support, great
tooling, and a clean agent-payments story. **Base** (Coinbase's Ethereum
L2) wins on all four, and its testnet is **Base Sepolia**.

> **USDT vs USDC note (important, read once):** the agent-payments
> standard we adopt (x402, §6) and most of Base's testnet tooling
> settle in **USDC**, the *other* major $1 stablecoin. USDT and USDC are
> interchangeable for our purposes (both ≈ $1). The pragmatic call:
> **our ledger is denominated in abstract "USD-cents credits"**, and we
> accept whichever $1 stablecoin a rail gives us — **USDC on the x402 /
> Base path, USDT on the manual-deposit path** (Base also has a testnet
> USDT). The user always sees "$" and "credits"; the stablecoin is an
> implementation detail of each rail. This sidesteps the single biggest
> beginner footgun (wrong-token-wrong-chain) while honoring the "USDT"
> ask wherever a USDT testnet token exists.

Concretely we hardcode, in settings, a `CHAINS` table:
`{ base-sepolia: { rpc, usd_tokens: {USDC: 0x…, USDT: 0x…}, explorer,
confirmations: 1 } }`. Switching to mainnet later = adding one row and a
feature flag, not a rewrite.

### 4.2 Custody — **"custodial-lite," one platform hot wallet**

The simplest correct model for testnet:

- inference.club holds **one platform wallet** (one keypair) on Base
  Sepolia. Its private key lives in a secret manager / env var (never in
  the repo, never in the DB). This is the **hot wallet**.
- **Deposits:** each user gets a **unique deposit memo/reference** (and,
  in v2, a unique derived deposit address). On testnet v1 we use a
  single platform address + a per-user `deposit_reference` the user is
  told to track; our indexer matches incoming transfers and credits by
  amount+time+reference, falling back to a manual admin match. (Per-user
  HD-derived addresses are the clean v2; see §11.)
- **Spending** is **off-chain**: debiting a user for an inference does
  **not** touch the chain — it's a `LedgerEntry`. Chain transactions
  happen only at **deposit** and **payout**. This is what makes
  micropayments viable (no gas per inference).
- **Payouts:** we send test-USDT *from* the platform wallet *to* the
  provider's self-custodied address. One on-chain tx per withdrawal.

This means: **we never custody mainnet value during this PRD** (testnet
funds are worthless), and the blast radius of a key leak is zero. The
exact same code paths, pointed at mainnet behind a flag, become the
real product later — but that flip is its own PRD with a security review.

### 4.3 How we touch the chain — a **library/provider, not raw nodes**

We do **not** run a blockchain node. Two clean options; pick one in §10:

- **viem/ethers (JS) or web3.py (Python)** against a hosted RPC
  (Alchemy/Infura free tier) — full control, a bit more code.
- **Coinbase's x402 + CDP SDK / facilitator** — handles the agent
  payment verification + settlement for us (recommended for the agent
  path, §6).

For deposit detection we either **poll** the RPC for `Transfer` logs to
our address every N seconds (a Celery beat task — Celery/Redis are
already deps) or subscribe to a webhook (Alchemy "Address Activity").
Polling is simplest and fine at our volume.

---

## 5. Data model (concrete)

All amounts are integers in **micro-USD** (1 USD = 1,000,000) to avoid
float drift; helpers convert to display "$1.23". Naming mirrors existing
`apps.inference` style (`BaseModel`, JSON metadata fields).

New app: **`apps.billing`** (keeps money code isolated, separately
testable, and out of the hot inference path except for the debit call).

```
Wallet (one per user)
  user            OneToOne(CustomUser)
  balance_micro   BigInteger  # DENORMALIZED cache of SUM(ledger); reconciled
  currency        char  default "USD"   # display currency; stablecoin abstracted away
  # invariant: balance_micro == SUM(LedgerEntry.amount_micro for this wallet)

LedgerEntry (append-only, NEVER updated/deleted)
  wallet          FK(Wallet, related_name="entries")
  amount_micro    BigInteger   # +credit / -debit, signed
  kind            enum: DEPOSIT_CRYPTO | DEPOSIT_STRIPE | INFERENCE_DEBIT
                       | PROVIDER_EARNING | PAYOUT | PLATFORM_FEE | ADJUSTMENT
                       | SUBSCRIPTION_CHARGE | REFUND | PROMO_CREDIT
  balance_after   BigInteger   # running balance snapshot for cheap statements/audit
  request         FK(InferenceRequest, null)   # set for INFERENCE_DEBIT / PROVIDER_EARNING
  deposit         FK(Deposit, null)
  payout          FK(Payout, null)
  idempotency_key char unique null   # dedupe webhook / on-chain replays
  memo            char
  metadata        JSON

Deposit (an inbound funding event)
  wallet          FK(Wallet)
  rail            enum: CRYPTO | STRIPE
  amount_micro    BigInteger
  status          enum: PENDING | CONFIRMED | CREDITED | FAILED
  # crypto-only:
  chain           char null        # "base-sepolia"
  token_symbol    char null        # "USDT" | "USDC"
  tx_hash         char null unique # the on-chain receipt id
  from_address    char null
  confirmations   int default 0
  # stripe-only:
  stripe_payment_intent  char null unique
  metadata        JSON

Payout (an outbound withdrawal to a provider's own address)
  wallet          FK(Wallet)
  amount_micro    BigInteger
  to_address      char            # provider's self-custodied USDT address
  chain           char            # "base-sepolia"
  token_symbol    char
  status          enum: REQUESTED | SENT | CONFIRMED | FAILED
  tx_hash         char null unique
  fee_micro       BigInteger default 0
  requested_at / sent_at / confirmed_at
  metadata        JSON

PriceBook (platform price table; one active row per (modality, unit))
  modality        enum mirrors ProviderService.service_type: llm|stt|tts|image
  unit            enum: PER_1K_PROMPT_TOK | PER_1K_COMPLETION_TOK
                       | PER_AUDIO_MINUTE | PER_IMAGE | PER_REQUEST
  price_micro     BigInteger      # micro-USD per unit
  provider_share_bps int default 7000   # 70% to provider, 30% platform (basis points)
  is_active       bool
  effective_from  datetime

Subscription (inference.club Premium)
  user            OneToOne(CustomUser)
  plan            enum: FREE | PREMIUM | PRO          # FREE = no row needed; default
  status          enum: ACTIVE | PAST_DUE | CANCELED | TRIALING
  stripe_customer_id / stripe_subscription_id  char
  current_period_end  datetime
  cancel_at_period_end bool
  metadata        JSON
```

**On `CustomUser`** add only thin pointers (keep money in `billing`):
- `payout_address` (char, blank) — provider's self-custodied USDT addr.
- a `@property plan` that reads `Subscription` (FREE if none).

**Why a ledger and not a single `balance` column?** Money bugs are
unforgivable. Append-only double-entry means every cent is traceable to
a cause, balance is reconstructable, and replays/webhooks can't
double-credit (idempotency_key). The `balance_micro` cache is an
optimization we *verify* against `SUM(entries)` in tests and a nightly
reconcile task.

---

## 6. Agent-native payments — **x402** (the headline feature)

This is what makes inference.club interesting in an agentic world: **an
AI agent can pay for an inference call by itself, no human, no
pre-funded account, in one HTTP round-trip.**

**What x402 is, plainly:** an open standard (originated by Coinbase) that
revives the dormant HTTP status code **`402 Payment Required`**. The flow:

```
1. Agent calls   POST /v1/chat/completions   (no payment yet)
2. Server replies 402 + a JSON "payment requirements" body:
   { amount, asset: USDC, chain: base-sepolia, payTo: <platform addr>, ... }
3. Agent's wallet signs a payment authorization and retries the SAME
   request with an  `X-PAYMENT`  header.
4. A "facilitator" (Coinbase's hosted one, or self-run) verifies +
   settles the stablecoin transfer on-chain.
5. Server runs the inference and returns 200 + the completion, plus an
   `X-PAYMENT-RESPONSE` header (the receipt / tx hash).
```

**Why it fits inference.club perfectly:** our `/v1/...` endpoints are
already the paywall boundary, and pricing is per-request off fields we
already compute. x402 is literally "402 in front of an HTTP API," which
is exactly our shape.

**Two payment modes we support (user/agent picks):**

- **Prepaid balance (default, cheapest):** user/agent tops up once
  (crypto or Stripe), then each call is an off-chain `INFERENCE_DEBIT`.
  No per-call chain tx, no per-call gas. Best for high volume.
- **x402 pay-per-call (no account):** for agents that hold a wallet and
  want zero setup — each call settles on-chain via x402. We still write a
  `Deposit`(rail=CRYPTO) + immediate `INFERENCE_DEBIT` so the ledger
  stays the single source of truth. Higher per-call overhead; ultimate
  convenience.

**Implementation note:** wrap `/v1/...` with x402 middleware. There are
maintained server middlewares (e.g. `x402` packages for Express/FastAPI)
and a Coinbase-hosted **facilitator** that does verify+settle, so we
don't write chain-signature code ourselves. On testnet the facilitator
points at Base Sepolia. If a request arrives **with** a valid prepaid
balance or platform API key, we **skip** the 402 and bill the balance —
402 is the fallback for un-funded callers.

> Alternatives considered: **L402** (Lightning-based, from Lightning
> Labs — great but pulls in Lightning infra and is BTC/sats, not USDT);
> **Google AP2 / Agent Payments Protocol** (broader mandate framework,
> heavier, worth tracking for v2). **x402 is the lowest-friction match
> for a stablecoin-on-an-HTTP-API product** and is what we build first.

---

## 7. Funding, spending, payout — the three flows

### 7.1 Top-up with crypto (testnet)
1. User opens **Dashboard → Billing → Add funds → Crypto**.
2. We show: the platform deposit **address** (QR), the **chain**
   (Base Sepolia), the **token** (test-USDT/USDC), a **`deposit_reference`**,
   and a link to a **faucet** to get free test-USDT first.
3. User sends test-USDT from their wallet.
4. Celery beat **indexer** (poll RPC `Transfer` logs to our address every
   ~15s) detects the tx → creates `Deposit(PENDING)` → on N confirmations
   → `CONFIRMED` → writes `LedgerEntry(DEPOSIT_CRYPTO, idempotency=tx_hash)`
   → `CREDITED`, balance updated. UI shows it live (poll/SSE).

### 7.2 Top-up with a card (Stripe, no crypto for the user)
1. **Billing → Add funds → Card** → enter amount → **Stripe Checkout**.
2. On success, Stripe **webhook** (`payment_intent.succeeded`) →
   `Deposit(rail=STRIPE, idempotency=payment_intent)` →
   `LedgerEntry(DEPOSIT_STRIPE)`. User now has credits without ever
   seeing a blockchain. (This is most users.)

### 7.3 Spending (metered debit) — the hot path
- After an `InferenceRequest` reaches `status=success` and token/audio/
  image counts are known, a **`bill_request(request)`** function:
  1. Looks up active `PriceBook` rows for the request's modality.
  2. Computes `cost_micro` from `prompt_tokens`/`completion_tokens` (LLM),
     `audio_seconds` (STT/TTS), or `image_count` (image).
  3. Writes **two** ledger entries atomically (double-entry):
     `INFERENCE_DEBIT` on the **consumer** wallet (−cost), and
     `PROVIDER_EARNING` on the **provider** wallet
     (+cost × `provider_share_bps`), plus a `PLATFORM_FEE` line for the
     remainder. All share an `idempotency_key = f"bill:{request.id}"` so
     a retry can't double-bill.
- **Pre-flight guard:** before routing, if the consumer's
  `balance_micro` ≤ 0 **and** they have no x402 payment **and** they're
  not on an allowance plan → reject with `402` (prepaid) or the x402
  challenge (agent). Cheap check on the denormalized balance.
- **Failure handling:** failed/aborted requests are **not** billed
  (status gate). Partial streams bill on tokens actually produced.

### 7.4 Provider payout (Premium-gated, §9)
1. Provider sets `payout_address` (their own wallet) in Settings.
2. **Billing → Withdraw** (visible only if `plan != FREE` and balance ≥
   min). Enter amount → `Payout(REQUESTED)`.
3. A worker sends test-USDT platform-wallet → `payout_address`, records
   `tx_hash`, writes `LedgerEntry(PAYOUT, −amount)`; on confirmation →
   `CONFIRMED`. Min-withdrawal + cooldown to bound tx-fee waste.

---

## 8. Pricing model (transparent, flat to start)

- **One platform price table** (`PriceBook`), shown publicly on a
  `/pricing` page and in the docs. Example launch numbers (illustrative,
  tune later):
  - LLM: `$0.50 / 1M prompt tok`, `$1.50 / 1M completion tok`.
  - STT: `$0.006 / audio-minute`. TTS: `$15 / 1M chars` (or per-second).
  - Image: `$0.01 / image`.
- **Revenue split:** `provider_share_bps` (default **70% provider / 30%
  platform**). Surfaced to providers as "you earn ~70% of what consumers
  pay for requests you serve."
- **Free tier:** every user gets a small recurring **`PROMO_CREDIT`**
  (e.g. $1/mo testnet) so the product is usable with zero setup; this
  also seeds the demo.
- Provider-**set** pricing (a provider charging a premium for a scarce
  big model on an H100) is a **fast-follow** (§11), not v1.

---

## 9. inference.club **Premium** (the subscription)

Billed in **fiat via Stripe** (recurring), because subscriptions are a
card-native UX and Stripe handles dunning/proration/invoices for us.
(Crypto-paid subscription is a v2 nicety.) Plans:

| Capability | **Free** | **Premium** | **Pro** |
|---|---|---|---|
| Use the proxy / playground | ✅ | ✅ | ✅ |
| Monthly promo credits | small | larger | largest |
| **Rate limits** (req/min, concurrent) | low | high | highest |
| **Priority routing** (queue position, prefer faster providers) | — | ✅ | ✅ + reserved hints |
| **Dedicated / reserved capacity** hint to router | — | — | ✅ (provider opt-in pools) |
| Longer **context / larger models** allowed | capped | raised | max |
| Higher per-request **token caps** | low | high | max |
| **Support** | community | email | priority/SLA |
| **Provider payout eligibility** (withdraw earnings) | ❌ | ✅ | ✅ |
| Lower **platform fee** on earnings (better split) | 70% | 75% | 80% |
| Advanced **usage analytics / exports** | basic | full | full + API |
| Custom **API key prefix**, multiple keys | — | ✅ | ✅ |

**Key design tie to crypto:** **payout eligibility is a Premium perk.**
Free providers can *earn* credits (and spend them on inference), but
**withdrawing to an external wallet requires Premium+**. Rationale: it
gates the one action with real fraud/compliance surface behind a
verified, paying relationship, and gives providers a concrete reason to
subscribe. The better revenue split for higher tiers is the carrot.

**Enforcement points (all cheap):**
- Rate limits / concurrency → DRF throttle classes keyed on `user.plan`.
- Token / context caps → checked in the `/v1` request validator.
- Priority routing → router sorts candidate providers; Premium requests
  get a lower queue key / prefer-faster weighting (ties into the
  deferred routing work in MVP-scope memory).
- Payout button → gated on `plan != FREE` (§7.4).
- Earning split → `provider_share_bps` overridden by the provider's plan.

**Webhooks:** Stripe `customer.subscription.*` events keep
`Subscription.status` / `current_period_end` in sync; a nightly task
downgrades expired subs to FREE.

---

## 10. Open questions / decisions

1. **Chain:** confirm **Base Sepolia** (recommended) vs Polygon Amoy
   (also cheap; USDT more native) vs Ethereum Sepolia (most "standard,"
   pricier gas). *Recommendation: Base Sepolia for the x402 synergy.*
2. **USDT vs USDC** on the manual-deposit rail — accept both, display
   "$"? *Recommendation: yes (§4.1).*
3. **Chain library:** `web3.py` in Django (one language) vs a small Node
   sidecar using viem + the official x402 middleware (best x402
   support). *Recommendation: Node sidecar for x402 + `web3.py` polling
   for deposits — or all-Node x402 gateway in front of `/v1`.*
4. **x402 facilitator:** Coinbase-hosted (fastest) vs self-hosted
   (no third-party dependency). *Start hosted on testnet.*
5. **Per-user deposit addresses (HD wallet)** now or in v2? *v2 — v1
   uses one address + reference + admin match to ship fast.*
6. **Pricing numbers** and the **70/30** split — Brian to set.
7. **Premium price points** ($/mo) and trial length — Brian to set.
8. **Refunds policy** for Stripe top-ups (credits are spent on
   third-party GPU work) — likely "credits non-refundable once spent."

---

## 11. Phasing (suggested implementation order)

- **Phase 0 — Ledger core (no chain, no Stripe).** `apps.billing`,
  `Wallet`/`LedgerEntry`/`PriceBook`, `bill_request()` wired into the
  request lifecycle, balance pre-flight guard, admin `ADJUSTMENT` to
  grant test credits, `/pricing` page, Billing dashboard showing balance
  + statement. **Fully testable with zero crypto.** *Highest value,
  lowest risk — do this first.*
- **Phase 1 — Stripe top-up + Premium.** Stripe Checkout for credits,
  `Subscription` + webhooks, plan-based throttles/caps, payout button
  *gated but disabled*. Real revenue path that touches no blockchain.
- **Phase 2 — Crypto deposits (testnet).** Platform wallet, deposit
  page + faucet link, Celery indexer, `Deposit`/credit flow on Base
  Sepolia.
- **Phase 3 — Provider payout (testnet).** `payout_address`, `Payout`
  flow, min/cooldown, Premium gate enforced.
- **Phase 4 — x402 agent payments.** 402 middleware on `/v1`,
  facilitator wiring, `X-PAYMENT` handling, docs + a runnable agent
  example.
- **Phase 5 (separate PRD) — Mainnet go-live.** Security review, HD
  deposit addresses, KYC/limits, real-money flag. **Not in this PRD.**

---

## 12. Acceptance criteria (high level)

- `balance_micro` **always** equals `SUM(LedgerEntry.amount_micro)` for
  every wallet (property-tested + nightly reconcile job).
- No code path can **double-credit** a deposit or **double-bill** a
  request (idempotency keys enforced by unique constraints; tests fire
  duplicate webhooks / replayed tx hashes).
- A successful LLM/STT/TTS/image request writes exactly the right
  debit + provider-earning + platform-fee triple; a **failed** request
  writes **none**.
- A user with $0 and no x402 gets a clean `402` (or x402 challenge), not
  a 500 and not a free inference.
- Stripe top-up of $X credits exactly `$X` (minus declared fees) and is
  idempotent across webhook retries.
- On testnet: sending test-USDT to the deposit address credits the
  correct wallet within one indexer cycle; withdrawing sends a real
  on-chain testnet tx whose hash resolves on the explorer.
- An external agent example completes a paid `/v1/chat/completions` via
  x402 against testnet with no pre-existing account.
- Premium gates verified: Free user **cannot** withdraw; Premium can;
  plan changes flip throttles within one request.

---

## 13. UX notes

- **Money is scary — over-communicate.** Every debit links to its
  request; every request detail shows "you paid $0.0014 (X prompt + Y
  completion tok)". Statements are downloadable CSV.
- **Crypto is optional and clearly labeled "testnet — not real money"**
  with a faucet link, so a non-crypto user never has to engage with it.
- Balance + low-balance warning live in the `TopBar` for signed-in
  users; an auto-topup toggle (Stripe) is a nice fast-follow.
- Provider earnings get their own card on the dashboard ("earned this
  month, available to withdraw") next to the existing leaderboard.
- All amounts via one `formatUsd(micro)` helper; never render raw micros.

---

## 14. Security & correctness guardrails

- **Private keys** for the platform wallet live in a secret manager / env
  only; never in DB, repo, logs, or client. Separate testnet vs mainnet
  keys; mainnet key only introduced in Phase 5 behind review.
- All ledger writes inside `transaction.atomic()`; `select_for_update`
  on the wallet row to serialize concurrent debits.
- Idempotency keys are **unique DB constraints**, not app-level checks.
- Webhooks verify Stripe signatures; on-chain credits require N
  confirmations and re-org handling (mark `Deposit` reversible until
  final).
- Rate-limit the deposit-address and withdraw endpoints; withdraw needs
  re-auth + min/cooldown + (later) email/2FA confirm.
- A read-only **`/billing/audit`** admin view and a nightly reconcile
  task that alerts if any `balance_micro != SUM(entries)`.

---

## 15. Touch list (for implementation)

**Backend (`backend/`)**
- New app `apps/billing/`: `models.py` (Wallet, LedgerEntry, Deposit,
  Payout, PriceBook, Subscription), `services.py`
  (`bill_request`, `credit_deposit`, `request_payout`,
  `apply_subscription_event`), `pricing.py`, `chain.py` (RPC/indexer),
  `stripe_webhooks.py`, `x402.py` (middleware/gateway), `admin.py`,
  `tests/`.
- `apps/inference`: call `bill_request()` post-success in the request
  lifecycle; add balance pre-flight to the `/v1` views; throttle classes
  keyed on plan; token/context caps in validators.
- `apps/accounts`: add `payout_address` + `plan` property to
  `CustomUser`; migration.
- Settings: `CHAINS` table, `STRIPE_*`, `X402_*`, platform-wallet secret
  refs, Celery beat entries (indexer, reconcile, sub-expiry).
- URLs/serializers: `/api/billing/wallet`, `/statement`, `/deposit`,
  `/withdraw`, `/pricing`, `/subscription` (+ Stripe/x402 webhook routes).

**Frontend (`frontend/`)**
- `pages/dashboard/billing/` (balance, statement, add-funds [card|crypto],
  withdraw, earnings), `pages/pricing.vue`, `pages/dashboard/settings`
  (plan + payout address), upgrade/Premium page.
- `composables/useBilling.ts`, `useSubscription.ts`; `formatUsd` util;
  TopBar balance widget; per-request cost line on request detail/cards.
- i18n strings for all of the above (per PRD 02 patterns).

**Infra (`infra/`)**
- Secrets for Stripe + platform wallet; optional Node x402 sidecar
  service in compose/Caddy; Alchemy/Infura RPC URL config.

**Docs**
- `/docs` pages: "Paying for inference," "Paying as an agent (x402),"
  "Earning & withdrawing," "Premium."
```
