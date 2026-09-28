#!/usr/bin/env python3
"""Magnetic Blade Runner gate for data/core_materials.ndjson (+ advanced_core_materials.ndjson).

Runs MKF's physics validator (PyOpenMagnetics.validate_all_materials) over the core-material data
and fails (exit 1) on ANY IMPOSSIBLE finding, whether or not the change under test introduced it:
physically impossible material data may not sit in MAS. SUSPICIOUS findings are printed, never
fatal.

Usage:
  python3 scripts/check-material-physics.py --data-dir data
The dir holds core_materials.ndjson and, optionally, advanced_core_materials.ndjson (the real
file, not a git-LFS pointer).
"""
import argparse
import os
import sys

import PyOpenMagnetics


def run(data_dir):
    core = os.path.join(data_dir, "core_materials.ndjson")
    advanced = os.path.join(data_dir, "advanced_core_materials.ndjson")
    if os.path.exists(advanced):
        with open(advanced, "rb") as f:
            if f.read(40).startswith(b"version https://git-lfs"):
                sys.exit(f"{advanced} is a git-LFS pointer: check out with lfs: true")
    else:
        advanced = ""
    return PyOpenMagnetics.validate_all_materials(core, advanced)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    args = parser.parse_args()

    summary = run(args.data_dir)
    print(f"Magnetic Blade Runner: {summary['records']} materials, {summary['invalid']} IMPOSSIBLE, "
          f"{summary['recordsWithSuspicious']} with SUSPICIOUS findings, {summary['unclassified']} unclassified")
    if "provenance" in summary:
        print(summary["provenance"])
    for code, counts in sorted(summary["findingsByCode"].items()):
        print(f"  {code}: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))

    print("\nSUSPICIOUS:")
    for f in summary["suspicious"]:
        print(f"  [{f['code']}] {f['reference']}: {f['message']}")
    if summary["impossible"]:
        print(f"\nFAIL: {len(summary['impossible'])} IMPOSSIBLE finding(s):")
        for f in sorted(summary["impossible"], key=lambda f: (f["reference"], f["code"])):
            print(f"  [{f['code']}] {f['reference']}: {f['message']}")
        return 1
    print("\nOK: no IMPOSSIBLE finding")
    return 0


if __name__ == "__main__":
    sys.exit(main())
