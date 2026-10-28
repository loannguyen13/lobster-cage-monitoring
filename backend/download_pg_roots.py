"""Fetch public trust roots linked by Microsoft PostgreSQL TLS documentation."""
import ssl
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URLS = (
    "https://www.microsoft.com/pkiops/certs/Microsoft%20RSA%20Root%20Certificate%20Authority%202017.crt",
    "https://cacerts.digicert.com/DigiCertGlobalRootG2.crt.pem",
)


def main():
    certificates = []
    for url in URLS:
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read()
        pem = data.decode("ascii") if data.startswith(b"-----BEGIN CERTIFICATE-----") else ssl.DER_cert_to_PEM_cert(data)
        # Reject malformed downloads before writing the bundle.
        ssl.PEM_cert_to_DER_cert(pem)
        certificates.append(pem.strip())
    target = ROOT / "backend" / "certs" / "azure-postgresql-roots.pem"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(certificates) + "\n", encoding="ascii")
    print(f"Saved {len(certificates)} public CA certificates to {target}")


if __name__ == "__main__":
    main()
