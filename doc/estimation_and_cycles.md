### Estimation, Sizing, and Focus Cycles (AIDA)

This guide defines how we size work and run short, Kanban-friendly “focus cycles” for AI-enabled development. It optimizes for fast flow, minimal overhead, and clear gates.

#### Principles
- Prefer flow metrics over time estimates (lead time, throughput, WIP).
- Use effort/complexity signals instead of hours. Reserve points for truly non-trivial work.
- Keep human-in-the-loop gates for acceptance criteria (AC) and risky items.
- The Scrum Master agent plans and enforces; developer agent advises (no authority).

#### Estimation Policy (time‑free)
- No hour estimates. Do not convert work into hours/minutes.
- Effort bucket (required on every candidate):
  - micro: micro change (often < ~1h) → no points
  - small: simple change, low risk
  - medium: non-trivial change or moderate risk
  - large: cross-cutting or high risk
- Feasibility and risk (required):
  - feasibility: trivial | straightforward | non_trivial | risky
  - risks: short bullets
  - deps: ids/links
- Story points (optional): only for non_trivial/risky items to aid prioritization (1,2,3,5,8).
- Spikes: label as spike with a timebox (e.g., 30–60 min); deliverable is a decision or notes, not code.

#### Gates (Scrum Master grooming rules)
- DoR validation: template complete, testable AC, links/attachments present.
- If feasibility ∈ {non_trivial, risky} or points ≥ 3 → PM approval required before publish.
- Micro/small items can skip points if AC is clear and DoR passes.
- DoD validation on completion: acceptance criteria mapping (pass/fail + evidence).

#### Kanban + Focus Cycles
- Board: Ready → In Progress → Review → Done (+ Blocked). Enforce small WIP (1–2 per person/agent).
- Focus cycles (optional overlay): short timeboxes (5–60 min) to create phasing without Scrum overhead.
  - Cycle fields: id/name, start/end timestamps, explicit scope (in/out), close summary.
  - Representation in Taiga: tags `cycle:<id>` (simple) or ephemeral milestone per cycle.
  - Local state (kept under version control boundaries, not committed): `.aida/cycle.json`, `.aida/scope.json`.

#### Grooming Mode (Scrum Master)
- Inputs: curated docs in `.aida/docs/`, current scope/cycle, backlog, developer feedback.
- Propose: draft story candidates as strict JSON (title, value, AC[], tech notes, risks, deps, effort_bucket, feasibility, optional points/spike_timebox).
- Review: run DoR checks; de-duplicate; order by value/effort; flag blockers.
- Approve: PM edits/approves AC; only then publish to Taiga.

#### Conversation & Artifacts
- Chat lives in the AIDA Bridge (/chat endpoints) and `.aida/chat.jsonl`.
- Docs are opt‑in: `.aida/docs/` files + `docs.jsonl` manifest (tags: brief, architecture, risk, etc.).
- Outbox events: `.aida/outbox/*.json` store comment/status actions before push.

#### Metrics & WIP
- Track lead time (Ready→Done) and throughput (Done per cycle/day) from statuses.
- Enforce WIP limits; prefer swapping items to “adding more.”
- Use metrics for feedback loops, not as performance targets.

#### When to use points
- Only apply points for items that are non_trivial or risky.
- Points inform priority (value/effort), not scheduling. The clock is the cycle.

#### Spikes
- Timebox: 30–60 min; outcome is decision notes, not code.
- Convert into concrete stories with AC if the spike confirms a path.

#### Summary
- Flow-first: Kanban with optional focus cycles.
- Time-free sizing: effort bucket + feasibility/risk; points only when justified.
- Strong gates: DoR before publish; DoD with AC evidence at completion.
- Local, explicit context: docs and chats are opt‑in and stored under `.aida/`.
