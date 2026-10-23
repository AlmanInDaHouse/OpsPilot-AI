FROM quay.io/keycloak/keycloak:26.8.1@sha256:79c623a22abacf3fe6c00a5fb30f5b7843d717b234033b80995891c06116d244 AS keycloak
FROM alpine:3.24@sha256:71e9b7bae160ba167fa17414401b94cbcdaf3c32feeab9298bd794a2a0614c35
RUN apk add --no-cache bash ca-certificates=20261020-r0 libstdc++ freetype fontconfig
ADD --checksum=sha256:9138eab0f7d230e17163953f015ec9ae2431dbc49069c658b7f991e45b54fb9b https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.13%2B9/OpenJDK21U-jre_x64_alpine-linux_hotspot_21.0.13_9.tar.gz /tmp/temurin.tar.gz
RUN mkdir -p /opt/java && tar -xzf /tmp/temurin.tar.gz -C /opt/java --strip-components=1 && rm /tmp/temurin.tar.gz
COPY --from=keycloak --chown=1000:0 /opt/keycloak /opt/keycloak
ENV JAVA_HOME=/opt/java PATH=/opt/java/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin KC_RUN_IN_CONTAINER=true
WORKDIR /opt/keycloak
USER 1000:0
ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
