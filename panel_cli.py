#!/usr/bin/env python3
"""AI Counsel Panel Marketplace CLI.

Install, list, and manage panel presets for deliberation.

Usage:
    python panel_cli.py list                    # List installed panels
    python panel_cli.py info <panel-name>       # Show panel details
    python panel_cli.py install <url-or-path>   # Install a panel from file/URL
    python panel_cli.py export <panel-name>     # Export a panel to shareable YAML
"""
import argparse
import json
import sys
from pathlib import Path

import yaml


PANELS_FILE = Path(__file__).parent / "panels.yaml"


def load_panels() -> dict:
    """Load all panels from panels.yaml."""
    if not PANELS_FILE.exists():
        return {}
    with open(PANELS_FILE) as f:
        data = yaml.safe_load(f)
    return data.get("panels", {})


def save_panels(panels: dict):
    """Save panels back to panels.yaml."""
    with open(PANELS_FILE, "w") as f:
        yaml.dump({"panels": panels}, f, default_flow_style=False, sort_keys=False)


def cmd_list(args):
    """List all installed panels."""
    panels = load_panels()
    if not panels:
        print("No panels installed.")
        return

    print(f"{'Name':<25} {'Participants':<5} {'Rounds':<7} {'Mode':<12} Description")
    print("-" * 90)
    for name, panel in panels.items():
        participants = len(panel.get("participants", []))
        rounds = panel.get("rounds", 2)
        mode = panel.get("mode", "quick")
        desc = panel.get("description", "")[:40]
        print(f"{name:<25} {participants:<5} {rounds:<7} {mode:<12} {desc}")

    print(f"\n{len(panels)} panel(s) installed")


def cmd_info(args):
    """Show detailed info about a panel."""
    panels = load_panels()
    name = args.name

    if name not in panels:
        print(f"Panel '{name}' not found. Run 'list' to see available panels.")
        sys.exit(1)

    panel = panels[name]
    print(f"Panel: {name}")
    print(f"Description: {panel.get('description', 'N/A')}")
    print(f"Mode: {panel.get('mode', 'quick')}")
    print(f"Rounds: {panel.get('rounds', 2)}")
    print(f"\nParticipants ({len(panel.get('participants', []))}):")

    for i, p in enumerate(panel.get("participants", []), 1):
        persona = p.get("persona", "")
        model = p.get("model", "default")
        cli = p.get("cli", "unknown")
        effort = p.get("reasoning_effort", "")

        line = f"  {i}. {model}@{cli}"
        if persona:
            line += f" — {persona}"
        if effort:
            line += f" (effort: {effort})"
        print(line)

        if p.get("system_prompt"):
            prompt_preview = p["system_prompt"][:100].replace("\n", " ")
            print(f"     Prompt: {prompt_preview}...")


def cmd_install(args):
    """Install a panel from a YAML file or URL."""
    source = args.source
    panels = load_panels()

    # Load panel from file
    source_path = Path(source)
    if source_path.exists():
        with open(source_path) as f:
            new_data = yaml.safe_load(f)
    elif source.startswith("http"):
        try:
            import httpx
            resp = httpx.get(source, timeout=10, follow_redirects=True)
            resp.raise_for_status()
            new_data = yaml.safe_load(resp.text)
        except Exception as e:
            print(f"Failed to fetch panel from URL: {e}")
            sys.exit(1)
    else:
        print(f"Source not found: {source}")
        sys.exit(1)

    # Support both single panel and multi-panel formats
    if "panels" in new_data:
        new_panels = new_data["panels"]
    elif "participants" in new_data:
        # Single panel — use filename as name
        panel_name = source_path.stem if source_path.exists() else "imported-panel"
        new_panels = {panel_name: new_data}
    else:
        print("Invalid panel format. Expected 'panels' dict or single panel with 'participants'.")
        sys.exit(1)

    # Install
    installed = []
    for name, panel in new_panels.items():
        if name in panels:
            print(f"  Updating: {name}")
        else:
            print(f"  Installing: {name}")
        panels[name] = panel
        installed.append(name)

    save_panels(panels)
    print(f"\nInstalled {len(installed)} panel(s): {', '.join(installed)}")


def cmd_export(args):
    """Export a panel to a shareable YAML file."""
    panels = load_panels()
    name = args.name

    if name not in panels:
        print(f"Panel '{name}' not found.")
        sys.exit(1)

    output = args.output or f"{name}.panel.yaml"
    panel_data = {name: panels[name]}

    with open(output, "w") as f:
        yaml.dump({"panels": panel_data}, f, default_flow_style=False, sort_keys=False)

    print(f"Exported '{name}' to {output}")


def main():
    parser = argparse.ArgumentParser(
        description="AI Counsel Panel Marketplace CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="List installed panels")

    info_parser = sub.add_parser("info", help="Show panel details")
    info_parser.add_argument("name", help="Panel name")

    install_parser = sub.add_parser("install", help="Install a panel from file or URL")
    install_parser.add_argument("source", help="Path to .panel.yaml file or URL")

    export_parser = sub.add_parser("export", help="Export a panel to shareable YAML")
    export_parser.add_argument("name", help="Panel name to export")
    export_parser.add_argument("-o", "--output", help="Output file path")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "info":
        cmd_info(args)
    elif args.command == "install":
        cmd_install(args)
    elif args.command == "export":
        cmd_export(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
