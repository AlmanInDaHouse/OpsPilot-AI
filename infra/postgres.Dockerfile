FROM postgres:18.6-alpine@sha256:898c60cb390d1085bc97bdd6a1ae968757421df394b071848b52b1c09c89d6a5
# CVE-2026-111497: signed Alpine 3.24/main fix; retain libcurl's Brotli dependency.
RUN apk add --no-cache 'brotli-libs=1.2.1-r0'
# Initialization and the database run as postgres; the root privilege helper is unused.
RUN rm /usr/local/bin/gosu
USER postgres
