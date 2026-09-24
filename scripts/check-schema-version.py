#!/usr/bin/env python3
"""Fail if schemas/ changed between two commits while VERSION did not bump.

VERSION (repo root) is the single source of truth for the MAS release a document
stamps in its optional top-level `schemaVersion` (PEAS utils.json#/$defs/schemaVersion).

The rule, between a BASE commit and a HEAD commit:
  1. VERSION at HEAD exists and is a SemVer 2.0.0 string.
  2. VERSION at HEAD >= VERSION at BASE (a version never goes backwards).
  3. If anything under schemas/ differs between BASE and HEAD, VERSION at HEAD > VERSION at BASE.
     A document stamped with a release must mean exactly that release's schemas.

Which BASE CI passes (.github/workflows/schema-version.yml):
  * pull_request: the merge base of the PR's base branch and its head, so the PR is judged
    only on its own changes, not on what landed on the base branch meanwhile.
  * push to main: the event's `before` SHA (the previous tip of main), so two PRs that each
    bumped to the same number against the same merge base fail once the second one lands.

BASE without a VERSION file is accepted only as the change that introduces VERSION; that
case is reported explicitly. Every other missing/invalid input (unknown commit, VERSION
missing at HEAD, not SemVer, git failure) exits non-zero with the reason.

Usage (from anywhere inside the repository):
    python3 scripts/check-schema-version.py --base <commit> [--head <commit>]   # --head defaults to HEAD
    python3 scripts/check-schema-version.py --base "$(git merge-base origin/main HEAD)"
"""
import argparse
import subprocess
import sys

from mas_version import parse_version_text, precedence

SCHEMA_DIR = "schemas/"


class CheckError(Exception):
    pass


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise CheckError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def resolve(rev: str) -> str:
    return git("rev-parse", "--verify", f"{rev}^{{commit}}").strip()


def has_path(commit: str, path: str) -> bool:
    """Whether `path` exists in `commit`'s tree (an explicit query, not a failed read)."""
    return git("ls-tree", "--name-only", commit, "--", path).strip() == path


def version_at(commit: str) -> str:
    return parse_version_text(git("show", f"{commit}:VERSION"), f"VERSION at {commit[:12]}")


def check(base_rev: str, head_rev: str) -> str:
    base, head = resolve(base_rev), resolve(head_rev)
    if not has_path(head, "VERSION"):
        raise CheckError(f"VERSION does not exist at {head_rev} ({head[:12]}); it holds the current MAS release")
    head_version = version_at(head)
    changed = git("diff", "--name-only", base, head, "--", SCHEMA_DIR).split()

    if not has_path(base, "VERSION"):
        return (f"OK: VERSION {head_version} is introduced by this change (absent at {base_rev} {base[:12]}); "
                f"{len(changed)} schema file(s) changed")

    base_version = version_at(base)
    if precedence(head_version) < precedence(base_version):
        raise CheckError(f"VERSION went backwards: {base_version} at {base_rev} -> {head_version} at {head_rev}")
    if changed and precedence(head_version) == precedence(base_version):
        raise CheckError(f"{len(changed)} file(s) under {SCHEMA_DIR} changed between {base_rev} ({base[:12]}) and "
                         f"{head_rev} ({head[:12]}) but VERSION is still {head_version}; bump it "
                         f"(MAJOR/MINOR/PATCH per CHANGELOG.md). First: {changed[0]}")
    return (f"OK: VERSION {base_version} -> {head_version} between {base_rev} ({base[:12]}) and "
            f"{head_rev} ({head[:12]}); {len(changed)} schema file(s) changed")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True, help="commit to compare against (PR merge base / push `before`)")
    ap.add_argument("--head", default="HEAD", help="commit being checked (default: HEAD)")
    args = ap.parse_args()
    try:
        print(check(args.base, args.head))
    except (CheckError, ValueError) as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
