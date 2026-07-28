"""Sealed Linux .run installer packaging (no DB required)."""

from __future__ import annotations

import hashlib
import io
import tarfile
from pathlib import Path
from uuid import uuid4

from ai_spm.services.enrollment_service import EnrollmentService, PAYLOAD_MARKER


def test_build_linux_installer_is_sealed_sfx(tmp_path: Path, monkeypatch):
    asset = tmp_path / "assets"
    asset.mkdir()
    (asset / "install-agent.sh").write_text("#!/bin/bash\necho ok\n", encoding="utf-8")
    (asset / "aispm-agent-installer").write_text(
        "#!/bin/bash\necho launcher\n", encoding="utf-8"
    )
    (asset / "aispm-agent-installer").chmod(0o755)
    (asset / "reconcile-browser-extensions.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    ext = asset / "browser-extension"
    ext.mkdir()
    (ext / "manifest.json").write_text('{"version":"1.0.0","name":"t"}\n', encoding="utf-8")
    (ext / "background.js").write_text("// bg\n", encoding="utf-8")
    mitm = asset / "mitmproxy"
    mitm.mkdir()
    (mitm / "web_ui_mitm.py").write_text("# addon\n", encoding="utf-8")
    (mitm / "pii_rules.py").write_text("# rules\n", encoding="utf-8")
    (mitm / "start-web-mitm.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    (mitm / "start-web-mitm.sh").chmod(0o755)

    import ai_spm.services.enrollment_service as es

    monkeypatch.setattr(es, "installer_asset_dir", lambda settings=None: asset)

    svc = EnrollmentService()
    org_id = uuid4()
    blob = svc.build_linux_installer(
        gateway_url="http://localhost:8090",
        org_id=org_id,
        org_token="test-org-token-abc",
        org_name="Dev Corp",
        org_slug="dev-corp",
    )

    assert blob.startswith(b"#!/usr/bin/env bash")
    assert PAYLOAD_MARKER in blob
    assert b"integrity check failed" in blob

    idx = blob.index(PAYLOAD_MARKER) + len(PAYLOAD_MARKER)
    payload = blob[idx:]
    expected_sha = hashlib.sha256(payload).hexdigest()
    assert f'AISPM_SHA256="{expected_sha}"'.encode() in blob

    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as tar:
        names = {m.name for m in tar.getmembers()}
        assert "enrollment.env" in names
        assert "install-agent.sh" in names
        assert "aispm-agent-installer" in names
        assert "browser-extension/manifest.json" in names
        assert "browser-extension/background.js" in names
        assert "mitmproxy/web_ui_mitm.py" in names
        assert "mitmproxy/pii_rules.py" in names
        assert "mitmproxy/start-web-mitm.sh" in names
        env = tar.extractfile("enrollment.env").read().decode()
    assert "AISPM_GATEWAY_URL='http://localhost:8090'" in env or "AISPM_GATEWAY_URL=http://localhost:8090" in env
    assert f"AISPM_ORG_ID={org_id}" in env or f"AISPM_ORG_ID='{org_id}'" in env
    assert "AISPM_ORG_TOKEN=test-org-token-abc" in env or "AISPM_ORG_TOKEN='test-org-token-abc'" in env
    # Org names with spaces must be shell-quoted so `source enrollment.env` works.
    assert "AISPM_ORG_NAME='Dev Corp'" in env


def test_enrollment_env_quotes_spaces():
    from ai_spm.services.enrollment_service import enrollment_env_contents

    text = enrollment_env_contents(
        gateway_url="http://localhost:8090",
        org_id=uuid4(),
        org_token="tok",
        org_name="Acme Corp & Co",
    )
    assert "AISPM_ORG_NAME=" in text
    assert "Corp" in text
    # Must be one assignment line, not bare `Corp` after an unquoted value.
    name_line = next(line for line in text.splitlines() if line.startswith("AISPM_ORG_NAME="))
    assert name_line.startswith("AISPM_ORG_NAME='") or name_line.startswith('AISPM_ORG_NAME="')
    assert " & " in name_line or "&" in name_line



def test_build_linux_zip_alias_returns_sfx(tmp_path: Path, monkeypatch):
    asset = tmp_path / "assets"
    asset.mkdir()
    (asset / "install-agent.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    mitm = asset / "mitmproxy"
    mitm.mkdir()
    (mitm / "web_ui_mitm.py").write_text("# addon\n", encoding="utf-8")
    (mitm / "pii_rules.py").write_text("# rules\n", encoding="utf-8")
    (mitm / "start-web-mitm.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    (mitm / "start-web-mitm.sh").chmod(0o755)

    import ai_spm.services.enrollment_service as es

    monkeypatch.setattr(es, "installer_asset_dir", lambda settings=None: asset)

    blob = EnrollmentService().build_linux_zip(
        gateway_url="http://localhost:8090",
        org_id=uuid4(),
        org_token="tok",
        org_name="Org",
    )
    assert blob.startswith(b"#!/usr/bin/env bash")
    assert PAYLOAD_MARKER in blob


def test_sealed_installer_requires_mitmproxy(tmp_path: Path, monkeypatch):
    asset = tmp_path / "assets"
    asset.mkdir()
    (asset / "install-agent.sh").write_text("#!/bin/bash\n", encoding="utf-8")

    import ai_spm.services.enrollment_service as es

    monkeypatch.setattr(es, "installer_asset_dir", lambda settings=None: asset)
    monkeypatch.setattr(es, "_repo_dir", lambda *parts: None)
    monkeypatch.setattr(es, "_repo_file", lambda *parts: None)

    try:
        EnrollmentService().build_linux_installer(
            gateway_url="http://localhost:8090",
            org_id=uuid4(),
            org_token="tok",
            org_name="Org",
        )
        raise AssertionError("expected RuntimeError for missing mitmproxy")
    except RuntimeError as exc:
        assert "mitmproxy" in str(exc).lower()
