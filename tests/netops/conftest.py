"""Shared helpers for NetOps tests: load skill modules by file path (as the SRE Agent sandbox does)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "netops"
SKILLS = PLUGIN / "skills"


def load_skill_module(skill, filename, name=None):
    path = SKILLS / skill / filename
    spec = importlib.util.spec_from_file_location(name or f"t_{skill}_{path.stem}".replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def root():
    return ROOT
