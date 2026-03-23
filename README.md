<p align="center">
  <img src="assets/ai-counsel.png" alt="AI Counsel Logo" width="400">
</p>

# AI Counsel

**A council of AI models that reviews your code before you ship it.**

One AI can miss things. Three AIs debating each other catch what one alone cannot: security holes, architecture mistakes, performance traps, and missing error handling.

They read your actual code. They challenge each other's reasoning. They converge on evidence-backed recommendations — with confidence scores and plain-English explanations.

**The senior engineering team you don't have.**

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)
![MCP](https://img.shields.io/badge/MCP-Server-green.svg)
![Tests](https://img.shields.io/badge/tests-950%2B%20passing-green)

---

## See It In Action

**Pre-Commit Code Review** (3 models, 3 perspectives):
```javascript
mcp__ai_counsel__deliberate({
  question: "Review my staged changes for issues",
  panel: "pre-commit-review",
  working_directory: "/path/to/your/project"
})
```
**Result**: `APPROVE_WITH_NOTES` — 1 high finding (missing input validation on contact form), 2 medium. Plain-English executive summary included.

**Codebase Health Check** (multi-panel, scored report card):
```javascript
mcp__ai_counsel__run_health_check({
  working_directory: "/path/to/your/project",
  panels: ["security-audit", "architecture-review", "code-review"]
})
```
**Result**: `B+ (87/100)` — Security: A-, Architecture: B, Correctness: A, Performance: C+. "Your site is strong on security but the listing logic is duplicated in three places."

---

## Features

### Code Quality
- **Pre-Commit Review Panels** — 3 reviewers (Correctness, Architecture, Risk) with APPROVE/REQUEST_CHANGES verdicts
- **Codebase Health Score** — Multi-panel A-F grading with weighted category scores
- **Structured Findings** — Machine-readable JSON: severity, category, file/line, suggested fixes
- **Executive Summaries** — Plain-English 3-paragraph summaries for non-technical stakeholders

### Learning Flywheel
- **Architecture Debt Tracker** — Persistent SQLite ledger of all findings with severity tracking
- **Regression Sentinel** — Auto-detects when the same issue recurs across deliberations
- **Model Calibration** — Per-model accuracy tracking by domain (security, performance, etc.)
- **Deliberation Chains** — Multi-step pipelines: quick-check → code-review → security-audit

### Deliberation Engine
- **Multi-Round Convergence** — Semantic similarity detection with auto-stopping
- **Evidence-Based** — Models read files, search code, run commands, search the web (Tavily/DuckDuckGo)
- **Persona System** — Custom per-participant roles, system prompts, and evaluation criteria
- **Decision Graph Memory** — Learns from past deliberations, injects context into new ones
- **Structured Voting** — Confidence levels, rationale, and continue_debate signals

### Growth & Community
- **Live Streaming Web UI** — FastAPI + SSE with real-time debate feed and convergence meter
- **GitHub Action** — Run code reviews on every PR, block merge on critical findings
- **Panel Marketplace** — Install, export, and share panel presets
- **Zero-Config Setup** — Auto-detects installed adapters and generates config

### Infrastructure
- **10 Adapters** — Claude, Codex, Droid, Gemini, llama.cpp, Ollama, LM Studio, OpenRouter, Nebius, OpenAI
- **950+ Tests** — TDD discipline, full Windows + Linux compatibility
- **Fault Tolerant** — Individual adapter failures don't halt deliberation

---

## Quick Start

### Option 1: Auto-Setup (Recommended)
```bash
git clone https://github.com/loftsshuki/ai-counsel.git
cd ai-counsel
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python setup_wizard.py  # Auto-detects your adapters, generates config
```

### Option 2: Manual Setup
```bash
git clone https://github.com/loftsshuki/ai-counsel.git
cd ai-counsel
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.yaml.example config.yaml  # Edit with your adapters
```

### Configure in Claude Code

Create `.mcp.json` in your project:
```json
{
  "mcpServers": {
    "ai-counsel": {
      "type": "stdio",
      "command": ".venv/bin/python",
      "args": ["server.py"],
      "env": {}
    }
  }
}
```

### Web UI
```bash
python -m web.app  # Opens at http://localhost:8080
```

---

## Panel Presets

| Panel | Models | Rounds | Purpose |
|-------|--------|--------|---------|
| `pre-commit-review` | 3 (Correctness, Architecture, Risk) | 2 | Review staged changes before commit |
| `pre-commit-quick` | 2 | 1 | Fast review for small changes |
| `security-audit` | 3 (Claude Opus, Grok, Qwen) | 3 | Deep security review |
| `architecture-review` | 3 | 2 | Architecture and design review |
| `code-review` | 3 | 2 | Code quality and correctness |
| `deep-analysis` | 3 (premium models) | 3 | Thorough analysis |
| `product-council` | 3 (Strategist, User Advocate, Pragmatist) | 2 | Product decisions |
| `security-red-team` | 3 (Attacker, Defender, Compliance) | 3 | Adversarial security |
| `luxury-brand-council` | 3 (Creative Director, Conversion, Technical) | 2 | Brand & design review |

### Panel Marketplace
```bash
python panel_cli.py list                    # List installed panels
python panel_cli.py info pre-commit-review  # Show panel details
python panel_cli.py install panel.yaml      # Install from file or URL
python panel_cli.py export security-audit   # Export to shareable file
```

---

## MCP Tools

| Tool | Description |
|------|-------------|
| `deliberate` | Run a multi-model deliberation with voting and convergence |
| `run_health_check` | Score codebase health across multiple review panels (A-F) |
| `list_models` | Show available models per adapter |
| `set_session_models` | Set session-scoped default models |
| `query_decisions` | Search past deliberations, find contradictions, trace evolution |
| `get_quality_metrics` | Track per-model vote success rate and response quality |

---

## GitHub Action

Run code reviews on every PR:

```yaml
# .github/workflows/code-review.yml
name: AI Counsel Review
on: [pull_request]
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: loftsshuki/ai-counsel@main
        with:
          panel: pre-commit-review
          fail_on_critical: "true"
          openrouter_api_key: ${{ secrets.OPENROUTER_API_KEY }}
```

---

## Architecture

```
ai-counsel/
├── server.py                 # MCP server (stdio transport)
├── config.yaml               # All configuration
├── panels.yaml               # Panel presets
├── web/                      # Live streaming web UI
│   ├── app.py               # FastAPI + SSE backend
│   └── index.html           # Dark-theme frontend
├── adapters/                 # 10 CLI/HTTP adapters
├── deliberation/             # Core engine
│   ├── engine.py            # Multi-round orchestration
│   ├── convergence.py       # Semantic similarity detection
│   ├── findings.py          # Structured findings extraction
│   ├── health_score.py      # Codebase health scoring
│   ├── calibration.py       # Model accuracy tracking
│   ├── web_search.py        # DuckDuckGo + Tavily
│   └── tools.py             # Evidence-based tool execution
├── decision_graph/           # Persistent memory
│   ├── storage.py           # SQLite persistence
│   ├── debt_tracker.py      # Architecture debt ledger
│   └── integration.py       # Context injection
├── models/                   # Pydantic schemas
├── tests/                    # 950+ tests
├── setup_wizard.py           # Zero-config setup
├── panel_cli.py              # Panel marketplace CLI
├── action.yml                # GitHub Action
└── action_entrypoint.py      # CI/CD entrypoint
```

---

## Development

```bash
pytest tests/unit -v                        # Unit tests
pytest tests/integration -v -m integration  # Integration tests
black . && ruff check .                     # Code quality
```

## License

MIT License

---

**950+ tests. Evidence-based. Gets smarter with every review.**
