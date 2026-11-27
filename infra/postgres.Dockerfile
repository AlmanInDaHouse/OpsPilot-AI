FROM postgres:19.0-alpine@sha256:cac45fb483caee3668946088a1c0532db89d5285c28dbfeac889b4068296e06f
# CVE-2026-111497: signed Alpine 3.24/main fix; retain libcurl's Brotli dependency.
RUN apk add --no-cache 'brotli-libs=1.2.1-r0'
# Initialization and the database run as postgres; the root privilege helper is unused.
RUN rm /usr/local/bin/gosu
USER postgres
