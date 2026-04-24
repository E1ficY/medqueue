import argparse
import os
from pathlib import Path

import trustme
import uvicorn


def ensure_dev_certificates(certs_dir: Path):
    cert_file = certs_dir / "localhost-cert.pem"
    key_file = certs_dir / "localhost-key.pem"
    ca_file = certs_dir / "localhost-ca.pem"

    if cert_file.exists() and key_file.exists() and ca_file.exists():
        return cert_file, key_file, ca_file

    certs_dir.mkdir(parents=True, exist_ok=True)
    ca = trustme.CA()
    server_cert = ca.issue_cert("localhost", "127.0.0.1", "::1")

    server_cert.cert_chain_pems[0].write_to_path(cert_file)
    server_cert.private_key_pem.write_to_path(key_file)
    ca.cert_pem.write_to_path(ca_file)

    return cert_file, key_file, ca_file


def main():
    parser = argparse.ArgumentParser(description="Run MedQueue over HTTPS (dev mode).")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-reload", action="store_true", help="Disable auto-reload")
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parent
    certs_dir = backend_dir / ".certs"
    cert_file, key_file, ca_file = ensure_dev_certificates(certs_dir)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "medqueue_project.settings")

    print("[HTTPS] Dev certificate ready")
    print(f"[HTTPS] URL: https://{args.host}:{args.port}/")
    print(f"[HTTPS] Certificate: {cert_file}")
    print(f"[HTTPS] Key: {key_file}")
    print(f"[HTTPS] CA (optional to trust in browser): {ca_file}")

    uvicorn.run(
        "medqueue_project.asgi:application",
        host=args.host,
        port=args.port,
        reload=not args.no_reload,
        ssl_certfile=str(cert_file),
        ssl_keyfile=str(key_file),
    )


if __name__ == "__main__":
    main()
