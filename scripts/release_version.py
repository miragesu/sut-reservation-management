"""Validate a Docker-compatible SemVer release ref before any registry access."""

import os
import re
from pathlib import Path


def version_from_ref(ref):
    match = re.fullmatch(
        r"refs/tags/v((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?)",
        ref,
    )
    if not match:
        raise ValueError(
            "Release requires refs/tags/vMAJOR.MINOR.PATCH[-prerelease]; build metadata is not supported"
        )
    version = match[1]
    if len(version) > 128:
        raise ValueError("Docker tag must fit 128 characters")
    if "-" in version:
        for part in version.split("-", 1)[1].split("."):
            if not part or part.isdigit() and len(part) > 1 and part.startswith("0"):
                raise ValueError("Invalid SemVer prerelease identifier")
    return version


if __name__ == "__main__":
    version = version_from_ref(os.environ.get("GITHUB_REF", ""))
    if output := os.environ.get("GITHUB_OUTPUT"):
        with Path(output).open("a") as file:
            file.write(f"version={version}\n")
    print(version)
