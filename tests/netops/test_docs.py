"""Docs wiring: onboarding paths exist and are linked from the READMEs."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ONBOARDING = ROOT / "docs" / "netops" / "ONBOARDING.md"
PLUGIN_README = ROOT / "plugins" / "netops" / "README.md"


def test_onboarding_has_both_install_paths():
    text = ONBOARDING.read_text(encoding="utf-8")
    assert "## Option A: Automated" in text
    assert "## Option B: Manual (portal)" in text
    assert "## Least-privilege RBAC" in text


def test_readmes_link_onboarding_and_plugin():
    root = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "plugins/netops/README.md" in root
    assert "docs/netops/ONBOARDING.md" in root
    plugin = PLUGIN_README.read_text(encoding="utf-8")
    assert "../../docs/netops/ONBOARDING.md" in plugin


def test_plugin_readme_lists_every_skill():
    plugin = PLUGIN_README.read_text(encoding="utf-8")
    skills = sorted(p.name for p in (ROOT / "plugins" / "netops" / "skills").iterdir() if p.is_dir())
    assert len(skills) == 10
    for name in skills:
        assert f"`{name}`" in plugin, name


def test_plugin_readme_never_suggests_write_roles():
    plugin = PLUGIN_README.read_text(encoding="utf-8")
    assert "Network Contributor is **not** required" in plugin
    assert "Analysis only — verify against vendor documentation before applying." in plugin
