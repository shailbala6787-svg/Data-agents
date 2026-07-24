# Roadmap

## Phase 0 — Foundation (this PR)
[ ] Fix spec → code drift: baseline is a text-transformer; this repo is the UP Police data analyst
[ ] Plug Ollama provider into LLM layer (replace Anthropic/Gemini/OpenRouter as required defaults)
[ ] Extend AgentState (transient space → persistent workspace with CSVs + DB profile)
[ ] Rewrite graph: plan → execute → format (supervisor-like multi-step with optional retry)
[ ] Add Mistral SQL generation prompts: CSV-only path and MsSQL path
[ ] Extend API: CSV upload, DB connection profile CRUD, run + ask endpoints
[ ] Extend frontend: role gate, CSV uploader, DB profile panel, run chat history
[ ] Add pyodbc + pydantic-settings to pyproject.toml

## Phase 1 — Officer Quick-Answer Mode
[ ] Hard row-cap enforcement (10 000 rows) in execute_node
[ ] Single LLM pass (no planning step) for officer role
[ ] Plain-text / tight-table response formatting
[ ] Query frequency rate-limit (in-memory token bucket per user)

## Phase 2 — Analyst Deep-Dive Mode
[ ] Plan-first reasoning with schema-awareness node
[ ] Iterative refinement loop (LLM re-scores result quality before returning)
[ ] Auto anomaly-scan: pass over result set for gaps, outliers, abnormal frequency
[ ] Follow-up suggestions surfaced post-answer
[ ] Cross-source auto-join with analyst confirmation checkpoint

## Phase 3 — Evidence-Grade Hardening
[ ] Append-only audit log to external rotation target
[ ] Per-user RBAC (separate from role — granular table/column access in MsSQL)
[ ] REST auth (JWT short-lived tokens) replacing the demo header-passthrough
[ ] Black-box import / export (session-level .zip of CSVs + reports for evidence chain)
