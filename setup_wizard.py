#!/usr/bin/env python3
"""AI Counsel Zero-Config Setup Wizard.

Auto-detects installed adapters, generates config.yaml, and validates the setup.
Run: python setup_wizard.py
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def check_command(cmd: str) -> bool:
    """Check if a command is available on PATH."""
    return shutil.which(cmd) is not None


def check_http_service(url: str, timeout: int = 3) -> bool:
    """Check if an HTTP service is reachable."""
    try:
        import httpx
        resp = httpx.get(url, timeout=timeout)
        return resp.status_code < 500
    except Exception:
        return False


def detect_adapters() -> dict:
    """Auto-detect available adapters."""
    adapters = {}

    # CLI adapters
    cli_checks = {
        "claude": "claude",
        "codex": "codex",
        "droid": "droid",
        "gemini": "gemini",
        "llama-cli": "llamacpp",
    }
    for cmd, name in cli_checks.items():
        if check_command(cmd):
            adapters[name] = {"type": "cli", "command": cmd}
            print(f"  [FOUND] {name} ({cmd})")
        else:
            print(f"  [    ] {name} ({cmd}) — not installed")

    # HTTP adapters
    http_checks = {
        "ollama": "http://localhost:11434",
        "lmstudio": "http://localhost:1234",
    }
    for name, url in http_checks.items():
        if check_http_service(url):
            adapters[name] = {"type": "http", "url": url}
            print(f"  [FOUND] {name} ({url})")
        else:
            print(f"  [    ] {name} ({url}) — not running")

    # API key adapters
    api_checks = {
        "openrouter": "OPENROUTER_API_KEY",
        "openai": "OPENAI_API_KEY",
        "tavily": "TAVILY_API_KEY",
        "nebius": "NEBIUS_API_KEY",
    }
    for name, env_var in api_checks.items():
        if os.environ.get(env_var):
            adapters[name] = {"type": "api", "env_var": env_var}
            print(f"  [FOUND] {name} (${env_var} set)")
        else:
            print(f"  [    ] {name} (${env_var} not set)")

    return adapters


def generate_config(adapters: dict, output_path: str = "config.yaml") -> str:
    """Generate a minimal config.yaml based on detected adapters."""
    lines = ['version: "1.0"', ""]

    # CLI tools section
    cli_adapters = {k: v for k, v in adapters.items() if v["type"] == "cli"}
    if cli_adapters:
        lines.append("cli_tools:")
        for name, info in cli_adapters.items():
            cmd = info["command"]
            if name == "claude":
                lines.extend([
                    f"  claude:",
                    f'    command: "claude"',
                    f'    args: ["-p", "--model", "{{model}}", "--settings", \'{{"disableAllHooks": true}}\', "{{prompt}}"]',
                    f"    timeout: 300",
                ])
            elif name == "codex":
                lines.extend([
                    f"  codex:",
                    f'    command: "codex"',
                    f'    args: ["exec", "--skip-git-repo-check", "--sandbox", "workspace-write", "--model", "{{model}}", "{{prompt}}"]',
                    f"    timeout: 300",
                ])
            elif name == "gemini":
                lines.extend([
                    f"  gemini:",
                    f'    command: "gemini"',
                    f'    args: ["-m", "{{model}}", "-p", "{{prompt}}"]',
                    f"    timeout: 300",
                ])
            elif name == "llamacpp":
                lines.extend([
                    f"  llamacpp:",
                    f'    command: "llama-cli"',
                    f'    args: ["-m", "{{model}}", "-p", "{{prompt}}", "-n", "2048", "-c", "4096"]',
                    f"    timeout: 300",
                ])
        lines.append("")

    # HTTP adapters section
    http_adapters = {k: v for k, v in adapters.items() if v["type"] == "http"}
    api_adapters = {k: v for k, v in adapters.items() if v["type"] == "api"}

    if http_adapters or api_adapters:
        lines.append("adapters:")
        for name, info in http_adapters.items():
            lines.extend([
                f"  {name}:",
                f'    type: http',
                f'    base_url: "{info["url"]}"',
                f"    timeout: 300",
                f"    max_retries: 3",
            ])
        if "openrouter" in api_adapters:
            lines.extend([
                f"  openrouter:",
                f'    type: http',
                f'    base_url: "https://openrouter.ai/api/v1"',
                f'    api_key: "${{OPENROUTER_API_KEY}}"',
                f"    timeout: 300",
                f"    max_retries: 3",
            ])
        if "openai" in api_adapters:
            lines.extend([
                f"  openai:",
                f'    type: openai',
                f'    base_url: "https://api.openai.com/v1"',
                f'    api_key: "${{OPENAI_API_KEY}}"',
                f"    timeout: 300",
                f"    max_retries: 3",
            ])
        lines.append("")

    # Defaults
    lines.extend([
        "defaults:",
        '  mode: "quick"',
        "  rounds: 2",
        "  max_rounds: 5",
        "  timeout_per_round: 600",
        "",
        "storage:",
        '  transcripts_dir: "transcripts"',
        '  format: "markdown"',
        "  auto_export: true",
        "",
        "deliberation:",
        "  convergence_detection:",
        "    enabled: true",
        "    semantic_similarity_threshold: 0.85",
        "    divergence_threshold: 0.40",
        "    min_rounds_before_check: 1",
        "    consecutive_stable_rounds: 2",
        "    stance_stability_threshold: 0.80",
        "    response_length_drop_threshold: 0.40",
        "  early_stopping:",
        "    enabled: true",
        "    threshold: 0.66",
        "    respect_min_rounds: true",
        "  convergence_threshold: 0.8",
        "  enable_convergence_detection: true",
        "  file_tree:",
        "    enabled: true",
        "    max_depth: 2",
        "    max_files: 50",
        "  tool_security:",
        "    exclude_patterns:",
        '      - "transcripts/"',
        '      - "transcripts/**"',
        '      - ".git/"',
        '      - ".git/**"',
        '      - "node_modules/"',
        '      - "node_modules/**"',
        '      - ".venv/"',
        '      - "venv/"',
        '      - "__pycache__/"',
        "    max_file_size_bytes: 1048576",
        "  vote_retry:",
        "    enabled: true",
        "    max_retries: 1",
        "    min_response_length: 100",
    ])

    # Web search if Tavily key available
    if "tavily" in api_adapters:
        lines.extend([
            "  web_search:",
            "    enabled: true",
            '    provider: "tavily"',
            '    api_key: "${TAVILY_API_KEY}"',
            "    max_results: 5",
        ])

    # Decision graph
    lines.extend([
        "",
        "decision_graph:",
        "  enabled: true",
        '  db_path: "decision_graph.db"',
        "  context_token_budget: 1000",
        "  tier_boundaries:",
        "    strong: 0.75",
        "    moderate: 0.60",
        "",
        "results:",
        "  auto_open_html: true",
    ])

    config_text = "\n".join(lines) + "\n"

    with open(output_path, "w") as f:
        f.write(config_text)

    return output_path


def main():
    print("=" * 60)
    print("  AI Counsel — Zero-Config Setup Wizard")
    print("=" * 60)
    print()

    # Check Python version
    if sys.version_info < (3, 10):
        print(f"ERROR: Python 3.10+ required (you have {sys.version})")
        sys.exit(1)
    print(f"Python: {sys.version.split()[0]}")

    # Check if config already exists
    config_path = Path("config.yaml")
    if config_path.exists():
        print(f"\nconfig.yaml already exists. Overwrite? [y/N] ", end="")
        if input().strip().lower() != "y":
            print("Aborted.")
            sys.exit(0)

    # Detect adapters
    print("\nDetecting available adapters...")
    adapters = detect_adapters()

    if not adapters:
        print("\nNo adapters found! Install at least one:")
        print("  - Claude CLI: npm install -g @anthropic-ai/claude-code")
        print("  - Ollama: https://ollama.com")
        print("  - OpenRouter: Set OPENROUTER_API_KEY env var")
        sys.exit(1)

    # Generate config
    print(f"\nGenerating config.yaml with {len(adapters)} adapter(s)...")
    output = generate_config(adapters)
    print(f"Config written to: {output}")

    # Summary
    cli_count = sum(1 for v in adapters.values() if v["type"] == "cli")
    http_count = sum(1 for v in adapters.values() if v["type"] in ("http", "api"))
    print(f"\nSetup complete!")
    print(f"  CLI adapters: {cli_count}")
    print(f"  HTTP/API adapters: {http_count}")
    print(f"\nNext steps:")
    print(f"  1. Review config.yaml")
    print(f"  2. Add to your MCP config (.mcp.json or claude_desktop_config.json)")
    print(f"  3. Run: python server.py (or use via MCP)")


if __name__ == "__main__":
    main()
