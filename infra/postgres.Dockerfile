FROM postgres:18.6-alpine@sha256:10a5c69a83035ab5239f5620d708520e8b28f5aa1f2b20143e6024532edadfb5
# CVE-2026-111497: signed Alpine 3.24/main fix; retain libcurl's Brotli dependency.
RUN apk add --no-cache 'brotli-libs=1.2.1-r0'
# Initialization and the database run as postgres; the root privilege helper is unused.
RUN rm /usr/local/bin/gosu
USER postgres
