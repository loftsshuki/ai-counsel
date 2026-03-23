"""AI Counsel Web UI — FastAPI server with SSE streaming.

Provides a real-time web interface for watching deliberations unfold.
Models debate, convergence meter updates, and results stream live.

Run: python -m web.app
"""
import asyncio
import json
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.config import load_config
from models.schema import DeliberateRequest, Participant
from adapters import create_adapter
from deliberation.engine import DeliberationEngine

logger = logging.getLogger(__name__)

# Global state
engine: Optional[DeliberationEngine] = None
config = None
panels_config = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize engine on startup, cleanup on shutdown."""
    global engine, config, panels_config

    project_dir = Path(__file__).parent.parent
    config = load_config(str(project_dir / "config.yaml"))

    # Load panels
    import yaml
    panels_path = project_dir / "panels.yaml"
    if panels_path.exists():
        with open(panels_path) as f:
            panels_config = yaml.safe_load(f).get("panels", {})

    # Build adapters
    adapters = {}
    if config.cli_tools:
        for name, tool_config in config.cli_tools.items():
            try:
                adapters[name] = create_adapter(name, tool_config)
            except Exception as e:
                logger.warning(f"Failed to create CLI adapter {name}: {e}")

    if config.adapters:
        for name, adapter_config in config.adapters.items():
            try:
                adapters[name] = create_adapter(name, adapter_config)
            except Exception as e:
                logger.warning(f"Failed to create HTTP adapter {name}: {e}")

    engine = DeliberationEngine(adapters, config=config, server_dir=project_dir)
    logger.info(f"Web UI initialized with {len(adapters)} adapters")

    yield  # App runs here

    logger.info("Web UI shutting down")


app = FastAPI(title="AI Counsel", description="Multi-model deliberation with live streaming", lifespan=lifespan)


class WebDeliberateRequest(BaseModel):
    """Simplified request model for the web UI."""
    question: str
    panel: Optional[str] = "quick-check"
    rounds: int = 2
    working_directory: str = "."
    custom_models: Optional[list] = None  # For custom council mode


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main UI."""
    html_path = Path(__file__).parent / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>AI Counsel</h1><p>index.html not found</p>")


@app.get("/api/models")
async def list_models():
    """List available models grouped by adapter with tier info."""
    if not config or not config.model_registry:
        return {}

    result = {}
    for adapter_name, models in config.model_registry.items():
        adapter_models = []
        for m in models:
            if not m.enabled:
                continue
            adapter_models.append({
                "id": m.id,
                "label": m.label,
                "tier": m.tier,
                "default": getattr(m, "default", False),
                "adapter": adapter_name,
            })
        if adapter_models:
            result[adapter_name] = adapter_models

    return result


@app.get("/api/panels")
async def list_panels():
    """List available panels."""
    result = {}
    for name, panel in panels_config.items():
        result[name] = {
            "description": panel.get("description", ""),
            "participants": len(panel.get("participants", [])),
            "rounds": panel.get("rounds", 2),
            "mode": panel.get("mode", "quick"),
        }
    return result


@app.post("/api/deliberate/stream")
async def deliberate_stream(request: WebDeliberateRequest):
    """
    Stream a deliberation via Server-Sent Events.

    Each event has a type:
    - status: Deliberation lifecycle updates
    - round_start: A new round is beginning
    - response: A model's response in the current round
    - convergence: Convergence check result
    - summary: Final summary
    - findings: Structured findings
    - complete: Deliberation finished
    - error: Something went wrong
    """
    if not engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            # Custom models override panel selection
            if request.custom_models and len(request.custom_models) >= 2:
                participants = [Participant(cli=m["adapter"], model=m["id"]) for m in request.custom_models]
                mode = "conference" if len(participants) > 2 else "quick"
                rounds = request.rounds
            elif request.panel and request.panel in panels_config:
                panel = panels_config[request.panel]
                participants = [Participant(**p) for p in panel["participants"]]
                mode = panel.get("mode", "quick")
                rounds = request.rounds or panel.get("rounds", 2)
            else:
                yield _sse("error", {"message": f"Panel '{request.panel}' not found"})
                return

            # Build request
            delib_request = DeliberateRequest(
                question=request.question,
                participants=participants,
                rounds=rounds,
                mode=mode,
                working_directory=request.working_directory,
            )

            # Use asyncio.Queue for true streaming — engine pushes events,
            # SSE generator pulls them and sends to browser in real-time
            event_queue: asyncio.Queue = asyncio.Queue()

            async def on_event(event_type: str, data: dict):
                """Callback fired by engine as each model responds."""
                await event_queue.put((event_type, data))

            async def run_deliberation():
                """Run engine in background task, push final events to queue."""
                try:
                    result = await engine.execute(delib_request, on_event=on_event)

                    # Push summary (engine doesn't fire this via callback)
                    if result.summary:
                        await event_queue.put(("summary", {
                            "consensus": result.summary.consensus,
                            "key_agreements": result.summary.key_agreements,
                            "key_disagreements": result.summary.key_disagreements,
                            "recommendation": result.summary.final_recommendation,
                            "executive_summary": result.summary.executive_summary,
                        }))

                    # Push findings
                    if result.structured_findings:
                        sf = result.structured_findings
                        await event_queue.put(("findings", {
                            "verdict": sf.verdict,
                            "risk_level": sf.risk_level,
                            "findings_count": len(sf.findings),
                            "findings": [f.model_dump() for f in sf.findings[:20]],
                        }))

                    # Push complete
                    await event_queue.put(("complete", {
                        "status": result.status,
                        "rounds_completed": result.rounds_completed,
                        "transcript_path": result.transcript_path,
                    }))
                except Exception as e:
                    logger.error(f"Deliberation error: {e}", exc_info=True)
                    await event_queue.put(("error", {"message": str(e)}))
                finally:
                    # Sentinel to signal stream end
                    await event_queue.put(None)

            # Start deliberation in background — don't await it
            task = asyncio.create_task(run_deliberation())

            # Yield events as they arrive from the engine
            while True:
                event = await event_queue.get()
                if event is None:
                    break  # Deliberation finished
                event_type, data = event
                yield _sse(event_type, data)

            # Ensure task is done (should be, since it sent None)
            await task

        except Exception as e:
            logger.error(f"Deliberation stream error: {e}", exc_info=True)
            yield _sse("error", {"message": str(e)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(event: str, data: dict) -> str:
    """Format a Server-Sent Event."""
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.app:app", host="0.0.0.0", port=8080, reload=True)
