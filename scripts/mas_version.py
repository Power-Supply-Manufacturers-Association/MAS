"""SemVer 2.0.0 parsing/precedence and the MAS release number from VERSION.

Shared by scripts/migrate-to-1.0.py (which stamps schemaVersion) and
scripts/check-schema-version.py (which enforces the VERSION bump). Every
malformed or missing input raises; nothing is defaulted.
"""
import re
from pathlib import Path

# The official SemVer 2.0.0 regex (semver.org, numbered-capture-group variant); the same
# pattern as PEAS utils.json#/$defs/schemaVersion.
SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)

# VERSION sits at the repository root, one level above scripts/.
VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"


def precedence(version: str):
    """Sort key implementing SemVer 2.0.0 precedence (build metadata ignored).

    Raises ValueError when `version` is not a SemVer 2.0.0 string.
    """
    if not isinstance(version, str):
        raise ValueError(f"not a SemVer 2.0.0 string: {version!r}")
    m = SEMVER.match(version)
    if not m:
        raise ValueError(f"not a SemVer 2.0.0 string: {version!r}")
    core = tuple(int(m.group(i)) for i in (1, 2, 3))
    if m.group(4) is None:
        return core, (1,)  # a release outranks any of its pre-releases
    ids = tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in m.group(4).split("."))
    return core, (0, ids)


def parse_version_text(text: str, source: str) -> str:
    """The SemVer string held in a VERSION file's text; raises if it is not exactly one."""
    version = text.strip()
    if not SEMVER.match(version):
        raise ValueError(f"{source}: {version!r} is not a SemVer 2.0.0 string")
    return version


def current_version() -> str:
    """The current MAS release, read from the repository's VERSION file. Raises if missing or invalid."""
    if not VERSION_FILE.is_file():
        raise FileNotFoundError(f"{VERSION_FILE} does not exist; it holds the current MAS release")
    return parse_version_text(VERSION_FILE.read_text(), str(VERSION_FILE))
