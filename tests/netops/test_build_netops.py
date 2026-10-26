"""Generated NetOps content must match its source of truth (registry.mjs + specialists/**)."""

import shutil
import subprocess

import pytest

from conftest import ROOT


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_build_netops_check_passes():
    proc = subprocess.run(["node", "scripts/netops/build-netops.mjs", "--check"], cwd=ROOT,
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr