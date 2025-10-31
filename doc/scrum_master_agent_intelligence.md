### Scrum Master Agent Intelligence: Options & Recommendations

#### Overview
A hybrid approach best fits AIDA: a deterministic rules engine for process enforcement, paired with an LLM for judgment (classification, extraction, drafting). Start with a single cloud LLM and direct HTTP integrations; introduce MCP later if/when multi-tool interoperability becomes a priority.

#### Requirements (from AIDA goals)
- Validate artifacts against strict templates (DoR/DoD), extract acceptance criteria, summarize.
- Decide next action (nudge, escalate, prompt AI dev, ask PM, do nothing).
- Draft concise, templated communications to Taiga.
- Maintain memory of story history, avoid drift, detect duplicates.
- Operate safely: structured outputs, no secrets leakage, auditable trail.

#### Architecture Options
- Option A — Deterministic envelope + single cloud LLM (no MCP)
  - Pros: simplest to ship; fewer moving parts; direct Taiga/HTTP clients; low ops.
  - Cons: tool contracts are app-specific; less interoperable.
  - When: Phase 1 (recommended start).
- Option B — Deterministic envelope + thin MCP server (taiga.*, git.*, files.*, memory.*)
  - Pros: standard tool contracts; enables MCP-capable clients/agents; clearer separation of concerns.
  - Cons: adds plumbing/maintenance; versioning tool schemas.
  - When: Phase 2, once interop benefits outweigh complexity.
- Option C — Multi-agent hub with MCP-first design
  - Pros: future-proof for complex workflows; plug-and-play toolchain.
  - Cons: highest complexity/overhead; premature for v1.
  - When: Only if multi-agent orchestration is a near-term requirement.

#### LLM Service Options
- Cloud primary
  - Anthropic Claude 3.7 Sonnet: strong tool-use and reasoning; good for JSON-constrained outputs.
  - OpenAI (o4/4.1/4o-mini): robust tool calling; wide ecosystem support.
  - Azure OpenAI: enterprise controls, regional/data options.
- Local fallback (later)
  - Llama 3.1 70B/405B via vLLM, or Mistral Large local serving.
- Recommendation: pick one primary + one fallback behind a provider abstraction (env-configurable).

#### Tools & Services (minimal → robust)
- Core integrations: Taiga REST/Webhooks; LLM API; SQLite/Postgres for state; filesystem/repo for artifacts.
- Helpful next: vector memory (Chroma/SQLite FTS/PG-Vector) for story history; scheduler/cron for nudges; telemetry (OpenTelemetry) for audit; secrets management (`.env` → vault later).

#### Prompting Strategy
- Global system prompt (role + norms)
  - Role: Scrum Master Agent with dual mandate (facilitator + enforcer).
  - Norms: Validate templates, enforce DoR/DoD, never invent facts, ask PM if uncertain, produce strict JSON for machine steps and concise natural-language for Taiga.
- Module prompts (separate, few-shot, JSON-first)
  - StoryValidator → {missing_fields[], red_flags[], normalized_summary}
  - ActionSelector → {action: enum[prompt_ai_dev|ask_pm|nudge|escalate|do_nothing], rationale_brief}
  - CommunicationDraft → {comment_body, audience: enum[ai_dev|pm], max_len}
  - DoDChecker → {criteria: [{text, pass: bool, evidence}], overall_pass}
  - FeedbackRouter → {classification, extracted_requests[], next_action}
- Parameters: low temperature (0.2–0.4), small max tokens, JSON schema enforcement with retries.

#### Guardrails & Reliability
- Deterministic rules gate all status transitions, timeouts, and escalations.
- Strict schema validation of LLM outputs; auto-repair prompts on format errors.
- Idempotency via content hashing to avoid duplicate comments.
- Cost/latency control: cache summaries, reuse embeddings, keep prompts short.
- Privacy: redact secrets from prompts and logs.

#### Phased Plan
- Phase 1 (ship fast): Option A; cloud LLM; direct Taiga client; SQLite; simple scheduler; implement StoryValidator, ActionSelector, CommunicationDraft, DoDChecker.
- Phase 2 (scale/interop): add vector memory; introduce thin MCP server for taiga/git/files/memory; optional multi-LLM routing.
- Phase 3 (resilience): local LLM fallback; queue-based workers; richer observability and SLOs.

#### Risks & Mitigations
- Vendor lock-in → provider abstraction + dual-provider support.
- Hallucinations → strict schemas, low temperature, deterministic envelope.
- Cost/latency → caching, prompt discipline, streaming when applicable.
- Process drift → prompt unit tests and golden transcripts for regression.

#### Decision Summary (Recommended Path)
- Start with Option A (deterministic + single cloud LLM, no MCP), add Option B (thin MCP) when interop or external agent tooling becomes valuable.
- Choose one primary LLM (Anthropic or OpenAI) with a configurable fallback.
- Use JSON-first modular prompts, with a rules engine to enforce process and quality.

#### Open Questions
- Preferred LLM provider(s) and data/region constraints?
- Is MCP interoperability needed soon, or acceptable in Phase 2?
- Should task decomposition stay human-driven (PM) or allow limited auto-decomposition by the agent?
