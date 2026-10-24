import json
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from opspilot.adapters.oidc.verifier import OidcVerifier
from opspilot.shared.errors import DependencyUnavailable, Unauthenticated

ISSUER = "https://identity.opspilot.invalid/realms/test"


@pytest.fixture
def identity():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    key.update(kid="test-key", alg="RS256", use="sig")
    calls, clock = [], [1000.0]

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json={"keys": [key]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    verifier = OidcVerifier(ISSUER, "api", ISSUER + "/certs", client, monotonic=lambda: clock[0])
    claims = {
        "iss": ISSUER,
        "aud": "api",
        "sub": "test-subject",
        "typ": "Bearer",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
    }
    return private, key, claims, verifier, client, calls, clock


def signed(private, claims, **headers):
    return jwt.encode(claims, private, algorithm="RS256", headers={"kid": "test-key", **headers})


def test_valid_access_and_cached_key_without_network(identity):
    private, _, claims, verifier, client, calls, _ = identity
    token = signed(private, claims)
    assert verifier.verify(token).subject == "test-subject"
    client.close()
    assert verifier.verify(token).issuer == ISSUER
    assert len(calls) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"iss": "https://attacker.invalid"},
        {"aud": "other"},
        {"exp": 1},
        {"iat": "future"},
        {"nbf": "future"},
        {"sub": ""},
        {"typ": "ID"},
        {"exp": "far_future"},
        {"iat": "100"},
        {"nbf": True},
        {"exp": True},
        {"aud": []},
    ],
)
def test_invalid_claims(identity, change):
    private, _, claims, verifier, *_ = identity
    # Resolve relative times at execution; a longer integration suite must not
    # turn collection-time future claims into valid current timestamps.
    change = {
        key: int(time.time()) + (1000 if value == "far_future" else 120)
        if value in ("future", "far_future")
        else value
        for key, value in change.items()
    }
    with pytest.raises(Unauthenticated):
        verifier.verify(signed(private, {**claims, **change}))


@pytest.mark.parametrize("claim", ["iss", "aud", "sub", "exp", "iat"])
def test_missing_required_claim(identity, claim):
    private, _, claims, verifier, *_ = identity
    claims.pop(claim)
    with pytest.raises(Unauthenticated):
        verifier.verify(signed(private, claims))


@pytest.mark.parametrize("algorithm", ["HS256", "none"])
def test_algorithm_confusion_rejected_without_network(identity, algorithm):
    _, _, claims, verifier, _, calls, _ = identity
    token = jwt.encode(
        claims,
        "unit-test-hmac-key-for-negative-case-only" if algorithm == "HS256" else None,
        algorithm=algorithm,
        headers={"kid": "test-key"},
    )
    with pytest.raises(Unauthenticated):
        verifier.verify(token)
    assert not calls


def test_invalid_signature(identity):
    _, _, claims, verifier, *_ = identity
    another = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(Unauthenticated):
        verifier.verify(signed(another, claims))


def test_expired_cache_failure_closed(identity):
    private, _, claims, verifier, client, _, clock = identity
    token = signed(private, claims)
    verifier.verify(token)
    clock[0] += 301
    client._transport = httpx.MockTransport(lambda request: httpx.Response(503))
    with pytest.raises(DependencyUnavailable):
        verifier.verify(token)
    assert not verifier.ready()


def test_unknown_kid_rate_limited_and_does_not_follow_token_urls(identity):
    private, _, claims, verifier, _, calls, clock = identity
    assert verifier.ready()
    token = signed(
        private, claims, kid="unknown", jku="http://127.0.0.1/secrets", x5u="file:///secrets"
    )
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(verifier.verify, token) for _ in range(20)]
    for future in futures:
        with pytest.raises(Unauthenticated):
            future.result()
    assert len(calls) == 1
    clock[0] += 31
    with pytest.raises(Unauthenticated):
        verifier.verify(token)
    assert len(calls) == 2
    assert all(url == ISSUER + "/certs" for url in calls)


@pytest.mark.parametrize(
    "data,status",
    [({"keys": []}, 200), ({"keys": "invalid"}, 200), ({"keys": []}, 302), ({"keys": []}, 503)],
)
def test_invalid_jwks_unavailable(data, status):
    verifier = OidcVerifier(
        ISSUER,
        "api",
        ISSUER + "/certs",
        httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(status, json=data))
        ),
    )
    assert not verifier.ready()


@pytest.mark.parametrize(
    "attack", ["duplicate", "private", "weak", "wrong_operations", "too_many", "oversized"]
)
def test_malicious_or_ambiguous_jwks_fails_closed(identity, attack):
    _, key, _, _, _, _, _ = identity
    body = {"keys": [key.copy()]}
    if attack == "duplicate":
        body["keys"] *= 2
    elif attack == "private":
        body["keys"][0]["d"] = "private-material-is-forbidden"
    elif attack == "weak":
        private = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        body["keys"] = [
            {
                **json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key())),
                "kid": "test-key",
            }
        ]
    elif attack == "wrong_operations":
        body["keys"][0]["key_ops"] = ["encrypt"]
    elif attack == "too_many":
        body["keys"] *= 33

    def handler(request):
        return (
            httpx.Response(200, content=b"x" * 131073)
            if attack == "oversized"
            else httpx.Response(200, json=body)
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        verifier = OidcVerifier(ISSUER, "api", ISSUER + "/certs", http)
        assert not verifier.ready()


def test_rotating_to_new_key_refreshes_only_fixed_jwks(identity):
    private, _, claims, verifier, client, calls, clock = identity
    verifier.verify(signed(private, claims))
    replacement = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(replacement.public_key()))
    jwk["kid"] = "new-key"
    clock[0] += 31
    client._transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"keys": [jwk]})
    )
    assert verifier.verify(signed(replacement, claims, kid="new-key")).subject == "test-subject"
    with pytest.raises(Unauthenticated):
        verifier.verify(signed(private, claims))
    assert calls == [ISSUER + "/certs"]


def test_admin_role_claims_never_create_local_authority(identity):
    from uuid import uuid4

    from opspilot.identity.domain.principal import Principal, Role
    from opspilot.shared.errors import Forbidden

    private, _, claims, verifier, *_ = identity
    external = verifier.verify(
        signed(private, {**claims, "roles": ["admin"], "realm_access": {"roles": ["admin"]}})
    )
    assert set(external.__dataclass_fields__) == {"issuer", "subject"}
    principal = Principal(uuid4(), True, frozenset({Role.OPERATOR}))
    with pytest.raises(Forbidden):
        principal.require_audit_read()
