"""Workflow definitions for different deliberation modes.

Each workflow defines per-round prompt strategies that transform how models
interact. The engine runs rounds as normal, but the prompt each model sees
changes based on the workflow phase.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class WorkflowPhase:
    """A single phase in a workflow."""
    name: str
    instruction: str  # Injected before the user's question
    label: str  # Short label for UI display


@dataclass
class Workflow:
    """A multi-phase workflow that transforms prompts per round."""
    id: str
    name: str
    description: str
    phases: list[WorkflowPhase]
    icon: str = ""

    def get_phase(self, round_num: int) -> WorkflowPhase:
        """Get the phase for a given round (1-indexed). Repeats last phase if rounds > phases."""
        idx = min(round_num - 1, len(self.phases) - 1)
        return self.phases[idx]

    def get_enhanced_prompt(self, round_num: int, question: str) -> str:
        """Wrap the user's question with the phase-specific instruction."""
        phase = self.get_phase(round_num)
        return f"""## Workflow Phase: {phase.name}

{phase.instruction}

---

## Question / Topic

{question}"""

    @property
    def recommended_rounds(self) -> int:
        return len(self.phases)


# ============================================================
# Built-in Workflows
# ============================================================

WORKFLOWS: dict[str, Workflow] = {}


def _register(w: Workflow):
    WORKFLOWS[w.id] = w
    return w


# --- Deliberate (default — no prompt transformation) ---
_register(Workflow(
    id="deliberate",
    name="Deliberate",
    description="Models debate, challenge reasoning, and converge on a recommendation.",
    icon="scales",
    phases=[
        WorkflowPhase("Debate", "Present your analysis and position. Be thorough and specific.", "Debate"),
        WorkflowPhase("Refine", "You've seen the other models' positions. Refine yours — address their strongest points, concede where they're right, strengthen where you disagree.", "Refine"),
        WorkflowPhase("Converge", "Final round. State your position clearly. Where do you agree with the group? Where do you still disagree and why?", "Converge"),
    ],
))

# --- Brainstorm ---
_register(Workflow(
    id="brainstorm",
    name="Brainstorm",
    description="Diverge first (wild ideas), then expand, then rank the best.",
    icon="lightbulb",
    phases=[
        WorkflowPhase(
            "Diverge",
            """Generate as many ideas as possible — aim for 8-12.
Be creative, unconventional, even provocative. No filtering, no critique yet.
Quantity over quality. Include at least 2 ideas that feel risky or unexpected.
Format each idea as: **Idea N: [Title]** — [1-2 sentence description]""",
            "Diverge"
        ),
        WorkflowPhase(
            "Expand",
            """You can now see everyone's ideas. Your job:
1. Pick the 3-4 most promising ideas from ALL models (not just yours)
2. For each, flesh it out: who's it for, how it works, what makes it viable
3. Combine ideas that strengthen each other — mashups welcome
4. Add 1-2 NEW ideas inspired by what you've seen
Do NOT rank yet — just build and expand.""",
            "Expand"
        ),
        WorkflowPhase(
            "Rank",
            """Final round. Rank the top 5 ideas across all models. For each:
1. **Why it's top 5** — the core insight that makes it strong
2. **Biggest risk** — what could kill it
3. **First step** — the smallest action to validate it
Then: name the #1 idea you'd bet on and explain why in 2 sentences.""",
            "Rank"
        ),
    ],
))

# --- Red Team ---
_register(Workflow(
    id="red_team",
    name="Red Team",
    description="One model proposes, others attack. Then the proposer defends.",
    icon="shield",
    phases=[
        WorkflowPhase(
            "Propose",
            """You are the PROPOSER. Present your best solution, plan, or approach.
Make the strongest case you can — be specific, detailed, and confident.
Structure it clearly so others can find weaknesses.""",
            "Propose"
        ),
        WorkflowPhase(
            "Attack",
            """You are the RED TEAM. Your job is to BREAK the proposal.
Find every weakness, gap, assumption, risk, and failure mode.
Be adversarial but constructive — explain WHY each issue matters.
Prioritize: what's most likely to actually go wrong?
Do not hold back. The proposal needs to survive this to be worth doing.""",
            "Attack"
        ),
        WorkflowPhase(
            "Defend & Revise",
            """You've seen the attacks. Now:
1. Acknowledge which criticisms are valid — don't be defensive
2. Explain how you'd address the top 3 most dangerous issues
3. Present a REVISED version of the proposal that survives the red team
4. Flag any risks you can't fully mitigate — be honest about what remains""",
            "Defend"
        ),
    ],
))

# --- Interview ---
_register(Workflow(
    id="interview",
    name="Interview",
    description="Models ask clarifying questions first, then give an informed answer.",
    icon="chat",
    phases=[
        WorkflowPhase(
            "Clarify",
            """Before answering, ask 3-5 clarifying questions that would significantly
change your advice depending on the answer. Focus on:
- Context you're missing (scale, timeline, constraints)
- Assumptions you'd need to validate
- Trade-offs that depend on the user's priorities
Format: numbered questions, each with a brief note on why it matters.""",
            "Questions"
        ),
        WorkflowPhase(
            "Analyze",
            """The user may not have answered your questions yet — that's OK.
Give your BEST answer assuming the most common/likely answers to your questions.
Where your advice would change based on different answers, say so explicitly.
Be thorough and actionable.""",
            "Analyze"
        ),
        WorkflowPhase(
            "Synthesize",
            """Final round. You've seen other models' questions and analyses.
Synthesize the best insights across all models into a single, comprehensive answer.
Highlight where models agreed (high confidence) and disagreed (flag for the user).
End with the 3 most important next steps.""",
            "Synthesize"
        ),
    ],
))

# --- Tournament ---
_register(Workflow(
    id="tournament",
    name="Tournament",
    description="Models compete head-to-head. Best ideas survive each round.",
    icon="trophy",
    phases=[
        WorkflowPhase(
            "Submit",
            """Submit your single best answer/solution/approach.
Make it as strong as possible — you're competing against other models.
Be specific and actionable. Quality over quantity.""",
            "Submit"
        ),
        WorkflowPhase(
            "Judge",
            """You can see all submissions. Act as a judge:
1. Score each submission 1-10 on: clarity, feasibility, insight, completeness
2. Identify the TOP 2 submissions and explain why they're strongest
3. Identify the WEAKEST submission and explain what it's missing
4. Take the best elements from all submissions and write a COMBINED version that's better than any individual one.""",
            "Judge"
        ),
        WorkflowPhase(
            "Crown",
            """Final round. Looking at the original submissions and the judging:
1. Declare a winner and explain why in 2 sentences
2. Present the DEFINITIVE version — the best possible answer combining all insights
3. List 3 things the user should do FIRST based on this answer""",
            "Crown"
        ),
    ],
))


# --- CEO & Board ---
_register(Workflow(
    id="ceo_boardroom",
    name="CEO & Board",
    description="One model leads as CEO. Board members debate. CEO writes the final memo.",
    icon="crown",
    phases=[
        WorkflowPhase(
            "Frame",
            "CEO frames the decision for the board. Board members give initial positions.",
            "Frame"
        ),
        WorkflowPhase(
            "Debate",
            "CEO challenges the board. Board members defend, revise, or escalate.",
            "Debate"
        ),
        WorkflowPhase(
            "Memo",
            "Board gives closing statements. CEO writes the definitive decision memo.",
            "Memo"
        ),
    ],
))


def get_workflow(workflow_id: str) -> Optional[Workflow]:
    """Get a workflow by ID. Returns None if not found."""
    return WORKFLOWS.get(workflow_id)


def list_workflows() -> list[dict]:
    """List all available workflows for the API."""
    return [
        {
            "id": w.id,
            "name": w.name,
            "description": w.description,
            "icon": w.icon,
            "phases": [{"name": p.name, "label": p.label} for p in w.phases],
            "recommended_rounds": w.recommended_rounds,
        }
        for w in WORKFLOWS.values()
    ]
