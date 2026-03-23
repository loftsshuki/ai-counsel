"""CEO & Board orchestration pattern.

Unlike equal-peer deliberation where all models run in parallel,
the CEO pattern has a designated leader who:
1. Frames the question for the board
2. Reads all board responses and directs follow-ups
3. Writes the final synthesis/memo

The first participant in the list is always the CEO.
All others are board members who respond in parallel.
"""
import asyncio
import logging
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

from models.schema import Participant, RoundResponse

if TYPE_CHECKING:
    from deliberation.engine import DeliberationEngine, EventCallback

logger = logging.getLogger(__name__)


async def execute_ceo_round(
    engine: "DeliberationEngine",
    round_num: int,
    total_rounds: int,
    prompt: str,
    ceo: Participant,
    board: List[Participant],
    previous_responses: List[RoundResponse],
    graph_context: str = "",
    working_directory: Optional[str] = None,
    on_event: "EventCallback" = None,
    expertise_store: Optional[dict] = None,
) -> List[RoundResponse]:
    """Execute a single CEO-orchestrated round.

    Round 1: CEO frames the question → board responds in parallel
    Round N (middle): CEO directs conversation → board responds
    Final round: CEO writes the definitive memo
    """
    responses: List[RoundResponse] = []

    # Get adapter references
    ceo_adapter = engine.adapters.get(ceo.cli)
    if not ceo_adapter:
        return [RoundResponse(
            round=round_num,
            participant=f"{ceo.model}@{ceo.cli}",
            response=f"[ERROR: Adapter '{ceo.cli}' not found]",
            timestamp=datetime.now().isoformat(),
        )]

    # Build context from previous responses
    context = engine._build_context(previous_responses, current_round_num=round_num) if previous_responses else None

    # Load CEO expertise if available
    expertise_context = ""
    if expertise_store and f"{ceo.model}@{ceo.cli}" in expertise_store:
        expertise_context = f"\n\n## Your Expertise Notes\n{expertise_store[f'{ceo.model}@{ceo.cli}']}"

    # ===== PHASE 1: CEO speaks =====
    if round_num == 1:
        ceo_instruction = f"""## You are the CEO — Chief Executive Officer of this council.

You lead this deliberation. Your board members are: {', '.join(f'{b.persona or b.model}' for b in board)}.

**Your task for Round 1:** Frame the question for the board. Break it down into the key dimensions they should address. Set the stakes. Tell them what you need from them.

Do NOT answer the question yourself yet. Direct the conversation.{expertise_context}

---

{prompt}"""
    elif round_num == total_rounds:
        ceo_instruction = f"""## You are the CEO — Final Round

You've heard all perspectives from your board. Now write the DEFINITIVE MEMO.

**Structure your memo as:**
1. **Decision** — Your clear recommendation (1-2 sentences)
2. **Decision Framework** — A visual/SVG diagram showing the decision logic
3. **Board Stances** — Each member's position and key argument
4. **Resolved Tensions** — Where the board agreed
5. **Unresolved Tensions** — Where disagreement remains and why it matters
6. **Top 3 Actions** — Specific next steps with owners and timelines
7. **Risks & Trade-offs** — What could go wrong

Be decisive. The board has debated — now you decide.{expertise_context}

---

{prompt}"""
    else:
        ceo_instruction = f"""## You are the CEO — Round {round_num}

You've read the board's responses. Now:
1. Identify the strongest points and weakest arguments
2. Push the board on unresolved tensions — ask harder questions
3. Challenge any surface-level thinking
4. Direct specific board members to go deeper on specific issues

Do NOT write the final memo yet. Keep the debate productive.{expertise_context}

---

{prompt}"""

    # Build CEO-specific prompt with persona
    ceo_prompt = ceo_instruction
    if ceo.persona:
        ceo_prompt = f"## Your Role: {ceo.persona}\n\n{ceo_instruction}"

    try:
        ceo_response = await ceo_adapter.invoke(
            prompt=ceo_prompt,
            model=ceo.model,
            context=context,
            is_deliberation=True,
            working_directory=working_directory,
            reasoning_effort=ceo.reasoning_effort,
        )
    except Exception as e:
        ceo_response = f"[ERROR: {type(e).__name__}: {str(e)}]"

    ceo_rr = RoundResponse(
        round=round_num,
        participant=f"{ceo.model}@{ceo.cli}",
        response=ceo_response,
        timestamp=datetime.now().isoformat(),
    )
    responses.append(ceo_rr)

    # Fire event for CEO response
    if on_event:
        try:
            await on_event("response", {
                "round": round_num,
                "participant": f"{ceo.model}@{ceo.cli}",
                "response": ceo_response,
                "timestamp": ceo_rr.timestamp,
                "role": "ceo",
            })
        except Exception:
            pass

    # ===== PHASE 2: Board responds (parallel) =====
    # On final round, board gives closing statements
    if round_num == total_rounds:
        board_instruction = """## Final Round — Closing Statement

The CEO is writing the final memo. Give your FINAL POSITION in one concise statement:
1. Your recommendation (accept/reject/modify and why)
2. The ONE thing the CEO must not ignore
3. Your confidence level (1-10)

Be brief and decisive."""
    else:
        board_instruction = f"""## Board Response — Round {round_num}

The CEO has directed the conversation. Read their message carefully and respond to their specific requests.
If they asked you a direct question, answer it. If they challenged your position, defend or revise it.

Remember: you are arguing for what's BEST, not what's safe. Push back on the CEO if you disagree."""

    # Build updated context including CEO's response this round
    updated_previous = previous_responses + responses
    board_context = engine._build_context(updated_previous, current_round_num=round_num)

    async def invoke_board_member(member: Participant) -> RoundResponse:
        adapter = engine.adapters.get(member.cli)
        if not adapter:
            return RoundResponse(
                round=round_num,
                participant=f"{member.model}@{member.cli}",
                response=f"[ERROR: Adapter '{member.cli}' not found]",
                timestamp=datetime.now().isoformat(),
            )

        member_prompt = board_instruction
        if member.persona:
            member_prompt = f"## Your Role: {member.persona}\n\n{board_instruction}"
        if member.system_prompt:
            member_prompt = f"{member.system_prompt}\n\n{member_prompt}"

        # Inject expertise
        if expertise_store and f"{member.model}@{member.cli}" in expertise_store:
            member_prompt += f"\n\n## Your Expertise Notes\n{expertise_store[f'{member.model}@{member.cli}']}"

        member_prompt += f"\n\n---\n\n{prompt}"

        try:
            text = await adapter.invoke(
                prompt=member_prompt,
                model=member.model,
                context=board_context,
                is_deliberation=True,
                working_directory=working_directory,
                reasoning_effort=member.reasoning_effort,
            )
        except Exception as e:
            text = f"[ERROR: {type(e).__name__}: {str(e)}]"

        return RoundResponse(
            round=round_num,
            participant=f"{member.model}@{member.cli}",
            response=text,
            timestamp=datetime.now().isoformat(),
        )

    # Run board members in parallel
    tasks = [asyncio.create_task(invoke_board_member(m)) for m in board]
    for coro in asyncio.as_completed(tasks):
        rr = await coro
        responses.append(rr)

        if on_event:
            try:
                await on_event("response", {
                    "round": round_num,
                    "participant": rr.participant,
                    "response": rr.response,
                    "timestamp": rr.timestamp,
                    "role": "board",
                })
            except Exception:
                pass

    return responses


def update_expertise(
    expertise_store: dict,
    responses: List[RoundResponse],
    question: str,
) -> dict:
    """Update expertise notes for each participant based on their deliberation.

    This is a lightweight version — tracks patterns, positions, and tensions.
    In production, you'd use a model to summarize key learnings.
    """
    for resp in responses:
        key = resp.participant
        if key not in expertise_store:
            expertise_store[key] = ""

        # Append a condensed note about this deliberation
        # Keep it short — expertise should be patterns, not transcripts
        short_q = question[:80] + ("..." if len(question) > 80 else "")
        note = f"\n- [{resp.timestamp[:10]}] Q: {short_q} | Position: {resp.response[:150]}..."
        expertise_store[key] += note

        # Cap expertise at ~4000 chars per agent to prevent unbounded growth
        if len(expertise_store[key]) > 4000:
            # Keep the most recent entries
            lines = expertise_store[key].strip().split("\n")
            while len("\n".join(lines)) > 3500 and len(lines) > 5:
                lines.pop(0)
            expertise_store[key] = "\n".join(lines)

    return expertise_store
