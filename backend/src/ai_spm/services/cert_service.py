"""mTLS certificate issuance for endpoint agents."""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)

CERTS_DIR = Path(__file__).resolve().parents[4] / "infrastructure" / "certs"


class CertService:
    def __init__(self, certs_dir: Path | None = None) -> None:
        self.certs_dir = certs_dir or CERTS_DIR

    def ensure_ca(self) -> tuple[Path, Path]:
        self.certs_dir.mkdir(parents=True, exist_ok=True)
        ca_key = self.certs_dir / "ca.key"
        ca_crt = self.certs_dir / "ca.crt"
        if not ca_key.exists():
            subprocess.run(
                [
                    "openssl", "req", "-x509", "-newkey", "rsa:4096", "-sha256",
                    "-days", "365", "-nodes",
                    "-keyout", str(ca_key),
                    "-out", str(ca_crt),
                    "-subj", "/CN=AI-SPM Dev CA/O=AI-SPM/C=US",
                ],
                check=True,
                capture_output=True,
            )
        return ca_crt, ca_key

    def issue_agent_cert(
        self,
        org_id: UUID,
        agent_id: UUID,
        csr_pem: str | None = None,
    ) -> dict:
        """Issue client certificate with SPIFFE SAN for tenant-bound mTLS."""
        ca_crt, ca_key = self.ensure_ca()
        # OpenSSL CN max is 64 chars — do not embed both UUIDs in CN.
        # Full org/agent binding lives in the SPIFFE SAN below.
        name = f"agent-{agent_id}"
        cn = name  # "agent-" + 36-char UUID = 42 chars

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            agent_key = tmp_path / f"{name}.key"
            agent_csr = tmp_path / f"{name}.csr"
            agent_crt = tmp_path / f"{name}.crt"
            ext_file = tmp_path / f"{name}.ext"

            if csr_pem:
                agent_csr.write_text(csr_pem)
                subprocess.run(
                    ["openssl", "genrsa", "-out", str(agent_key), "2048"],
                    check=True,
                    capture_output=True,
                )
            else:
                subprocess.run(
                    ["openssl", "genrsa", "-out", str(agent_key), "2048"],
                    check=True,
                    capture_output=True,
                )
                subprocess.run(
                    [
                        "openssl", "req", "-new",
                        "-key", str(agent_key),
                        "-out", str(agent_csr),
                        "-subj", f"/CN={cn}/O=AI-SPM Agent",
                    ],
                    check=True,
                    capture_output=True,
                )

            spiffe_uri = f"spiffe://aispm.io/org/{org_id}/agent/{agent_id}"
            ext_file.write_text(
                f"subjectAltName = URI:{spiffe_uri}\n"
                "extendedKeyUsage = clientAuth\n"
            )

            subprocess.run(
                [
                    "openssl", "x509", "-req",
                    "-in", str(agent_csr),
                    "-CA", str(ca_crt),
                    "-CAkey", str(ca_key),
                    "-CAcreateserial",
                    "-out", str(agent_crt),
                    "-days", "90",
                    "-sha256",
                    "-extfile", str(ext_file),
                ],
                check=True,
                capture_output=True,
            )

            cert_pem = agent_crt.read_text()
            key_pem = agent_key.read_text()
            fingerprint = hashlib.sha256(cert_pem.encode()).hexdigest()

            out_dir = self.certs_dir / "issued"
            out_dir.mkdir(exist_ok=True)
            (out_dir / f"{name}.crt").write_text(cert_pem)
            (out_dir / f"{name}.key").write_text(key_pem)

        expires_at = datetime.now(UTC) + timedelta(days=90)
        return {
            "certificate_pem": cert_pem,
            "private_key_pem": key_pem,
            "ca_certificate_pem": ca_crt.read_text(),
            "cert_fingerprint": fingerprint,
            "spiffe_uri": spiffe_uri,
            "expires_at": expires_at.isoformat(),
        }
