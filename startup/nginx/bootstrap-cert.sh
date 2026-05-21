#!/bin/sh
set -eu

CERT_DIR=/etc/letsencrypt/live/medqueue.me
FULLCHAIN="$CERT_DIR/fullchain.pem"
PRIVKEY="$CERT_DIR/privkey.pem"

if [ ! -s "$FULLCHAIN" ] || [ ! -s "$PRIVKEY" ]; then
    mkdir -p "$CERT_DIR" /etc/letsencrypt/archive/medqueue.me

    cat >/tmp/medqueue-openssl.cnf <<'EOF'
[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = req_distinguished_name
x509_extensions = v3_req

[req_distinguished_name]
C = KZ
ST = Almaty
L = Almaty
O = MedQueue
CN = medqueue.me

[v3_req]
subjectAltName = @alt_names

[alt_names]
DNS.1 = medqueue.me
DNS.2 = www.medqueue.me
EOF

    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
        -keyout "$PRIVKEY" \
        -out "$FULLCHAIN" \
        -config /tmp/medqueue-openssl.cnf
fi