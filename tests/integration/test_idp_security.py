import httpx
import pytest

from .conftest import IDP_BASE, pkce_tokens

pytestmark = pytest.mark.integration


def test_wrong_pkce_verifier_rejected_by_real_idp(accounts):
    result = pkce_tokens(accounts["operator"], wrong_verifier=True)
    assert result.get("error") == "invalid_grant" and "access_token" not in result


def test_resource_owner_password_grant_disabled_for_product_client(accounts):
    account = accounts["operator"]
    with httpx.Client(trust_env=False, timeout=5) as client:
        response = client.post(
            IDP_BASE + "/realms/opspilot/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "opspilot-lab-pkce",
                "username": account["username"],
                "password": account["password"],
            },
        )
    assert response.status_code == 400
    assert response.json().get("error") == "unauthorized_client"
