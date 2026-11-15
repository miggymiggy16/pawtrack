"""
PawTrack - create a self-signed HTTPS certificate for the local network
=======================================================================
Browsers only allow camera access over HTTPS (or http://localhost). Run this
once, then start PawTrack with HTTPS enabled:

    python scripts/make_cert.py

Add these lines to .env:

    PAWTRACK_HTTPS=True
    PAWTRACK_SSL_CERT=certs/pawtrack.crt
    PAWTRACK_SSL_KEY=certs/pawtrack.key

Then open https://<this-computer-ip>:5000 on the other devices. Accept the
certificate warning and allow camera access. For a certificate that devices
trust without a warning, use mkcert and replace the two files.
"""
import ipaddress
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

BASE_DIR = Path(__file__).resolve().parent.parent
CERT_DIR = BASE_DIR / "certs"
CERT_FILE = CERT_DIR / "pawtrack.crt"
KEY_FILE = CERT_DIR / "pawtrack.key"


def local_addresses():
    """Localhost plus every IPv4/IPv6 address this computer currently has."""
    addresses = {"127.0.0.1", "::1"}
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            try:
                addresses.add(str(ipaddress.ip_address(info[4][0].split("%")[0])))
            except ValueError:
                pass
    except OSError:
        pass
    # The address used to reach the internet; no packet is actually sent.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            addresses.add(sock.getsockname()[0])
    except OSError:
        pass
    return sorted(addresses)


def build_certificate(addresses):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "PH"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "PawTrack"),
        x509.NameAttribute(NameOID.COMMON_NAME, "PawTrack Local"),
    ])
    alt_names = [x509.DNSName("localhost")]
    for address in addresses:
        try:
            alt_names.append(x509.IPAddress(ipaddress.ip_address(address)))
        except ValueError:
            pass
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(key, hashes.SHA256())
    )
    return key, certificate


def main():
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    addresses = local_addresses()
    key, certificate = build_certificate(addresses)
    KEY_FILE.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    CERT_FILE.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    print(f"Created {CERT_FILE}")
    print(f"Created {KEY_FILE}")
    print("Certificate addresses: localhost, " + ", ".join(addresses))
    print()
    print("Add these lines to .env:")
    print("  PAWTRACK_HTTPS=True")
    print("  PAWTRACK_SSL_CERT=certs/pawtrack.crt")
    print("  PAWTRACK_SSL_KEY=certs/pawtrack.key")
    print()
    print("Then run: python app.py")
    print("Open https://<this-computer-ip>:5000 on the other devices.")
    print("Accept the certificate warning, then allow camera access.")
    print("For a trusted certificate, use mkcert and replace these two files.")


if __name__ == "__main__":
    main()
