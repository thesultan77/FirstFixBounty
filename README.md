# FirstFixBounty

**Open, Race-Safe Bug Bounty with First-Valid-Fix-Wins on GenLayer**

A bug bounty where anyone — not a single pre-assigned worker — can race to
submit a fix. The first submission an on-chain LLM verifies as genuinely
resolving the bug wins the entire pool; every submission after that is
automatically rejected, with no special concurrency handling required.

---

## What it does

1. A poster **funds a bug bounty** with a description of the bug and a
   reference URL (the buggy content/context the fix needs to address).
2. **Anyone** can submit a fix URL at any time — this is an open board, not
   assigned to one pre-chosen worker.
3. Each submission is checked immediately: the contract fetches both the
   reference content and the submitted fix content, and asks an LLM whether
   the fix genuinely and correctly resolves the described bug.
   GenLayer's validator consensus (`gl.eq_principle.prompt_comparative`)
   ensures multiple independent LLM runs agree on the categorical
   `VALID_FIX`/`INVALID_FIX` verdict before it's accepted on-chain.
4. The **first submission verified as `VALID_FIX` wins the entire pool**
   immediately, and the bounty closes. Every submission after that —
   even one sent moments later — is rejected outright, since the bounty
   is no longer open.
5. Safety exits: the poster can **cancel** before any fix is submitted, and
   anyone can trigger a **timeout refund** if the deadline passes with no
   valid fix found.

## Why this is different

Every other bounty/escrow contract in this series (TaskMatchEscrow,
ReputationTaskMatch, QualityScoredBounty) assigns the work to one specific,
pre-chosen address before anything happens — a 1:1 agreement. FirstFixBounty
is a genuinely open board: anyone can attempt a fix, submissions can arrive
concurrently from different people, and the contract has to resolve that
race deterministically and safely. This works without any special locking
logic because GenLayer transactions execute sequentially in consensus
order — a single `assert status == "OPEN"` at the top of `submit_fix` is
all that's needed. Whichever valid fix lands first flips the bounty to
`CLOSED`; anything ordered after that simply fails the assert and is
rejected, with no risk of double-paying the pool.

## Architecture

| Concern | Mechanism |
|---|---|
| Bounty state | Parallel `TreeMap[str, ...]` fields per bounty ID (poster, description, repo URL, pool, status, winner, winning fix URL, reasoning, attempt count, deadline) |
| Race safety | A single `status == "OPEN"` check at the top of `submit_fix`, relying on GenLayer's sequential transaction ordering — no explicit locking needed |
| AI verification | `gl.nondet.web.render` fetches both the reference and the fix content; `gl.nondet.exec_prompt` inside a closure, reconciled across validators via `gl.eq_principle.prompt_comparative` |
| Output safety | Verifier output is validated (JSON parse, structure, field presence, type, and domain of the `verdict` field) before any state mutation or fund transfer |
| Fund safety | Funds only move once, to the first `VALID_FIX` submitter, or via `cancel_bug` (before any fix submitted) or `claim_timeout_refund` (deadline passed, still open) |

No address-taking parameters are needed anywhere in this contract — the
poster and winner are both captured directly from `gl.message.sender_address`
at the moment of the relevant transaction, avoiding the raw-int-parameter
storage issue that affects `Address`-typed method parameters elsewhere in
this series.

## Contract methods

### Write

- **`post_bug(bug_description: str, repo_url: str, minutes_until_deadline: int) -> str`** *(payable)*
  Poster funds the bounty pool. Returns the new `bounty_id` (e.g. `"F0"`).
- **`submit_fix(bounty_id: str, fix_url: str) -> str`**
  Anyone can attempt a fix. Triggers AI verification and validator
  consensus. If `VALID_FIX`, the caller wins the pool immediately and the
  bounty closes; if `INVALID_FIX`, nothing happens except the attempt being
  logged — the bounty stays open for further attempts.
- **`cancel_bug(bounty_id: str)`**
  Poster reclaims the full pool, but only before any fix has been
  submitted.
- **`claim_timeout_refund(bounty_id: str)`**
  Anyone can trigger a full refund to the poster once the deadline has
  passed with no valid fix accepted.

### View

- **`get_bounty(bounty_id: str) -> dict`**
  Full current state of a bounty (poster, description, URLs, pool, status,
  winner, winning fix URL, reasoning, attempt count, deadline).
- **`get_bounty_count() -> int`**

## Tested end-to-end in GenLayer Studio

- `post_bug` confirmed funding a bounty (2 GEN) describing a bug in a
  reference Gist missing a specific fact, returning `"F0"`.
- `submit_fix` with an unrelated, clearly-wrong fix correctly returned
  **`"INVALID_FIX - ..."`**, with the bounty remaining open and no funds
  moved, `FINALIZED`/`SUCCESS`.
- `submit_fix` with a genuine, correct fix correctly returned
  **`"VALID_FIX - you won the bounty, paid 2000000000000000000 wei"`**,
  with full validator consensus on the verdict, `FINALIZED`/`SUCCESS`.
- A third `submit_fix` call, sent after the bounty had already closed,
  correctly **failed** with `"Bounty already closed - a valid fix was
  already accepted, or it was cancelled/timed out"` — confirming the
  race-safety lock works and a closed bounty cannot pay out twice.
- `get_bounty` confirmed final state: `status: "CLOSED"`, `winner` matching
  the correct address, `attempt_count: "2"` (the two submissions that
  actually reached the verification logic; the third, rejected-at-the-door
  attempt never incremented the counter).

## Deployment

```
# v0.2.16
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
```

No VecDB/embeddings dependency needed for this contract. Constructor takes
no arguments. Deploy directly in GenLayer Studio or via `genlayer-js`
against Studionet / Bradbury testnet.

## Notes on GenVM quirks discovered while building this

- GenLayer transactions execute sequentially in consensus order, so a
  plain `assert status == "OPEN"` at the top of a write method is
  sufficient to make "first valid submission wins" race-safe — no special
  locking, nonce, or ordering logic is needed beyond relying on the
  platform's own sequential execution.
- Avoiding `Address`-typed method parameters entirely (by only ever
  capturing addresses from `gl.message.sender_address` rather than
  accepting one as an argument) sidesteps the raw-int-parameter storage
  issue found in earlier contracts in this series, simplifying the code
  with no workaround needed.

## Notes on design decisions

- The verifier's output is validated (JSON structure, field presence,
  type, and domain of the `verdict` field) before any state change or fund
  transfer — the same safety pattern applied proactively across every
  contract in this series after it was flagged as a required fix on an
  earlier contract (SemanticDisputeRouter).
- Rejected (`INVALID_FIX`) submissions cost the submitter nothing extra
  beyond the gas of the attempt — there's no stake-per-submission — which
  keeps the "race to fix" mechanic open and low-friction rather than
  requiring submitters to risk funds on an unverified attempt.

## License

MIT
