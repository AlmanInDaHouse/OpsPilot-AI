FROM quay.io/keycloak/keycloak:26.8.1@sha256:79c623a22abacf3fe6c00a5fb30f5b7843d717b234033b80995891c06116d244 AS keycloak
FROM debian:bookworm-slim@sha256:7ff6ba31527b9e336162fa061746c366c4b2032f4d2cff2078bea43f78efe3f8
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates=20250419~deb12u2 libstdc++6 libfreetype6 && rm -rf /var/lib/apt/lists/*
ADD --checksum=sha256:a535a1df9c6284d9618872984e026ae0352d1f7e9e0605425c0e6114f47351dd https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.13%2B9/OpenJDK21U-jre_x64_linux_hotspot_21.0.13_9.tar.gz /tmp/temurin.tar.gz
RUN mkdir -p /opt/java && tar -xzf /tmp/temurin.tar.gz -C /opt/java --strip-components=1 && rm /tmp/temurin.tar.gz
COPY --from=keycloak --chown=1000:0 /opt/keycloak /opt/keycloak
ENV JAVA_HOME=/opt/java PATH=/opt/java/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin KC_RUN_IN_CONTAINER=true
WORKDIR /opt/keycloak
USER 1000:0
ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
