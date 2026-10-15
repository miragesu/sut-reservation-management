import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "release_version", Path(__file__).resolve().parents[2] / "scripts/release_version.py"
)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


@pytest.mark.parametrize("version", ["0.0.0", "1.2.3", "10.21.300", "1.0.0-rc.1", "1.0.0-0", "1.0.0-01rc"])
def test_release_ref_accepts_explicit_docker_compatible_semver(version):
    assert release.version_from_ref("refs/tags/v" + version) == version


@pytest.mark.parametrize(
    "ref",
    [
        "refs/heads/main",
        "refs/pull/6/merge",
        "refs/tags/vlatest",
        "refs/tags/v1.2",
        "refs/tags/v01.2.3",
        "refs/tags/v1.02.3",
        "refs/tags/v1.2.03",
        "refs/tags/v1.0.0+build.1",
        "refs/tags/v1.0.0-01",
        "refs/tags/v1.0.0-rc..1",
        "refs/tags/v1.0.0-",
        "refs/tags/v1.0.0\nversion=latest",
        "refs/tags/v1.0.0-" + "x" * 128,
    ],
)
def test_release_ref_rejects_branch_partial_unsafe_or_non_semver_tags(ref):
    with pytest.raises(ValueError):
        release.version_from_ref(ref)
