# Tracking

## In Progress

- PR #1 (loftsshuki/ai-counsel): All tiers + web UI + refinement mode — ready to merge

## Up Next

- Deploy web UI to public URL (Railway/Render)
- Record demo GIF for README
- Implement auth/payment for Pro tier
- Build out model picker with live API calls in the picker modal

## Done This Week

- **Tier 1 — Code Quality Foundation:**
  - Web search tool (DuckDuckGo + Tavily)
  - Persona/system_prompt system (8+ persona panels)
  - Pre-commit code review panels (full + quick)
  - Executive summary mode (plain-English)
  - Structured Decision Artifacts (Finding model, auto-extraction)
  - Codebase Health Score MCP tool (weighted A-F grades)
- **Tier 2 — Learning Flywheel:**
  - Architecture Debt Tracker (persistent SQLite ledger)
  - Regression Sentinel (auto-detect recurring issues)
  - Model Calibration System (per-model accuracy by domain)
  - Deliberation Chains (chain_id/chain_step, multi-step pipelines)
- **Tier 3 — Growth:**
  - Live Streaming Web UI (FastAPI + SSE + 4 design versions)
  - CI/CD GitHub Action (PR reviews with findings comments)
  - Panel Marketplace CLI (install/export/list)
  - Zero-Config Setup Wizard (auto-detect adapters)
- **Refinement Mode:**
  - 3 refinement panels: Prompt, Copy, System Prompt
  - Each runs 3 specialist models for 3 rounds of competitive improvement
  - Pro tier pricing CTA in web UI
- **Chained Review Panels:**
  - Full Stack Audit (Architecture → Code → Security → Performance)
  - Frontend Review (UX → Accessibility → Performance → Security)
  - Backend Review (API → Security → Data → Reliability)
  - Launch Readiness (Security → Performance → UX → Ops)
- **Web UI Design:**
  - v1: Scroll page with topo background, animated orbs, category cards
  - v2: Tabbed command console (Bloomberg Terminal style)
  - v3: Luxury real estate editorial (dark cards on dark bg)
  - v3-cream: Luxury editorial with cream background (current)
  - Model picker modal with tier badges
  - 26 category cards across 6 sections + 4 chain cards + 3 refinement cards
- **Infrastructure:**
  - Fixed 49 pre-existing test failures (949+ passing)
  - Removed upstream remote permanently
  - Business model doc (AI_COUNCIL_IDEAS.md)
  - Strategic vision doc (docs/plans/code-quality-guardian-v1.md)

