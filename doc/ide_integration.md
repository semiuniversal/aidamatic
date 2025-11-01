# IDE Integration Plan (VS Code, Cursor, Copilot)

## Goals
- Let a single user (admin PM) operate primarily in Taiga; Dev/AI work locally via the IDE.
- No separate web portal. Use the local AIDA Bridge (HTTP + CLI) as the single integration API.
- Keep the AI agent deterministic: reflect progress to Taiga (comments/status), never self-switch tasks without confirmation.

## Core UX (VS Code Extension)
- Status Bar: “AIDA: (ref) subject”
  - Actions: Take next (confirm), Post comment…, Set status…, Open in Taiga
- Command Palette (AIDA: …)
  - AIDA: Take next (confirm → select)
  - AIDA: Current task (shows title/ref/status)
  - AIDA: Post comment… → Bridge /task/comment
  - AIDA: Set status… (in_progress/review/done/blocked) → Bridge /task/status
  - AIDA: Sync outbox → Bridge /sync/outbox
  - AIDA: Add doc (text/file) → Bridge /docs, /docs/upload
- Sidebar (TreeView/Webview)
  - Current Task: title/ref/status, acceptance criteria, attachments
  - Docs: list with tags, open-in-editor; add file/text actions
  - Buttons: Take next (confirm), Post comment, Set status

Notes:
- Extension reads `.aida/assignment.json` and calls the Bridge. If Bridge is down, show “Run aida-start”.
- Confirmations: “Take next” always prompts; if none, show guidance and an “Open in Taiga” button.

## Chat-aware Patterns
- Preferred: keep source-of-truth in Taiga. Use Bridge only for comments/status.
- Chat commands (where supported): `/aida next`, `/aida status done`, `/aida comment …` → call Bridge.
- Prompt Composer: a small panel that assembles a context-rich prompt (current task + AC + docs) with a “Copy to Chat” button. Works with Copilot/Cursor without native chat hooks.
- Optional Chat Participant (VS Code Chat API): prepend “AIDA rules” (Definition of Ready/Done, AC echo, ask questions via Taiga) before sending.

## Cursor / MCP Adapter
- Ship an MCP server that wraps Bridge endpoints as tools:
  - task_current, task_next, task_comment, task_status, docs_add, docs_list, sync_outbox
- Cursor connects via MCP to “see” assignments and post comments/status deterministically.
- Still rely on Bridge as the only API; MCP is just an adapter.

## Bridge Endpoints Mapping
- Current
  - GET /health
  - GET /projects (scoped)
  - GET /task/current
  - POST /task/comment
  - POST /task/status
  - GET /task/history
  - POST /sync/outbox (dry_run)
  - Docs: POST /docs, POST /docs/upload, GET /docs
  - Chat (local notes): POST /chat/send, GET /chat/thread
  - Suggest next: GET /task/next (safe suggestion; no selection)
- Near-term additions
  - GET /task/details (full item payload + attachments)
  - POST /task/select (select an item by id/ref) – avoids direct file writes
  - POST /task/next/select?confirm=true – optional “suggest + select” with policy idempotency

## Profiles & Security
- Profiles: `developer` (active CLI), `scrum` (Bridge sync identity). Stored in `.aida/auth.<profile>.json`.
- The extension doesn’t store secrets; it uses the local Bridge and `.aida/*` files.
- Localhost only; no external exposure.

## Workflow (Happy Path)
1) PM prepares stories/bugs in Taiga; marks as Ready.
2) Dev clicks “AIDA: Take next” in VS Code → confirm → selected (assignment saved).
3) Dev opens “Prompt Composer” → copies context prompt to chat → AI begins work.
4) AI posts questions/status via Bridge → Taiga updates visible to PM.
5) Dev moves to “review/done” when AC met; PM accepts in Taiga.

## Error Handling & Guardrails
- No project selected → prompt to run `aida-task-select` or use “Take next”.
- No next item → clear message + “Open project in Taiga”.
- Identity drift → refuse silent switches; show “run aida-taiga-auth --profile …”.
- Bridge down → show quick fix (“aida-start”) with link to README.

## Minimal Extension Surface (v1)
- Commands:
  - AIDA: Take next
  - AIDA: Current task
  - AIDA: Post comment
  - AIDA: Set status
  - AIDA: Add doc (text/file)
  - AIDA: Sync outbox
- Status Bar: current task summary + dropdown
- Sidebar: Current task + Docs list

## Acceptance Criteria (v1)
- One-click “Take next” with confirmation chooses the same item as `aida-task-next`.
- Post comment/Set status reflect in Taiga within seconds (after sync or immediate if desired).
- Docs add/list works locally and appears in the panel.
- If no next item, user is guided to Taiga.

## Risks & Mitigations
- Chat UI constraints: use prompt composer + chat commands; avoid invasive UI hacks.
- Provider differences (Cursor/Copilot): keep everything behind Bridge/MCP; extension is thin.
- Identity confusion: profiles and explicit activation; Bridge runs under `scrum` by default.

## Next Steps
- Add Bridge: GET `/task/details`, POST `/task/select`.
- Scaffold VS Code extension (status bar, commands, sidebar) calling Bridge.
- MCP server wrapper for Bridge tools (optional for Cursor).
- Document prompt composer and chat command patterns.

