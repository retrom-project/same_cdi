#!/usr/bin/env python3
"""Build and describe immutable EmulatorJS core assets from this checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--tag", required=True)
args = parser.parse_args()
fork = json.loads((ROOT / "retrom-fork.json").read_text())
baseline = fork["defaultBranch"].split("/", 1)[1]
if not re.fullmatch(r"retrom-core-" + re.escape(baseline) + r"-r[1-9][0-9]*(?:-rc\.[1-9][0-9]*)?", args.tag):
    raise SystemExit("RETROM_CORE_RELEASE_TAG_INVALID")
commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
archive = next(name for name in fork["releaseAssets"] if name.endswith("-wasm.data"))
core = archive.removesuffix("-wasm.data")
license_name = next(name for name in fork["releaseAssets"] if name in ("LICENSE", "COPYING"))
subprocess.run([str(ROOT / ".github/rpg-runtime/build-web.sh"), str(args.output)], check=True)
expected = set(fork["releaseAssets"]) - {"rpg-runtime-release.json"}
if {p.name for p in args.output.iterdir()} != expected:
    raise SystemExit("RETROM_CORE_RELEASE_ASSETS_INVALID")
with tempfile.TemporaryDirectory() as temporary:
    subprocess.run(["7z", "x", "-bd", "-bso0", "-bsp0", f"-o{temporary}", str(args.output / archive)], check=True)
    extracted = Path(temporary)
    members = {f"{core}_libretro.js", f"{core}_libretro.wasm", "core.json", "build.json", "license.txt"}
    if {p.name for p in extracted.iterdir()} != members or any(not p.is_file() or p.is_symlink() for p in extracted.iterdir()):
        raise SystemExit("RETROM_CORE_ARCHIVE_INVALID")
    if (extracted / f"{core}_libretro.wasm").read_bytes()[:8] != b"\0asm\x01\0\0\0":
        raise SystemExit("RETROM_CORE_WASM_INVALID")
    if json.loads((extracted / "core.json").read_text())["name"] != core:
        raise SystemExit("RETROM_CORE_ARCHIVE_INVALID")
    if not (extracted / "license.txt").read_bytes() == (args.output / license_name).read_bytes() == (ROOT / license_name).read_bytes():
        raise SystemExit("RETROM_CORE_LICENSE_INVALID")
assets = [{"filename": name, "sizeBytes": (args.output / name).stat().st_size,
           "observedSha256": hashlib.sha256((args.output / name).read_bytes()).hexdigest()} for name in sorted(expected)]
metadata = {"schemaVersion": 1, "repository": fork["forkRepository"], "tag": args.tag,
            "commit": commit, "adapterAbi": fork["adapterAbi"], "assets": assets,
            "digestPolicy": "OBSERVED_CACHE_INTEGRITY_ONLY"}
(args.output / "rpg-runtime-release.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
