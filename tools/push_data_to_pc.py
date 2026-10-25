#!/usr/bin/env python3
"""Push the files the results DB is built from to the deploy PC, then rebuild it.

deploy.yml ships code only. Data never goes through git (the repo is public and
the datasets carry their own licences), so this is the data channel: one-way,
from the machine that holds the finals to the PC, over SSH.

    .venv/bin/python tools/push_data_to_pc.py             # dry run: what would change
    .venv/bin/python tools/push_data_to_pc.py --execute   # copy, re-hash, rebuild the DB

The list is exactly what the backend reads: the registry's dataset sources
(seed_registries.dataset_docs) plus migrate_results_to_mongo.migration_sources(),
minus files tracked in git (deploy brings those). Afterwards every listed file
on the PC is byte-identical to this machine's copy. A file that differs there is
first backed up under %USERPROFILE%\\vmlu-push-backup\\<stamp>\\ on the PC;
nothing else on the PC is touched or deleted. --execute then runs
tools/seed_db.ps1 there (seed -> migrate -> verify) unless --no-seed.

Target: --host user@pc, or VMLU_PC_SSH in .env. Key-based SSH only (BatchMode).
"""
from __future__ import annotations

import argparse
import base64
import os
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from code_benchmark.migrate_results_to_mongo import migration_sources
from code_benchmark.seed_registries import dataset_docs, sha256_file

# Diagnostic review packets (AI suggestions, adjudication drafts) never go to the
# shared PC: the independent review done there must stay blind to them.
NEVER_PUSH = ("all_res/diagnostic",)
BATCH = 80  # paths per remote call, far below the 32K Windows command-line cap


def local_files() -> dict[str, str]:
    """{repo-relative posix path: sha256} of every untracked file the DB reads."""
    files = {doc["source_file"]: doc["source_sha256"] for doc in dataset_docs()}
    for path in migration_sources():
        files.setdefault(path.as_posix(), sha256_file(path))
    tracked = subprocess.run(["git", "ls-files", "-z", "--", *files], cwd=ROOT, check=True,
                             capture_output=True).stdout.decode("utf-8").split("\0")
    files = {p: h for p, h in files.items() if p not in set(tracked)}
    leaked = [p for p in files if p.startswith(NEVER_PUSH)]
    if leaked:
        raise SystemExit(f"Error: refusing to push diagnostic review files: {leaked}")
    return files


def ps_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def ps_array(items: list[str]) -> str:
    return "@(" + ", ".join(ps_quote(i) for i in items) + ")"


def run_ps(host: str, script: str, *, capture: bool = True) -> str:
    """Run a PowerShell script on the PC, whose OpenSSH login shell is Windows
    PowerShell 5.1. -EncodedCommand sidesteps the ssh -> login shell -> powershell
    quoting layers; a failure anywhere is a non-zero exit, never partial output."""
    prelude = "[Console]::OutputEncoding = [Text.Encoding]::UTF8\n$ProgressPreference = 'SilentlyContinue'\n"
    encoded = base64.b64encode((prelude + script).encode("utf-16-le")).decode("ascii")
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", host,
         f"powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand {encoded}"],
        stdout=subprocess.PIPE if capture else None, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise SystemExit(f"Error: PowerShell on {host} exited {proc.returncode}")
    return proc.stdout or ""


def remote_hashes(host: str, root: str, paths: list[str]) -> dict[str, str]:
    """{path: sha256} for the listed paths that exist under `root` on the PC."""
    out: dict[str, str] = {}
    for i in range(0, len(paths), BATCH):
        script = f"""$root = {ps_quote(root)}
if (-not (Test-Path -LiteralPath $root -PathType Container)) {{ throw "no directory $root" }}
foreach ($rel in {ps_array(paths[i:i + BATCH])}) {{
    $p = Join-Path $root ($rel -replace '/', '\\')
    if (Test-Path -LiteralPath $p -PathType Leaf) {{
        '{{0}} {{1}}' -f (Get-FileHash -Algorithm SHA256 -LiteralPath $p).Hash.ToLower(), $rel
    }}
}}
"""
        for line in run_ps(host, script).splitlines():
            digest, _, rel = line.strip().partition(" ")
            if rel:
                out[rel] = digest
    return out


def copy_to_pc(host: str, root: str, paths: list[str], replace: list[str], stamp: str) -> None:
    """Ship `paths` in one tar and unpack it over `root`; back up `replace` first."""
    tar_name = f"vmlu-push-{stamp}.tar"
    with tempfile.TemporaryDirectory() as td:
        tar_path = Path(td) / tar_name
        with tarfile.open(tar_path, "w") as tar:
            for rel in paths:
                tar.add(ROOT / rel, arcname=rel)
        subprocess.run(["scp", "-q", "-o", "BatchMode=yes", str(tar_path), f"{host}:{tar_name}"], check=True)
    run_ps(host, f"""$root = {ps_quote(root)}
$tar = Join-Path $HOME {ps_quote(tar_name)}
$backup = Join-Path $HOME {ps_quote("vmlu-push-backup/" + stamp)}
foreach ($rel in {ps_array(replace)}) {{
    $dst = Join-Path $backup ($rel -replace '/', '\\')
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) | Out-Null
    Copy-Item -LiteralPath (Join-Path $root ($rel -replace '/', '\\')) -Destination $dst
}}
tar -xf $tar -C $root
if ($LASTEXITCODE -ne 0) {{ throw "tar -xf failed (exit $LASTEXITCODE)" }}
Remove-Item -LiteralPath $tar
""")


def rebuild_db(host: str, root: str) -> None:
    run_ps(host, f"""$seed = Join-Path {ps_quote(root)} 'tools\\seed_db.ps1'
if (-not (Test-Path -LiteralPath $seed)) {{ throw "missing $seed - deploy the commit that adds it first" }}
& $seed
exit $LASTEXITCODE
""", capture=False)


def main() -> None:
    ap = argparse.ArgumentParser(description="Push the results-DB source files to the deploy PC "
                                             "and rebuild the DB there (dry run by default).")
    ap.add_argument("--host", help="SSH target user@pc (default: VMLU_PC_SSH from .env)")
    ap.add_argument("--remote-root", default="C:\\vmlu", help="repo clone on the PC (default: C:\\vmlu)")
    ap.add_argument("--execute", action="store_true", help="copy the files and rebuild the DB")
    ap.add_argument("--no-seed", action="store_true", help="with --execute: copy only")
    args = ap.parse_args()
    os.chdir(ROOT)  # dataset_docs() and migration_sources() resolve repo-relative paths
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    host = args.host or os.environ.get("VMLU_PC_SSH")
    if not host:
        raise SystemExit("Error: pass --host user@pc or set VMLU_PC_SSH in .env")

    local = local_files()
    remote = remote_hashes(host, args.remote_root, list(local))
    missing = [p for p in local if p not in remote]
    differ = [p for p in local if p in remote and remote[p] != local[p]]
    print(f"{len(local)} files feed the results DB; on {host}:{args.remote_root}")
    print(f"  identical {len(local) - len(missing) - len(differ)}, missing {len(missing)}, "
          f"differ {len(differ)} (backed up on the PC, then replaced)")
    for p in missing:
        print(f"    + {p}")
    for p in differ:
        print(f"    ~ {p}")
    if not args.execute:
        size = sum((ROOT / p).stat().st_size for p in missing + differ)
        print(f"dry run; --execute copies {size / 1e6:.1f} MB"
              + ("" if args.no_seed else " and rebuilds the DB"))
        return
    if missing or differ:
        copy_to_pc(host, args.remote_root, missing + differ, differ, datetime.now().strftime("%Y%m%d-%H%M%S"))
        after = remote_hashes(host, args.remote_root, list(local))
        bad = [p for p in local if after.get(p) != local[p]]
        if bad:
            raise SystemExit(f"Error: {len(bad)} files still differ on the PC after the copy: {bad[:5]}")
        print(f"copied {len(missing) + len(differ)} files; all {len(local)} identical on the PC")
    if not args.no_seed:
        rebuild_db(host, args.remote_root)


if __name__ == "__main__":
    main()
