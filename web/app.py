"""AI Counsel Web UI — FastAPI server with SSE streaming.

Provides a real-time web interface for watching deliberations unfold.
Models debate, convergence meter updates, and results stream live.

Run: python -m web.app
"""
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.config import load_config
from models.schema import DeliberateRequest, Participant
from adapters import create_adapter
from deliberation.engine import DeliberationEngine

logger = logging.getLogger(__name__)

app = FastAPI(title="AI Counsel", description="Multi-model deliberation with live streaming")

# Global state
engine: Optional[DeliberationEngine] = None
config = None
panels_config = {}


class WebDeliberateRequest(BaseModel):
    """Simplified request model for the web UI."""
    question: str
    panel: Optional[str] = "quick-check"
    rounds: int = 2
    working_directory: str = "."


@app.on_event("startup")
async def startup():
    """Initialize engine on startup."""
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


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main UI."""
    html_path = Path(__file__).parent / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>AI Counsel</h1><p>index.html not found</p>")


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
            # Resolve panel
            if request.panel and request.panel in panels_config:
                panel = panels_config[request.panel]
                participants = [Participant(**p) for p in panel["participants"]]
                mode = panel.get("mode", "quick")
                rounds = request.rounds or panel.get("rounds", 2)
            else:
                yield _sse("error", {"message": f"Panel '{request.panel}' not found"})
                return

            yield _sse("status", {
                "phase": "starting",
                "question": request.question[:200],
                "panel": request.panel,
                "participants": [f"{p.model}@{p.cli}" for p in participants],
                "rounds": rounds,
            })

            # Build request
            delib_request = DeliberateRequest(
                question=request.question,
                participants=participants,
                rounds=rounds,
                mode=mode,
                working_directory=request.working_directory,
            )

            # Execute deliberation
            yield _sse("status", {"phase": "deliberating"})

            result = await engine.execute(delib_request)

            # Stream round responses
            for resp in result.full_debate:
                yield _sse("response", {
                    "round": resp.round,
                    "participant": resp.participant,
                    "response": resp.response[:2000],  # Truncate for streaming
                    "timestamp": resp.timestamp,
                })
                await asyncio.sleep(0.05)  # Small delay for visual effect

            # Stream convergence info
            if result.convergence_info:
                yield _sse("convergence", {
                    "detected": result.convergence_info.detected,
                    "status": result.convergence_info.status,
                    "similarity": result.convergence_info.final_similarity,
                })

            # Stream summary
            if result.summary:
                yield _sse("summary", {
                    "consensus": result.summary.consensus,
                    "key_agreements": result.summary.key_agreements,
                    "key_disagreements": result.summary.key_disagreements,
                    "recommendation": result.summary.final_recommendation,
                    "executive_summary": result.summary.executive_summary,
                })

            # Stream findings
            if result.structured_findings:
                sf = result.structured_findings
                yield _sse("findings", {
                    "verdict": sf.verdict,
                    "risk_level": sf.risk_level,
                    "findings_count": len(sf.findings),
                    "findings": [f.model_dump() for f in sf.findings[:20]],
                })

            # Complete
            yield _sse("complete", {
                "status": result.status,
                "rounds_completed": result.rounds_completed,
                "transcript_path": result.transcript_path,
            })

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
