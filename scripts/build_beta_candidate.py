#!/usr/bin/env python3
"""Build a deterministic read-only candidate archive, without tags or publication."""

import argparse
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def build(root, output):
    root, output = Path(root), Path(output)
    component = root / "custom_components/ev_charge_manager"
    manifest = json.loads((component / "manifest.json").read_text())
    if manifest["domain"] != "ev_charge_manager" or manifest["version"] != "0.1.0-beta.1":
        raise ValueError("Expected the reviewed proposed v0.1.0-beta.1 manifest")
    members = [
        p
        for p in component.rglob("*")
        if p.is_file()
        and p.suffix in {".py", ".json", ".yaml", ".png"}
        and "__pycache__" not in p.parts
    ]
    members += [
        root / name
        for name in (
            "LICENSE",
            "README.md",
            "hacs.json",
            "docs/beta-installation.md",
            "docs/beta-cutover.md",
            "docs/contracts/price-consumer-v1.md",
            "docs/provider-adapters.md",
            "docs/command-executor.md",
            "docs/measured-history.md",
        )
    ]
    if any(p.is_symlink() for p in members):
        raise ValueError("Candidate archives must not contain symlinked sources")
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w") as archive:
        for path in sorted(members):
            info = ZipInfo(path.relative_to(root).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    with ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError("Candidate ZIP integrity verification failed")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("dist/ev-charge-manager-v0.1.0-beta.1.zip")
    )
    args = parser.parse_args()
    print(build(Path(__file__).resolve().parents[1], args.output))


if __name__ == "__main__":
    main()
