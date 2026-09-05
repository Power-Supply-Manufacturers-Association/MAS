#!/usr/bin/env python3
"""Verify that a copy of MAS's ``data/*.ndjson`` is the canonical one.

WHY THIS EXISTS
---------------
MAS's component database is duplicated into every consumer — as submodules, as bare
clones, and compiled into engine binaries. On one developer machine in September 2026
there were 24 copies nested up to four levels deep, and four of them had silently gone
stale. Each failed a *different* way, which is why no single obvious check is enough:

1. Shared git dir. Two directories resolved ``--git-common-dir`` to the same module
   gitdir, so one working copy held 707 materials against a HEAD blob of 1058 and
   ``git status`` reported it CLEAN. A status check calls this healthy.

2. Count-equal, content-different. A ``cores_stock.ndjson`` had the canonical 1573
   records, but 151 of them differed — a different Digi-Key snapshot. A record count
   calls this healthy.

3. Fetch that silently does nothing. A clone with an ``https://`` remote ignored an
   ``sshCommand`` override; the fetch was a no-op that reported success and exited 0,
   so the revision never moved and nothing warned. A revision check calls this healthy.

4. Remote pointing at another repository. A vendored ``MAS`` directory whose ``origin``
   was ``PyMKF.git``: fetching ``origin/main`` can never reach canonical MAS at all.

The only check that catches all four is a per-file CONTENT HASH compared against
CANONICAL-CURRENT — not against the copy's own revision, which modes 3 and 4 leave
looking perfectly self-consistent.

USAGE
-----
    # Is this copy canonical? (writes nothing, exits 1 on drift)
    scripts/check-data-sync.py

    # Check some other copy
    scripts/check-data-sync.py --path /path/to/consumer/MAS

    # Regenerate the manifest — run this in the SAME commit that changes data/
    scripts/check-data-sync.py --write

Exit codes: 0 in sync, 1 drift detected, 2 the manifest itself is missing/unreadable.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

MANIFEST_NAME = "MANIFEST.sha256"


def data_files(data_dir: Path) -> list[Path]:
    """Every NDJSON in ``data/``, sorted so the manifest is reproducible."""
    return sorted(data_dir.glob("*.ndjson"))


def sha256_of(path: Path) -> str:
    """Stream the file — cores.ndjson is ~8 MB and there is no reason to hold it."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# AN UNFETCHED GIT-LFS FILE IS A 134-BYTE STUB THAT HASHES PERFECTLY WELL, and that is exactly
# the failure this manifest exists to catch. data/advanced_core_materials.ndjson is stored in LFS;
# on a checkout where it was never fetched, the pointer's own sha went into the manifest at
# 198d44e and every run since has reported "in sync" while the file was a stub. A hash cannot tell
# you WHAT it hashed, so the content has to be recognised. ABT #1019.
_LFS_MAGIC = b"version https://git-lfs.github.com/spec/v1"


def is_lfs_pointer(path: Path) -> bool:
    """True if this file is an unfetched git-lfs pointer rather than the real content."""
    try:
        with path.open("rb") as handle:
            return handle.read(len(_LFS_MAGIC)) == _LFS_MAGIC
    except OSError:
        return False


def build_manifest(data_dir: Path) -> dict[str, str]:
    return {path.name: sha256_of(path) for path in data_files(data_dir)}


def read_manifest(manifest_path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for raw in manifest_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, name = line.partition("  ")
        if not digest or not name:
            raise ValueError(f"malformed manifest line: {raw!r}")
        entries[name] = digest
    return entries


def write_manifest(manifest_path: Path, manifest: dict[str, str]) -> None:
    body = [
        "# sha256 of every data/*.ndjson at this revision.",
        "# Regenerate with scripts/check-data-sync.py --write in the same commit that",
        "# changes data/, so a consumer can always tell a genuine copy from a stale one.",
    ]
    body += [f"{digest}  {name}" for name, digest in sorted(manifest.items())]
    manifest_path.write_text("\n".join(body) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--path", type=Path, default=Path(__file__).resolve().parent.parent,
                        help="MAS checkout to verify (default: the one containing this script)")
    parser.add_argument("--write", action="store_true", help="regenerate the manifest instead of checking it")
    parser.add_argument("--canonical", type=Path, default=None,
                        help="compare against ANOTHER checkout's manifest (or a manifest file). This is the "
                             "mode consumers want: a stale-but-self-consistent copy passes a self-check, "
                             "because its own manifest went stale with it.")
    parser.add_argument("--quiet", action="store_true", help="print nothing when in sync")
    args = parser.parse_args()

    data_dir = args.path / "data"
    if not data_dir.is_dir():
        print(f"error: no data/ directory under {args.path}", file=sys.stderr)
        return 2

    manifest_path = data_dir / MANIFEST_NAME
    actual = build_manifest(data_dir)

    # Which manifest are we judged against? Its own (integrity), or canonical's
    # (integrity AND freshness). Modes 3 and 4 above leave a copy perfectly
    # self-consistent, so only the canonical comparison catches them.
    if args.canonical is not None:
        candidate = args.canonical
        if candidate.is_dir():
            candidate = candidate / "data" / MANIFEST_NAME
        manifest_path = candidate

    pointers = sorted(p.name for p in data_files(data_dir) if is_lfs_pointer(p))

    if args.write:
        # REFUSING IS THE POINT. Writing a pointer's sha teaches the manifest that a stub is
        # genuine, and every later check then passes while the data is absent -- which is how
        # 198d44e came to certify advanced_core_materials.ndjson. Fetch first.
        if pointers:
            print(f"error: refusing to write the manifest -- these are unfetched git-lfs pointers, "
                  f"not data:\n    " + "\n    ".join(pointers) +
                  "\n  Run `git lfs pull` first. Writing now would record the pointer's own hash "
                  "and make every future check pass on a stub.", file=sys.stderr)
            return 2
        write_manifest(manifest_path, actual)
        print(f"wrote {manifest_path} ({len(actual)} files)")
        return 0

    if not manifest_path.is_file():
        if args.canonical is None:
            print(f"error: {manifest_path} is missing. This copy predates the manifest; compare it against "
                  f"canonical instead:\n    {Path(__file__).name} --path {args.path} --canonical /path/to/canonical/MAS",
                  file=sys.stderr)
        else:
            print(f"error: no manifest at {manifest_path}", file=sys.stderr)
        return 2

    expected = read_manifest(manifest_path)

    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(name for name in set(expected) & set(actual) if expected[name] != actual[name])

    if pointers and not (missing or extra or changed):
        # The hashes agree, so the copy is self-consistent -- with a stub. Say so plainly rather
        # than "in sync", which is what this script was doing before ABT #1019.
        print(f"NOT USABLE in {args.path}", file=sys.stderr)
        for name in pointers:
            print(f"  unfetched git-lfs pointer: {name} "
                  f"({(data_dir / name).stat().st_size} bytes, not the real content)", file=sys.stderr)
        print("\nThe manifest matches, because the pointer's own hash was recorded in it. "
              "Run `git lfs pull`, then re-run with --write to record the real content.",
              file=sys.stderr)
        return 1

    if not (missing or extra or changed):
        if not args.quiet:
            against = "canonical" if args.canonical is not None else MANIFEST_NAME
            print(f"in sync: {len(actual)} data files match {against}")
        return 0

    print(f"DRIFT in {args.path}", file=sys.stderr)
    for name in changed:
        # Line counts are not the check, but they make the report readable.
        lines = sum(1 for _ in (data_dir / name).open("rb"))
        print(f"  changed: {name}  (has {lines} records; sha {actual[name][:12]}, expected {expected[name][:12]})", file=sys.stderr)
    for name in missing:
        print(f"  missing: {name}", file=sys.stderr)
    for name in extra:
        print(f"  untracked by the manifest: {name}", file=sys.stderr)
    print("\nThis copy is NOT canonical. Do not resolve component data against it.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
