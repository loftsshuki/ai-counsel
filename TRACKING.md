# Tracking

## In Progress

- Nothing — all shipped to main

## Up Next

- Record demo GIF for README
- Implement auth/payment for Pro tier
- Live test: run full brainstorm workflow against real models on Railway
- Build structured brief templates (optional, for Strategic Decision category)
- Rotate API keys (OpenRouter + Nebius exposed in conversation)

## Done This Week

- **CEO & Board Mode:**
  - CEO agent orchestration (one model leads, others respond, leader synthesizes)
  - Agent Expertise persistent memory (per-model scratch pads across sessions)
  - SVG visual arguments (models generate diagrams to support positions)
- **6 Workflow Modes:**
  - Deliberate (debate + converge), Brainstorm (diverge → expand → rank)
  - Red Team (propose → attack → defend), Interview (questions → answers → response)
  - Tournament (bracket elimination), Refine (iterative 5/10 → 10/10)
- **Document Upload:**
  - Drag-and-drop file upload for council review
  - 30+ file types supported (.py, .js, .ts, .md, .json, .yaml, .sql, etc.)
  - File contents injected as context into deliberation
- **Web UI deployed to Railway:**
  - Public URL: https://adorable-magic-production-cbf2.up.railway.app
  - Slim Dockerfile (no ML packages, fast builds)
  - OpenRouter + Nebius API keys configured
- **81+ Models via OpenRouter:**
  - Full model registry with pricing tiers
  - Xiaomi MiMo-V2-Pro, Grok 4.20, NVIDIA Nemotron, Kimi K2.5, DeepSeek v3.2, Perplexity Sonar Pro
- **E2E Encrypted Sharing:**
  - Browser-side AES-GCM encryption via Web Crypto API
  - Decryption key in URL hash (never sent to server)
- **Real-time Streaming Status Bar:**
  - Phase labels, model-by-model progress, cost tracker, timer
- **Cost Tracking:**
  - Per-model token pricing in config
  - Running cost display during deliberation
- **Private Mode:**
  - Toggle to skip transcript saving + decision graph storage
- **Luxury Brand Summary + HTML Export:**
  - Council Verdict: deep green hero, topo SVG, Cormorant Garamond, cream body
  - HTML export: full standalone branded page with metadata bar
- **Rewrite Mode:**
  - Toggle produces complete rewritten documents, not just critique
  - Download Rewrite button extracts and saves improved version
  - Progressive file version history across refinement rounds (v1→v2→v3)
  - Smart truncation: keeps first + last 2 versions if context exceeds 12K
- **Refinement File Upload:**
  - Upload updated files in refinement zone (not just initial upload)
  - Council sees full document evolution with version labels
- **Stop Button:**
  - AbortController cancels SSE stream mid-deliberation
- **File Upload Fix (Railway):**
  - python-multipart added to requirements-web.txt
- **Convergence Fix:**
  - SentenceTransformerBackend now fails fast at init for proper fallback chain
  - Jaccard fallback works on Railway (zero dependencies)
- **Previous Session (Tiers 1-3):**
  - Web search tool (DuckDuckGo + Tavily)
  - Persona/system_prompt system (8+ persona panels)
  - Pre-commit code review panels (full + quick)
  - Executive summary, Structured Findings, Health Score
  - Architecture Debt Tracker, Regression Sentinel, Model Calibration
  - Deliberation Chains, Panel Marketplace CLI, Setup Wizard
  - CI/CD GitHub Action, 4 web UI design versions
  - Fixed 49 pre-existing test failures (949+ passing)
  - Business model doc (AI_COUNCIL_IDEAS.md)
