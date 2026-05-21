FROM nginx:1.27-alpine

RUN apk add --no-cache openssl

COPY nginx/bootstrap-cert.sh /docker-entrypoint.d/99-bootstrap-cert.sh

RUN chmod +x /docker-entrypoint.d/99-bootstrap-cert.sh