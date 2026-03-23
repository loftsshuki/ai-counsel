# AI Counsel — Business Model & Product Ideas

## Business Model

### Pricing Tiers

| Tier | Price | Models | Features |
|---|---|---|---|
| **Free** | $0 | Free-tier only (Gemma 27B, Mistral Small 24B) | 5 deliberations/day, basic panels, 1 round max |
| **Pro** | $29/mo | Balanced-tier (Gemini Flash, GPT-4o Mini, Llama 70B) | Unlimited deliberations, all panels + chains, Tavily web search, health score, debt tracker, executive summaries |
| **Team** | $79/mo | Premium + Flagship (Claude Opus, GPT-5, Grok 4, o3) | Everything in Pro + GitHub Action CI/CD, model calibration, custom panels, API access, 5 seats |
| **Enterprise** | Custom | All models + self-hosted/private | SSO, audit logs, dedicated support, on-prem deployment, custom adapter development |

### Revenue Model Notes

- **We don't host models** — we route to them via API. Cost per deliberation is API pass-through only.
- A 3-model deliberation costs ~$0.10-0.50 in API calls but the structured output (health score, debt tracking, regression detection, executive summaries) is worth $5+ to the customer.
- **Margin is in the orchestration**, not the inference.
- Free tier uses OpenRouter free models (zero cost to us). Conversion to Pro happens when users want better models or more deliberations.
- Team tier unlocks the CI/CD pipeline — this is the "enterprise wedge" that gets into engineering teams.

### Growth Flywheel

```
Free users try it → see value in structured reviews
  → upgrade to Pro for better models + unlimited
    → engineering teams adopt → upgrade to Team for CI/CD
      → Team data feeds model calibration → reviews get smarter
        → more teams adopt → Enterprise deals
```

## Model Picker

### Design

The web UI should have a model picker that:
1. Shows all available models grouped by provider (Claude, OpenRouter, OpenAI, etc.)
2. Each model has a tier badge: Free, Balanced, Premium, Flagship
3. Users can select 2-5 models for their deliberation
4. Free tier users can only pick from Free-tier models
5. Hovering a model shows: provider, tier, speed rating, typical use case
6. The panel dropdown auto-selects recommended models, but users can customize
7. A "Custom Council" mode lets you build your own panel from scratch

### Tier-to-Model Mapping

| Tier | Badge Color | Example Models |
|---|---|---|
| Free | Gray | Gemma 27B, Mistral Small 24B, MiMo-VL |
| Balanced | Blue | Gemini 2.5 Flash, GPT-4o Mini, Llama 3.3 70B |
| Premium | Green | Claude Sonnet, Gemini 2.5 Pro, Grok 3 |
| Flagship | Gold | Claude Opus, GPT-5.4, Grok 4.20, o3 Pro, Gemini 3.1 Pro |
| Reasoning | Purple | DeepSeek R1, o3, Kimi K2 Thinking, Qwen 3 Thinking |

### Technical Implementation

- Backend: `/api/models` endpoint returns models from `model_registry` in config.yaml
- Frontend: Modal or slide-out panel with model cards
- Each model card shows: name, provider icon, tier badge, enabled/disabled state
- Selected models highlighted with green border
- "Start Deliberation" button shows selected model count

## Future Product Ideas

### Collaboration Features (Team tier)
- Shared deliberation history across team
- Comment on findings ("I'll fix this" / "Won't fix — here's why")
- Assign findings to team members
- Weekly digest email with codebase health trends

### Marketplace Revenue
- Panel creators earn revenue share when their panels are used
- Featured panels on homepage (sponsored placement)
- Verified panel badges for quality-tested presets

### API Access (Team/Enterprise)
- REST API for triggering deliberations programmatically
- Webhook callbacks when deliberation completes
- Streaming WebSocket API for real-time integration
- SDKs: Python, TypeScript, Go

### Analytics Dashboard (Pro+)
- Deliberation history with trending health score
- Model performance comparison (which models find the most real issues?)
- Team activity: who's running reviews, what's getting caught
- Cost tracking per deliberation, per model, per month
