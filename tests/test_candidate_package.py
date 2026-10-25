"""An installable source ZIP, not a publication or production deployment."""

import json
import runpy
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).parents[1]


def test_candidate_archive_is_deterministic_and_contains_complete_integration(tmp_path):
    build = runpy.run_path(str(ROOT / "scripts/build_beta_candidate.py"))["build"]
    a = build(ROOT, tmp_path / "a.zip")
    b = build(ROOT, tmp_path / "b.zip")
    assert a.read_bytes() == b.read_bytes()
    with ZipFile(a) as archive:
        names = archive.namelist()
        assert not any(
            "__pycache__" in name or ".storage" in name or name.endswith(".pyc") for name in names
        )
        for name in names:
            if name.endswith(".py"):
                compile(archive.read(name), name, "exec")
        manifest = json.loads(archive.read("custom_components/ev_charge_manager/manifest.json"))
        assert manifest["version"] == "0.1.0-beta.1"
        assert "custom_components/ev_charge_manager/journal.py" in names
        assert "custom_components/ev_charge_manager/providers.py" in names
        assert "custom_components/ev_charge_manager/config_flow.py" in names
        assert "docs/beta-cutover.md" in names and "hacs.json" in names
