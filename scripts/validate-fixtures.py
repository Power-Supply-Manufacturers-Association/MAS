#!/usr/bin/env python3
"""Validate the per-record sub-schema fixtures under samples/ (everything that is NOT a
complete MAS document — those are covered by validate-samples.py).

Each samples/ subdirectory maps to the sub-schema its fixtures instantiate; longest
directory prefix wins. Exits non-zero on any failure.
"""
import glob
import json
import os
import sys

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PSMA = os.path.dirname(HERE)

# samples/<prefix>  ->  schema ($id or repo-relative path)
MAP = {
    "inputs/designRequirements":        "schemas/inputs/designRequirements.json",
    # the MAS mirror was retired; the canonical excitation schema lives in PEAS
    "inputs/operatingPointExcitation":  "https://psma.com/peas/inputs/operatingPointExcitation.json",
    "magnetic/bobbin":                  "schemas/magnetic/bobbin.json",
    "magnetic/coil":                    "schemas/magnetic/coil.json",
    "magnetic/core/material":           "schemas/magnetic/core/material.json",
    "magnetic/core/shape":              "schemas/magnetic/core/shape.json",
    "magnetic/core":                    "schemas/magnetic/core.json",
    "magnetic/insulation/material":     "schemas/magnetic/insulation/material.json",
    "magnetic/wire/material":           "schemas/magnetic/wire/material.json",
    # wire fixtures validate against the UNION so the oneOf discriminator is exercised
    "magnetic/wire":                    "schemas/magnetic/wire.json",
}


def load_registry():
    resources = []
    for repo in ("MAS", "PEAS", "CAS", "SAS", "RAS", "AAS", "CTAS", "CONAS"):
        for f in glob.glob(os.path.join(PSMA, repo, "schemas", "**", "*.json"), recursive=True):
            try:
                doc = json.load(open(f))
            except (json.JSONDecodeError, OSError):
                continue
            if "$id" in doc:
                resources.append((doc["$id"], Resource.from_contents(doc)))
    return Registry().with_resources(resources)


def main() -> int:
    os.chdir(HERE)
    registry = load_registry()
    validators = {}

    def validator_for(ref: str) -> Draft202012Validator:
        if ref not in validators:
            if ref.startswith("https://"):
                schema = registry.get_or_retrieve(ref).value.contents
            else:
                schema = json.load(open(ref))
            validators[ref] = Draft202012Validator(schema, registry=registry)
        return validators[ref]

    failed = total = 0
    for path in sorted(glob.glob("samples/**/*.json", recursive=True)):
        rel = os.path.relpath(path, "samples")
        if rel.startswith("complete" + os.sep):
            continue  # complete documents are validate-samples.py's job
        prefix = max((p for p in MAP if rel.startswith(p + os.sep)), key=len, default=None)
        if prefix is None:
            print(f"FAIL {path}: no schema mapping for this fixture directory")
            failed += 1
            continue
        total += 1
        doc = json.load(open(path))
        errors = list(validator_for(MAP[prefix]).iter_errors(doc))
        if errors:
            failed += 1
            print(f"FAIL {path}:")
            for e in errors[:5]:
                print(f"    {list(e.absolute_path)} -> {e.message[:120]}")
        else:
            print(f"  OK  {path}")

    print(f"\n{total - failed}/{total} fixtures valid" + ("" if not failed else f" — {failed} FAILED"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
