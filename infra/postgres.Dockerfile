FROM postgres:18.6-alpine@sha256:898c60cb390d1085bc97bdd6a1ae968757421df394b071848b52b1c09c89d6a5
# Initialization and the database run as postgres; the root privilege helper is unused.
RUN rm /usr/local/bin/gosu
USER postgres
