"""Strict OIDC access-token verification with a bounded, synchronized JWKS cache."""

import threading
import time
from collections.abc import Callable
from typing import Any

import httpx
import jwt

from opspilot.identity.domain.principal import ExternalIdentity
from opspilot.shared.errors import DependencyUnavailable, Unauthenticated


class OidcVerifier:
    def __init__(
        self,
        issuer: str,
        audience: str,
        jwks_url: str,
        client: httpx.Client,
        ttl: int = 300,
        refresh_interval: int = 30,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.issuer, self.audience, self.jwks_url = issuer, audience, jwks_url
        self.client, self.ttl, self.refresh_interval = client, ttl, refresh_interval
        self.clock = monotonic
        self._keys: dict[str, Any] = {}
        self._expires = 0.0
        self._last_attempt = float("-inf")
        self._lock = threading.Lock()

    def _refresh(self) -> None:
        self._last_attempt = self.clock()
        try:
            with self.client.stream("GET", self.jwks_url, follow_redirects=False) as response:
                response.raise_for_status()
                if 300 <= response.status_code < 400:
                    raise ValueError("Redirect prohibited")
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 131072:
                        raise ValueError("JWKS too large")
            import json

            data = json.loads(raw)
            if not isinstance(data, dict) or not isinstance(data.get("keys"), list):
                raise ValueError("Invalid JWKS")
            keys = {}
            if len(data["keys"]) > 32:
                raise ValueError("Too many keys")
            for item in data["keys"]:
                if (
                    not isinstance(item, dict)
                    or item.get("kty") != "RSA"
                    or item.get("alg", "RS256") != "RS256"
                    or item.get("use", "sig") != "sig"
                ):
                    continue
                kid = item.get("kid")
                if not isinstance(kid, str) or not 1 <= len(kid) <= 200 or kid in keys:
                    raise ValueError("Invalid key identifier")
                if "d" in item or ("key_ops" in item and item["key_ops"] != ["verify"]):
                    raise ValueError("Private key in public JWKS")
                key = jwt.PyJWK.from_dict(item, algorithm="RS256").key
                if key.key_size < 2048:
                    raise ValueError("Weak key")
                keys[kid] = key
            if not keys:
                raise ValueError("No usable keys")
            self._keys, self._expires = keys, self.clock() + self.ttl
        except (httpx.HTTPError, ValueError, TypeError, KeyError, jwt.PyJWTError) as exc:
            raise DependencyUnavailable() from exc

    def _key(self, kid: str) -> Any:
        with self._lock:
            now = self.clock()
            if now >= self._expires or kid not in self._keys:
                if now - self._last_attempt >= self.refresh_interval:
                    self._refresh()
                elif now >= self._expires:
                    raise DependencyUnavailable()
            if self.clock() >= self._expires:
                raise DependencyUnavailable()
            if kid not in self._keys:
                raise Unauthenticated()
            return self._keys[kid]

    def ready(self) -> bool:
        with self._lock:
            if self.clock() >= self._expires:
                if self.clock() - self._last_attempt < self.refresh_interval:
                    return False
                try:
                    self._refresh()
                except DependencyUnavailable:
                    return False
            return bool(self._keys) and self.clock() < self._expires

    def verify(self, token: str) -> ExternalIdentity:
        if not 1 <= len(token) <= 16384:
            raise Unauthenticated()
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or header.get("crit"):
                raise Unauthenticated()
            kid = header.get("kid")
            if not isinstance(kid, str) or not 1 <= len(kid) <= 200:
                raise Unauthenticated()
            key = self._key(kid)
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self.issuer,
                audience=self.audience,
                leeway=30,
                options={"require": ["iss", "aud", "exp", "iat", "sub"]},
            )
            for field in ("exp", "iat", "nbf"):
                if field in claims and type(claims[field]) is not int:
                    raise Unauthenticated()
            if not 0 < claims["exp"] - claims["iat"] <= 300 or claims.get("typ") != "Bearer":
                raise Unauthenticated()
            subject = claims["sub"]
            if not isinstance(subject, str) or not 1 <= len(subject) <= 255:
                raise Unauthenticated()
            return ExternalIdentity(self.issuer, subject)
        except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
            raise Unauthenticated() from exc
