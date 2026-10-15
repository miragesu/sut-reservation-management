import importlib.util
import io
import json
import urllib.error
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "registry_release", Path(__file__).resolve().parents[2] / "scripts/registry_release.py"
)
registry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registry)


@pytest.mark.parametrize("code", [200, 404, 401, 429, 500])
def test_registry_only_missing_manifest_is_absent(code):
    class Response(io.BytesIO):
        headers = {"Docker-Content-Digest": "sha256:" + "a" * 64}

    def open_url(request, **kwargs):
        if isinstance(request, str):
            return Response(json.dumps({"token": "ephemeral-synthetic-token"}).encode())
        if code != 200:
            raise urllib.error.HTTPError(request.full_url, code, "synthetic", {}, None)
        return Response()

    if code in (200, 404):
        assert registry.resolve("1.0.1", open_url) == ("sha256:" + "a" * 64 if code == 200 else None)
    else:
        with pytest.raises(urllib.error.HTTPError):
            registry.resolve("1.0.1", open_url)


@pytest.mark.parametrize("present", [True, False])
def test_explicit_release_tag_guard(monkeypatch, capsys, present):
    monkeypatch.setattr("sys.argv", ["registry_release.py", "require-absent", "1.0.0"])
    monkeypatch.setattr(registry, "resolve", lambda _: "sha256:" + "a" * 64 if present else None)
    if present:
        with pytest.raises(SystemExit, match="refusing to overwrite"):
            registry.main()
    else:
        registry.main()
        assert "unused" in capsys.readouterr().out
