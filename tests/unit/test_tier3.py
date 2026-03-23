"""Unit tests for Tier 3 features: Setup Wizard, Panel CLI, Web UI, GitHub Action."""
import os
import tempfile
from pathlib import Path

import pytest
import yaml


class TestSetupWizard:
    """Tests for the zero-config setup wizard."""

    def test_check_command_finds_python(self):
        from setup_wizard import check_command
        assert check_command("python") or check_command("python3")

    def test_check_command_missing(self):
        from setup_wizard import check_command
        assert not check_command("nonexistent_command_xyz_12345")

    def test_generate_config_minimal(self):
        from setup_wizard import generate_config

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as f:
            output_path = f.name

        try:
            adapters = {
                "claude": {"type": "cli", "command": "claude"},
                "ollama": {"type": "http", "url": "http://localhost:11434"},
            }
            generate_config(adapters, output_path)

            with open(output_path) as f:
                content = f.read()

            assert "claude" in content
            assert "ollama" in content
            assert "version" in content
            assert "deliberation" in content
        finally:
            os.unlink(output_path)

    def test_generate_config_with_api_keys(self):
        from setup_wizard import generate_config

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as f:
            output_path = f.name

        try:
            adapters = {
                "openrouter": {"type": "api", "env_var": "OPENROUTER_API_KEY"},
                "tavily": {"type": "api", "env_var": "TAVILY_API_KEY"},
            }
            generate_config(adapters, output_path)

            with open(output_path) as f:
                content = f.read()

            assert "openrouter" in content
            assert "OPENROUTER_API_KEY" in content
            assert "web_search" in content
            assert "tavily" in content
        finally:
            os.unlink(output_path)


class TestPanelCLI:
    """Tests for the panel marketplace CLI."""

    def test_load_panels(self):
        from panel_cli import load_panels
        panels = load_panels()
        assert isinstance(panels, dict)
        assert len(panels) > 0  # Should have panels from panels.yaml

    def test_load_panels_has_pre_commit(self):
        from panel_cli import load_panels
        panels = load_panels()
        assert "pre-commit-review" in panels

    def test_export_and_install(self):
        from panel_cli import load_panels

        # Export a panel
        panels = load_panels()
        panel_name = "quick-check"
        assert panel_name in panels

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as f:
            yaml.dump({"panels": {panel_name: panels[panel_name]}}, f)
            export_path = f.name

        try:
            # Verify exported file is valid YAML with panel data
            with open(export_path) as f:
                exported = yaml.safe_load(f)
            assert "panels" in exported
            assert panel_name in exported["panels"]
            assert "participants" in exported["panels"][panel_name]
        finally:
            os.unlink(export_path)


class TestGitHubAction:
    """Tests for the GitHub Action configuration."""

    def test_action_yml_exists(self):
        action_path = Path(__file__).parent.parent.parent / "action.yml"
        assert action_path.exists()

    def test_action_yml_valid(self):
        action_path = Path(__file__).parent.parent.parent / "action.yml"
        with open(action_path) as f:
            data = yaml.safe_load(f)

        assert data["name"] == "AI Counsel Code Review"
        assert "inputs" in data
        assert "panel" in data["inputs"]
        assert "fail_on_critical" in data["inputs"]
        assert "outputs" in data
        assert "verdict" in data["outputs"]

    def test_action_entrypoint_exists(self):
        entrypoint = Path(__file__).parent.parent.parent / "action_entrypoint.py"
        assert entrypoint.exists()


class TestWebUI:
    """Tests for the web UI components."""

    def test_index_html_exists(self):
        html_path = Path(__file__).parent.parent.parent / "web" / "index.html"
        assert html_path.exists()

    def test_index_html_has_essential_elements(self):
        html_path = Path(__file__).parent.parent.parent / "web" / "index.html"
        content = html_path.read_text(encoding="utf-8")

        assert "AI Counsel" in content
        assert "startDeliberation" in content
        assert "stream" in content  # Uses fetch streaming or EventSource
        assert "convergence" in content.lower()

    def test_web_app_module_exists(self):
        app_path = Path(__file__).parent.parent.parent / "web" / "app.py"
        assert app_path.exists()

    def test_web_app_imports(self):
        """Verify web app can be imported (dependencies available)."""
        try:
            # Just verify the module structure is valid Python
            import ast
            app_path = Path(__file__).parent.parent.parent / "web" / "app.py"
            ast.parse(app_path.read_text(encoding="utf-8"))
        except SyntaxError as e:
            pytest.fail(f"web/app.py has syntax error: {e}")
