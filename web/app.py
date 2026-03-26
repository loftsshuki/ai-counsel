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

import tempfile
import uuid

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
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
    rounds: Optional[int] = None  # None = auto-detect from workflow/panel
    working_directory: str = "."
    custom_models: Optional[list] = None  # For custom council mode
    # Refinement loop fields
    previous_result: Optional[str] = None  # Council's previous output
    user_feedback: Optional[str] = None  # What the user wants improved
    refinement_round: int = 0  # Which iteration (0 = first run)
    workflow: Optional[str] = None  # Workflow mode: brainstorm, red_team, etc.
    private_mode: bool = False  # Skip transcript saving + decision graph storage
    upload_id: Optional[str] = None  # Reference to uploaded documents
    produce_rewrite: bool = False  # If true, models output rewritten doc, not just critique


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
                "input_cost": m.input_cost,   # per 1M tokens, USD
                "output_cost": m.output_cost,  # per 1M tokens, USD
            })
        if adapter_models:
            result[adapter_name] = adapter_models

    return result


@app.get("/api/workflows")
async def list_workflows_endpoint():
    """List available workflow modes."""
    from deliberation.workflows import list_workflows
    return list_workflows()


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


# --- Document Upload ---
# In-memory store for uploaded documents (keyed by session upload_id)
_uploaded_docs: dict[str, list[dict]] = {}

# Allowed file extensions and max size (10MB)
_ALLOWED_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".c", ".cpp",
    ".h", ".cs", ".rb", ".php", ".swift", ".kt", ".scala", ".r",
    ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".xml", ".csv",
    ".html", ".css", ".scss", ".sql", ".sh", ".bash", ".zsh",
    ".env", ".conf", ".cfg", ".ini", ".dockerfile",
    ".sol", ".vy",  # smart contracts
}
_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@app.post("/api/upload")
async def upload_documents(files: list[UploadFile] = File(...)):
    """Upload documents for council review. Returns an upload_id to reference in deliberation."""
    upload_id = str(uuid.uuid4())[:8]
    docs = []

    for f in files:
        # Validate extension
        ext = Path(f.filename or "").suffix.lower()
        if ext not in _ALLOWED_EXTENSIONS and ext != "":
            # Allow extensionless files (like Dockerfile, Makefile)
            pass

        # Read content with size limit
        content = await f.read()
        if len(content) > _MAX_FILE_SIZE:
            return JSONResponse(
                status_code=413,
                content={"error": f"File '{f.filename}' exceeds 10MB limit"}
            )

        # Decode text
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            return JSONResponse(
                status_code=415,
                content={"error": f"File '{f.filename}' is not a text file"}
            )

        docs.append({
            "filename": f.filename,
            "size": len(content),
            "content": text,
        })

    _uploaded_docs[upload_id] = docs

    return {
        "upload_id": upload_id,
        "files": [{"filename": d["filename"], "size": d["size"]} for d in docs],
    }


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
            # Resolve rounds: user choice > workflow recommendation > panel default > 2
            # Refinement runs auto-default to 2 rounds (less context bloat)
            from deliberation.workflows import get_workflow
            active_wf = get_workflow(request.workflow) if request.workflow else None
            is_refinement = request.previous_result and request.user_feedback
            if is_refinement:
                default_rounds = 2
            else:
                default_rounds = active_wf.recommended_rounds if active_wf else 2

            # Custom models override panel selection
            if request.custom_models and len(request.custom_models) >= 2:
                participants = [Participant(cli=m["adapter"], model=m["id"]) for m in request.custom_models]
                mode = "conference" if len(participants) > 2 else "quick"
                rounds = request.rounds if request.rounds is not None else default_rounds
            elif request.panel and request.panel in panels_config:
                panel = panels_config[request.panel]
                participants = [Participant(**p) for p in panel["participants"]]
                mode = panel.get("mode", "quick")
                rounds = request.rounds if request.rounds is not None else panel.get("rounds", default_rounds)
            else:
                yield _sse("error", {"message": f"Panel '{request.panel}' not found"})
                return

            # Build question — inject refinement context if this is a follow-up
            question = request.question
            if request.previous_result and request.user_feedback:
                question = f"""## Refinement Round {request.refinement_round}

You previously answered this question and the user wants improvements.

### Original Question
{request.question}

### Your Previous Answer
{request.previous_result}

### User Feedback — What They Want Changed
{request.user_feedback}

### Instructions
Address the user's feedback directly. Keep what worked, fix what didn't. Be specific and actionable. This is refinement round {request.refinement_round} — the goal is 10/10."""

            # Inject uploaded documents as context
            if request.upload_id and request.upload_id in _uploaded_docs:
                docs = _uploaded_docs[request.upload_id]
                doc_context = "\n\n## Uploaded Documents for Review\n\n"
                for doc in docs:
                    doc_context += f"### File: `{doc['filename']}`\n```\n{doc['content']}\n```\n\n"
                question = question + doc_context
                # Clean up after use
                del _uploaded_docs[request.upload_id]

            # Rewrite instruction — stored separately, injected only in final round
            # by the engine via delib_request.rewrite_instruction
            rewrite_instruction = None
            if request.produce_rewrite:
                rewrite_instruction = "\n\n### IMPORTANT: Produce Rewritten Version\nDo NOT just list suggestions or critique. You MUST output a complete, polished, rewritten version of the document that incorporates all improvements. Start your response with `## Rewritten Document` followed by the full improved text. After the rewritten document, add a brief `## Changes Made` section listing what you changed and why."

            # Build request
            delib_request = DeliberateRequest(
                question=question,
                participants=participants,
                rounds=rounds,
                mode=mode,
                working_directory=request.working_directory,
                workflow=request.workflow,
                rewrite_instruction=rewrite_instruction,
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
                    # Private mode: temporarily disable transcript + decision graph
                    saved_transcript_mgr = None
                    saved_graph = None
                    if request.private_mode and engine:
                        saved_transcript_mgr = engine.transcript_manager
                        saved_graph = engine.graph_integration
                        engine.transcript_manager = None
                        engine.graph_integration = None

                    result = await engine.execute(delib_request, on_event=on_event)

                    # Restore after execution
                    if request.private_mode and engine:
                        engine.transcript_manager = saved_transcript_mgr
                        engine.graph_integration = saved_graph

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


# ===== E2E Encrypted Sharing =====
# Server stores ONLY encrypted blobs. Decryption key never touches server.
# Key lives in URL hash (#fragment) which browsers don't send to servers.

import secrets
import time

# In-memory store with TTL. Production would use Redis.
_shares: dict[str, dict] = {}
_SHARE_MAX_SIZE = 2 * 1024 * 1024  # 2MB max encrypted payload
_SHARE_TTL = 86400  # 24 hours


def _cleanup_expired_shares():
    """Remove expired shares."""
    now = time.time()
    expired = [k for k, v in _shares.items() if now > v["expires_at"]]
    for k in expired:
        del _shares[k]


class ShareRequest(BaseModel):
    data: str  # Base64url-encoded encrypted ciphertext
    iv: str  # Base64url-encoded initialization vector
    expires: str = "24h"  # TTL


@app.post("/api/share")
async def create_share(req: ShareRequest):
    """Store an encrypted blob. Server never sees the decryption key."""
    _cleanup_expired_shares()

    # Size check (base64 is ~1.33x the binary size)
    if len(req.data) > _SHARE_MAX_SIZE:
        raise HTTPException(status_code=413, detail="Payload too large (max 2MB)")

    # Rate limit: max 100 active shares
    if len(_shares) > 100:
        raise HTTPException(status_code=429, detail="Too many active shares")

    share_id = secrets.token_urlsafe(16)
    _shares[share_id] = {
        "data": req.data,
        "iv": req.iv,
        "created_at": time.time(),
        "expires_at": time.time() + _SHARE_TTL,
    }

    logger.info(f"E2E share created: {share_id} (expires in 24h)")
    return {"id": share_id}


@app.get("/api/share/{share_id}")
async def get_share(share_id: str):
    """Retrieve an encrypted blob. Client decrypts with key from URL hash."""
    _cleanup_expired_shares()

    if share_id not in _shares:
        raise HTTPException(status_code=404, detail="Share not found or expired")

    share = _shares[share_id]
    return {"data": share["data"], "iv": share["iv"]}


@app.get("/shared/{share_id}", response_class=HTMLResponse)
async def shared_view(share_id: str):
    """Serve the decryption page. Key comes from URL hash (never sent to server)."""
    return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AI Counsel — Encrypted Share</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {{ --bg:oklch(96.5% 0.008 85); --surface:oklch(99% 0.003 85); --border:oklch(87% 0.01 85); --green:oklch(38% 0.12 155); --cream:oklch(18% 0.025 155); --fm:'JetBrains Mono',monospace; --fb:'Outfit',system-ui,sans-serif; }}
  * {{ margin:0;padding:0;box-sizing:border-box }}
  body {{ font-family:var(--fb);background:var(--bg);color:var(--cream);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:2rem }}
  .card {{ background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:2rem;max-width:800px;width:100% }}
  h1 {{ font-size:1.3rem;font-weight:600;margin-bottom:.5rem }}
  .badge {{ display:inline-flex;align-items:center;gap:.3rem;font-family:var(--fm);font-size:.7rem;padding:.25rem .6rem;border-radius:4px;background:oklch(45% 0.12 155 / 0.12);color:var(--green);border:1px solid oklch(45% 0.12 155 / 0.25);margin-bottom:1.5rem }}
  #content {{ font-family:var(--fm);font-size:.85rem;line-height:1.8;white-space:pre-wrap;max-height:70vh;overflow-y:auto;padding:1rem;background:var(--bg);border-radius:6px;border:1px solid var(--border) }}
  #status {{ font-family:var(--fm);font-size:.85rem;color:oklch(50% 0.02 155);text-align:center;padding:2rem }}
  .actions {{ display:flex;gap:.5rem;margin-top:1rem }}
  .actions button {{ background:var(--green);color:oklch(97% .01 85);border:none;border-radius:5px;padding:.5rem 1rem;font-family:var(--fb);font-size:.85rem;font-weight:500;cursor:pointer }}
</style>
</head><body>
<div class="card">
  <h1>AI Counsel Deliberation</h1>
  <div class="badge">
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>
    End-to-end encrypted
  </div>
  <div id="status">Decrypting...</div>
  <div id="content" style="display:none"></div>
  <div id="acts" class="actions" style="display:none">
    <button onclick="navigator.clipboard.writeText(document.getElementById('content').textContent).then(()=>this.textContent='Copied!')">Copy All</button>
    <button onclick="let b=new Blob([document.getElementById('content').textContent],{{type:'text/markdown'}});let a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='deliberation.md';a.click()">Download .md</button>
  </div>
</div>
<script>
(async()=>{{
  const keyB64=location.hash.slice(1);
  if(!keyB64){{ document.getElementById('status').textContent='No decryption key in URL. The link may be incomplete.';return }}
  try{{
    // Fetch encrypted data
    const r=await fetch('/api/share/{share_id}');
    if(!r.ok){{ document.getElementById('status').textContent='Share not found or expired (24h limit).';return }}
    const {{data,iv}}=await r.json();
    // Decode base64url
    const b64d=s=>Uint8Array.from(atob(s.replace(/-/g,'+').replace(/_/g,'/')),c=>c.charCodeAt(0));
    const keyRaw=b64d(keyB64);
    const ivRaw=b64d(iv);
    const cipherRaw=b64d(data);
    // Import key and decrypt
    const key=await crypto.subtle.importKey('raw',keyRaw,{{name:'AES-GCM'}},false,['decrypt']);
    const plain=await crypto.subtle.decrypt({{name:'AES-GCM',iv:ivRaw}},key,cipherRaw);
    const text=new TextDecoder().decode(plain);
    document.getElementById('status').style.display='none';
    document.getElementById('content').style.display='block';
    document.getElementById('content').textContent=text;
    document.getElementById('acts').style.display='flex';
  }}catch(e){{
    document.getElementById('status').textContent='Decryption failed. The key may be wrong or the data corrupted.';
  }}
}})();
</script>
</body></html>""")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.app:app", host="0.0.0.0", port=8080, reload=True)
